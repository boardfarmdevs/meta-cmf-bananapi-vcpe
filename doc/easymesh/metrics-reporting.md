# STA and AP metrics reporting

## Current state

Metrics reporting is active on the rev130 five-agent lab. Every agent sends an
AP Metrics Response on its configured interval and the controller persists the
STA, BSS and radio portions of the report.

```text
wmediumd SNR and frame delivery
        |
        v
Linux 7 hwsim per-link signal
        |
        v
OneWifi/HAL association, rate and traffic statistics
        |
        v
EasyMesh agent -- AP Metrics Response (1905 CMDU) --> controller
                                                        |
                                                        v
                                      STAList / BSSList / RadioList
                                                        |
                                                        v
                                            WebUI/API and optimizer
```

This is an observation path. A reporting threshold does not select a target AP
or initiate a steer. The external optimizer must consume the observations and
use a separate Client Steering Request when its own policy decides to act.

## Why it was inactive

The standard primitives and most of the agent reporting code already existed.
The path was disabled by several independent implementation defects:

1. OneWifi encoded `Primary VLAN ID` but decoded the misspelled
   `Primay VLAN ID`. It rejected every received policy subdocument before
   applying it.
2. The controller discarded the agent's Multi-AP Profile during
   autoconfiguration and stored Profile 0. It then rejected valid Profile-2/3
   AP Extended Metrics and Radio Metrics TLVs during message validation.
3. ACK routing added for steering recognized only outstanding steering message
   IDs. A Policy Configuration ACK was dropped before the policy state machine
   could finish.
4. Automatically created per-radio policy rows had a zero owner device MAC.
   They were invisible to `get_policy`, so the WebUI returned empty radio
   policy arrays.
5. The AP Metrics Response receiver persisted STA fields but ignored AP
   Extended Metrics and Radio Metrics.
6. The WebUI submitted all devices to a native command that accepts one device
   per transaction. Requests returned false success or collided with the
   controller's still-running policy state machine.
7. The Connected Clients adapter used the compact topology model, which
   intentionally omits periodic STA metrics. The controller contained valid
   RCPI, but the WebUI and `/api/v1/clients` rendered it as unavailable.

The retained activation fixes are libwebconfig patch `0003` and EasyMesh
patches `0042` through `0044`. Patch `0048` additionally prevents a stale
Agent-local metrics row from changing association ownership: metrics update an
existing current association but never create or move one. The WebUI skips
unchanged policy nodes, applies changed nodes one at a time, verifies
controller state and allows the asynchronous 1905 transaction to retire before
continuing. Its client adapter joins the detailed `get_sta` metrics to the live
topology inventory by STA MAC.

## Active policy values

The current defaults are applied independently to all five devices and all 15
radios:

| Setting | Value | Purpose |
| --- | ---: | --- |
| AP metrics interval | 5 seconds | periodic AP Metrics Response cadence |
| STA RCPI reporting threshold | 120 | threshold carried in the radio metrics policy |
| STA RCPI hysteresis | 5 | report hysteresis around that threshold |
| AP utilization threshold | 60 | channel-utilization reporting threshold |
| include STA traffic statistics | 1 | packets, bytes and errors |
| include STA link metrics | 1 | RCPI and link-rate fields |
| include STA status | 0 | associated-STA status reporting disabled |
| radio steering mode | 2 | RCPI steering allowed, not an autonomous-policy proof |

RCPI is an unsigned EasyMesh value. Its approximate dBm conversion is:

```text
dBm  = RCPI / 2 - 110
RCPI = 2 * (dBm + 110)
```

For example, RCPI 138 is about -41 dBm and RCPI 88 is about -66 dBm.

## Configure it

### WebUI

Open the controller WebUI and select **Policy Settings**. On the current
rev130 lab this is `http://192.168.2.130:8888`; use the forwarded controller
address for another deployment.

1. Select a controller or agent in **Device**.
2. In **AP Metrics Reporting Policy**, set **Interval (seconds)**. Five seconds
   is a useful interactive-lab value. Select **All Devices** when the same
   interval should be staged for every device, then select the section's
   **Save** button.
3. In **Radio Specific Metrics Policy**, set each existing RUID row:
   **STA RCPI Threshold**, **STA RCPI Hysteresis**, **AP Utilization
   Threshold**, and the three STA reporting enable fields. Select the
   section's **Save** button.
4. Repeat the per-radio step for each device. Keep the RUIDs already shown for
   that device; RUIDs are not interchangeable between agents.
5. Select the page-level **Apply Policy Settings** button.
6. Wait for the success result, then reload the policy and verify the values.

The section **Save** buttons only stage edits in the browser. They do not send
a Policy Configuration Request. **Apply Policy Settings** posts the complete
policy and is the required final step. The server skips unchanged devices and
applies changed devices sequentially. A five-device update can therefore take
about 10--11 seconds.

A successful apply means every changed device was admitted and its new state
was observed at the controller. The controller and agent logs remain the
protocol-level proof of Policy Configuration and 1905 ACK delivery.

The **Steering Policy** card on the same page controls steering eligibility and
thresholds. It is distinct from metrics reporting: reporting produces
observations, while steering settings constrain a later steering decision.

### Client REST API and WebUI

Read the current associated clients and their reported signal:

```sh
curl -fsS http://127.0.0.1:8888/api/v1/clients \
  | jq -r '.clients[]
      | [.hostname, .mac, .connected_device, .connected_bssid,
         .client_metrics.rcpi, .client_metrics.rssi_dbm]
      | @tsv'
```

The same data is shown at the WebUI `/clients` route. Its **Signal** column
renders, for example, `-41 dBm (RCPI 138)`. While that page is visible the
browser fetches `/api/v1/clients` every two seconds. Requests do not overlap,
and polling pauses when another tab is selected. The configured AP Metrics
Response interval is five seconds, so several two-second browser updates can
legitimately show the same observation.

`client_metrics.last_updated` records when the adapter read the current
controller model. The native model does not yet expose the exact report-receipt
timestamp, so this field must not be interpreted as measurement age.

### Policy REST API

Read the complete current policy through the API:

```sh
curl -fsS http://127.0.0.1:8888/api/v1/wifipolicy | jq .
```

The GET response contains `policyConfig`. A POST accepts that array, not the
outer GET wrapper. Always start from the live result so the current device and
RUID identities are retained. This example creates a restorable backup,
changes the complete metrics policy, and submits it:

```sh
policy_url=http://127.0.0.1:8888/api/v1/wifipolicy
policy_stamp=$(date -u +%Y%m%dT%H%M%SZ)
policy_get=/tmp/wifipolicy-${policy_stamp}.get.json
policy_backup=/tmp/wifipolicy-${policy_stamp}.post.json
policy_new=/tmp/wifipolicy-${policy_stamp}.new.json

curl -fsS "$policy_url" | tee "$policy_get" \
  | jq '.policyConfig' > "$policy_backup"

jq 'map(.apMetricReportingPolicy.interval = 5)
    | map(.radioSpecificMetricsPolicy |= map(
        .starCPIThreshold = 120
        | .starCPIHysteresis = 5
        | .apUtilizationThreshold = 60
        | .staTrafficStats = 1
        | .staLinkMetrics = 1
        | .staStatus = 0))' \
  "$policy_backup" > "$policy_new"

curl --fail --show-error --silent --max-time 30 \
  -H 'Content-Type: application/json' \
  --data-binary @"$policy_new" "$policy_url" | jq .
```

The field names `starCPIThreshold` and `starCPIHysteresis` are the current API
spelling. Do not silently correct them in a request. A successful response is:

```json
{"message":"Policy updated successfully","success":true}
```

Inspect what the controller now returns:

```sh
curl -fsS "$policy_url" \
  | jq -r '.policyConfig[] as $device
      | $device.radioSpecificMetricsPolicy[]
      | [$device.id, .id, $device.apMetricReportingPolicy.interval,
         .starCPIThreshold, .starCPIHysteresis,
         .apUtilizationThreshold, .staTrafficStats,
         .staLinkMetrics, .staStatus]
      | @tsv'
```

Restore the exact saved policy if required:

```sh
curl --fail --show-error --silent --max-time 30 \
  -H 'Content-Type: application/json' \
  --data-binary @"$policy_backup" "$policy_url" | jq .
```

Do not copy a policy JSON file between deployments. Device MAC addresses and
RUIDs belong to the live hwsim radio inventory. Also allow at least 30 seconds
for an API client timeout: a changed policy is deliberately serialized into
one EasyMesh transaction per device.

### Other interfaces

Use each interface for its intended plane:

| Interface | Use | Do not use it for |
| --- | --- | --- |
| WebUI **Policy Settings** | interactive policy editing and application | proving that the agent sent reports |
| `/api/v1/wifipolicy` | repeatable policy backup, transformation and deployment | changing RF conditions |
| controller MySQL tables | read-only inspection of persisted policy and metrics | editing policy rows directly |
| `journalctl -u em_ctrl.service` and `/tmp/em_agent.log` | protocol and reporting evidence | configuration persistence |
| wmediumd configurator/control socket | RF stimulus such as an SNR ramp | inserting a synthetic RCPI into EasyMesh |
| `steer.sh` or a future optimizer | issuing a steering action | enabling metrics collection |

There is no separate policy daemon to configure. The WebUI is an `em_cli`
front end and its REST endpoint drives the controller's native policy command.
Direct SQL updates bypass Policy Configuration Requests, ACK handling and agent
persistence and are unsupported. `steer.sh` performs a steering action; it does
not install the reporting policy.

## Verify it

### Policy and protocol state

Check model and reporting state in the controller container:

```sh
lxc exec bpibroadband -- mysql -N -B -uroot OneWifiMesh -e '
select count(*), min(Profile), max(Profile) from DeviceList;
select count(*) from RadioList;
select count(*) from PolicyList;
select MACAddress, BSSID, RCPI, PacketsSent, PacketsReceived
  from STAList where Associated=1 order by MACAddress;'

for node in bpibroadband bpiap bpiap-001 bpiap-002 bpiap-003; do
  lxc exec "$node" -- grep 'AP Metrics Response sent' /tmp/em_agent.log \
    | tail -1
done

lxc exec bpibroadband -- journalctl -u em_ctrl.service --no-pager \
  | grep 'Handling 1905 ACK for Policy Cfg' | tail
```

Run the API readback after applying a policy and use the database and log
checks as independent evidence. The minimum acceptance criteria are:

- the GET result contains the requested values for every intended device and
  RUID;
- every agent continues to emit periodic `AP Metrics Response sent` entries;
- the controller handles a Policy Configuration ACK for each changed device;
- associated fronthaul STA rows acquire non-zero RCPI and traffic fields.

### End-to-end RF verification

Policy configuration alone proves only the control plane. To prove that RCPI
is a live observation, use the wmediumd configurator to apply a reversible RF
scenario:

```sh
cd gen/wmediumd/configurator
python3 -m wmdcfg.cli inventory -o /tmp/inventory.json
python3 -m wmdcfg.cli status
python3 -m wmdcfg.cli validate scenarios/two-ap-crossover.wmd
python3 -m wmdcfg.cli compile scenarios/two-ap-crossover.wmd \
  --inventory /tmp/inventory.json \
  --bind client=wlan-client \
  --bind ap_a=bpibroadband \
  --bind ap_b=bpiap \
  -o /tmp/two-ap-crossover.plan.json
sudo python3 -m wmdcfg.cli run /tmp/two-ap-crossover.plan.json \
  --output-root /tmp/wmdcfg-runs
```

Compilation requires one explicit `--bind role=container` for every scenario
role. Replace the example containers with identities from the captured
inventory. Observe `STAList.RCPI` before, during and after the phase. Generate
client traffic after restoring the link because hwsim supplies a fresh signal
value when a frame traverses it. The runner captures and restores every
touched link; confirm its final result before accepting the test.

See [configurator.md](configurator.md) for role binding and scenario authoring,
and [wmediumd.md](wmediumd.md) for the control-socket and RF-model details.

### Live WebUI RCPI monitor

Use the purpose-built wrapper when the goal is to watch signal change rather
than to author a scenario manually:

```sh
cd gen/wmediumd/configurator
./run-rcpi-monitor.sh wlan-client
```

The wrapper discovers the selected client's MAC, current serving BSSID and AP
from live LXD/hwsim inventory. It then compiles
`scenarios/client-rcpi-monitor.wmd`, keeps client traffic flowing, and changes
that one bidirectional link from 45 to 25 dB and back six times. It prints the
same API values every two seconds while the WebUI **Connected Clients** page
updates. The 130-second runner uses atomic wmediumd control-socket generations,
protects backhaul links, verifies every update and restores the captured medium
state even after a handled interrupt.

The traffic target defaults to `10.0.0.1`; override it when required:

```sh
WMD_TRAFFIC_TARGET=10.0.0.254 ./run-rcpi-monitor.sh wlan-client-3
```

Traffic is required because hwsim attaches the current simulated signal to
frames. Without frames, a new wmediumd SNR can be applied correctly while the
last controller RCPI remains unchanged.

The 2026-08-18 acceptance result was:

```text
devices/profile       5 devices, all Profile 3
radios                 15
policy rows            70
STA rows               14 (10 fronthaul clients and 4 backhaul STAs)
fronthaul STA metrics  10/10 with non-zero RCPI, rates and traffic counters
agent cadence          5/5 agents reporting 10 BSSs and 3 radios
```

An end-to-end medium test changed both directions between
`wlan-client` and its serving AP from 50 dB to 25 dB. The controller RCPI moved
from 138 to 88. After restoring 50 dB and generating traffic, it returned to
138. This verifies that the value comes through the simulated radio path.

The dedicated RCPI monitor also passed on 2026-08-18 in 130.8 seconds with a
verified restore. Its two-second API samples repeatedly moved through RCPI
138, 128, 120, 116, 100 and 96 while the client remained associated to the
same BSSID, then returned to 138 after restore. All ten associated clients had
non-zero RCPI and all three EasyMesh services retained their PIDs with zero
restarts.

## Current limitations

- Radio noise and utilization remain zero because the current hwsim OneWifi
  HAL returns zero survey/channel values. The corresponding TLVs are sent,
  accepted and persisted; useful survey synthesis is separate work.
- The four backhaul STA rows do not yet receive the periodic client metric
  fields. The ten fronthaul WLAN clients do.
- Some hwsim-reported downlink rates exceed signed SQL `INT` range and appear
  negative in `STAList`. RCPI, association and traffic counters are unaffected,
  but rate storage needs a wider database/API path before an optimizer uses it.
- A restored wmediumd SNR may not appear as a new RCPI until a frame traverses
  the link. Generate traffic before evaluating restored signal state.
