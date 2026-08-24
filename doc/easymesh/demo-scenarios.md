# rev130 demonstration runbook

## What this demonstrates

This runbook starts with the accepted, fully loaded rev130 lab and presents four
short demonstrations that are visible in both a terminal and the WebUI:

1. a named, manually commanded EasyMesh steer;
2. live RCPI changes driven by a reversible wmediumd scenario;
3. either ten-client cohort rotating around all five APs; and
4. complete RF loss and recovery of one extender.

A final procedure brings the entire Wi-Fi lab down and reconstructs it without
deleting device identities. Do not run two RF scenarios at once: each is a
writer to the same wmediumd control socket. All clean test exits restore the
medium they captured.

Run steering, RF scenarios, audits, and Docker commands as the `rev` user. The
lab grants that user access through the LXD, Docker, and wmediumd control-socket
groups. `sudo` is reserved for the complete lifecycle command because that
runtime changes host networking, services, and container ownership state.

These demonstrations show mechanisms and observability. The manual steer is a
real EasyMesh Client Steering Request and 802.11v BTM exchange, but no current
demo proves an autonomous optimizer or a novel steering policy.

## Prepare the room

SSH to rev130 and use the canonical checkout:

```sh
ssh rev130
cd /home/rev/easymesh-lab/0824-clean/meta-cmf-bananapi-vcpe
```

Open the WebUI from the lab LAN and select **Network Topology**:

```text
http://192.168.2.130:8888
```

The page refreshes live topology every two seconds. Click **Optimize Layout**
once if a tidier starting arrangement is useful. It changes only the drawing.

Run the preflight before an audience arrives:

```sh
mkdir -p tmp/test-results/demo
gen/tests/health-audit.sh | tee tmp/test-results/demo/preflight.txt
```

The required starting state is:

```text
controller model       5 devices / 15 radios / 50 BSSs
associated STA rows    24 (20 clients + 4 wireless backhauls)
WebUI/API clients      20 unique STA MACs (10 private + 10 IoT)
WebUI mesh nodes       6 (Controller, Agent-1, Extender-1..4)
service restarts       zero for every monitored service
traffic                all 20 clients reach 10.0.0.1
```

The RCPI demonstration has one additional policy gate. Confirm that the chosen
client has a non-zero, recently updated sample before the audience arrives:

```sh
curl -fsS http://127.0.0.1:8888/api/v1/clients \
  | jq -r '.clients[] | select(.mac == "02:00:00:00:03:00")
           | [.client_metrics.rcpi, .client_metrics.rssi_dbm,
              .client_metrics.last_updated] | @tsv'
```

Expected output resembles `138  -41  TIMESTAMP`. A zero RCPI or year-0001
timestamp means the per-radio metrics policy is not active; skip Demo 2 and
repair policy delivery before the demo. It is not a wmediumd failure.

If any gate fails, do not conceal it with an ad-hoc process restart. Use the
full reconstruction procedure at the end of this document and rerun preflight.

## Demo 1: manually steer a named client

### Story

The operator identifies the same friendly names visible in the graph and asks
the controller to steer one client to another AP. The host adapter resolves the
live names to a station MAC and a current target BSSID, then calls the existing
controller-side `steer.sh`. The station receives a BTM Request, reassociates,
and the controller and WebUI learn its new parent.

`Agent-1` is the colocated radio agent inside `bpibroadband`. `Controller` is a
control-plane node with no WLAN BSS and is therefore not a steering target.

### Operator actions

First show where `STA-03` is currently placed:

```sh
sta=02:00:00:00:03:00
curl -fsS http://127.0.0.1:8888/api/v1/topology \
  | jq -r --arg sta "$sta" \
      '.nodes[] | select(any(.STAList[]?; .staMAC == $sta)) | .name'
```

Choose a different target visible in the graph. For example, use
`extender-2`; if the client is already there, use `agent-1`:

```sh
gen/steer.sh --dry-run sta-03 extender-2
gen/steer.sh sta-03 extender-2
```

The dry run is useful during narration: it prints the resolved STA MAC, target
BSSID, SSID and band without sending anything. By default the adapter keeps the
client on its current SSID and band. A deliberate band change is explicit:

```sh
gen/steer.sh --band 6 sta-03 extender-2
```

After the command, independently inspect the real station and controller API:

```sh
lxc exec wlan-client -- iw dev wlan0 link
curl -fsS http://127.0.0.1:8888/api/v1/topology \
  | jq -r --arg sta "$sta" \
      '.nodes[] | select(any(.STAList[]?; .staMAC == $sta))
       | [.name, .id] | @tsv'
```

### What to point out

The dry run prints the resolved transaction, and the real command must return
zero. The `iw` output must show the resolved target BSSID, and the API must
report the corresponding target node. In the WebUI, the `STA-03` phone moves
to that node without a page reload. Command success alone is not the pass
condition; all three views must agree.

## Demo 2: watch live RCPI change

### Story

wmediumd changes the bidirectional SNR of the client's current serving link
between 45 and 25 dB six times. The client remains active and sends traffic, so
hwsim supplies fresh signal values, agents report metrics, and the controller's
client API and WebUI show the changing RCPI/RSSI. This demonstrates the
observation path an external optimizer can consume.

### Operator actions

Open **Connected Clients**, find the row for `02:00:00:00:03:00`, and then run:

```sh
cd gen/wmediumd/configurator
./run-rcpi-monitor.sh wlan-client
cd ../../..
```

The scenario takes about 130 seconds. The terminal prints a sample every two
seconds with time, client MAC, serving BSSID, RCPI and RSSI.

### What to point out

The WebUI **Signal** value refreshes every two seconds and follows the high/low
phases printed in the terminal. The serving BSSID should remain stable; this is
a metrics demonstration, not an autonomous-roam claim. The runner verifies
every control-socket update and restores the exact captured link value.

## Demo 3: client carousel in Network Topology

### Story

Five pairs from one SSID cohort move around `Agent-1` and the four extenders.
Every move has a visible blackout followed by deterministic arrival at the
next AP. This is the clearest visual demonstration of live association
notifications and controller/WebUI convergence at scale.

### Operator actions

Return to **Network Topology** and run one complete rotation:

```sh
gen/tests/wmediumd-client-carousel.py --ssid private_ssid --rounds 1
```

Repeat with `--ssid iot_ssid` to move the ten IoT-icon clients independently.

The terminal announces each group with the same labels shown in the WebUI:

```text
BLACKOUT ... STA-03,STA-04 Agent-1 -> DISCONNECTED
ARRIVAL  ... STA-03,STA-04 DISCONNECTED -> Extender-1
```

For an open-ended display, use `--rounds 0` and press `Ctrl-C` once when done.
The handler stops at a phase boundary, returns clients to their captured APs
and restores every touched SNR pair.

### What to point out

After each `ARRIVAL`, the named phones jump to the AP announced in the terminal
and the script advances only after the real `iw` link and API parent agree. A
phone may remain drawn under its last-known AP during the four-second blackout:
the current controller retains last-known placement until a new association is
reported. The real disconnect is recorded by the test; the visual acceptance
signal is the deterministic parent change at arrival.

Evidence is written below `/tmp/wmediumd-client-carousel/`. A successful run
ends with `PASS`, verified medium restoration and restored original placement.

## Demo 4: make an extender disappear and return

### Story

This test first removes only the selected extender/client RF paths and proves
that affected clients choose other APs. It then isolates every RF path to the
extender. The wireless backhaul drops, normal IEEE 1905 liveness expires, the
controller removes the unreachable node from active topology, and the WebUI
automatically redraws. Restoring the exact medium brings back the same logical
extender without restarting its container or controller processes.

### Operator actions

Keep **Network Topology** open and run:

```sh
gen/tests/wmediumd-extender-outage.py --extender bpiap-003
```

`bpiap-003` is the node labelled `Extender-4` in the current five-AP lab.
Allow roughly three minutes. The main visual sequence is:

```text
affected phones move away
  -> one extender ages out after about 60 seconds
  -> medium is restored
  -> the same extender returns and clients/controller reconverge
```

The exact elapsed times and affected clients are written as JSON events. The
terminal ends with the evidence path:

```text
PASS artifacts=/tmp/wmediumd-extender-outage/TIMESTAMP-bpiap-003
```

### What to point out

The test never stops `bpiap-003`; loss is entirely through wmediumd's live
control socket. The API node count falls from six to five and returns to six,
while client traffic continues through other APs. A pass also requires exact
medium readback/restoration, stable controller PIDs and restart counts, 20/20
traffic, and 75 seconds of physical/API placement agreement after recovery.

## Bring the complete rev130 Wi-Fi lab down and back up

### Scope and safety

This is an identity-preserving reconstruction, not a fresh deployment. It
stops wmediumd, all 20 clients, all four extenders and `bpibroadband`; the
optional command also stops the two Boardfarm WAN/DHCP provider containers.
It does not delete LXD instances, profiles, `/nvram`, databases, Docker
networks or images. Do not use `bpi.sh -F` for this demonstration because `-F`
intentionally creates new logical device identities.

### Bring it down

```sh
cd /home/rev/easymesh-lab/0824-clean/meta-cmf-bananapi-vcpe
demo_runtime=gen/vm/scripts/guest/easymesh-lab-runtime

sudo env \
  EASYMESH_LAB_USER=rev \
  EASYMESH_LAB_HOME=/home/rev \
  EASYMESH_GEN="$PWD/gen" \
  EASYMESH_ACCEPTANCE_STATE="$PWD/tmp/test-results/demo-reconstruction" \
  bash "$demo_runtime" stop

# Optional: include the Boardfarm CPE-5 WAN and DHCP providers in the outage.
docker stop dhcp-cpe5 wan-cpe5
```

Check the stopped state:

```sh
lxc list -c ns --format table
gen/wmediumd/wmediumd-up.sh status || true
docker ps --format '{{.Names}}' | grep -E '^(dhcp|wan)-cpe5$' || true
```

All managed LXD instances should be `STOPPED`, wmediumd should be down, and the
last command should be empty only if the optional Boardfarm stop was used. The
WebUI is unavailable while `bpibroadband` is stopped.

### Bring it up

Use the same runtime command with `start`; it starts the named Boardfarm
providers if necessary and enforces controller, extender, client and medium
ordering. Allow roughly 10 minutes, including its two-minute stability window:

```sh
mkdir -p tmp/test-results/demo-reconstruction
sudo env \
  EASYMESH_LAB_USER=rev \
  EASYMESH_LAB_HOME=/home/rev \
  EASYMESH_GEN="$PWD/gen" \
  EASYMESH_ACCEPTANCE_STATE="$PWD/tmp/test-results/demo-reconstruction" \
  bash "$demo_runtime" start \
  | tee tmp/test-results/demo-reconstruction/latest-start.txt
```

This is intentionally not a fast parallel start. It waits for the WAN provider,
controller tri-band state, each extender's complete onboarding, all 20 clients,
the `5/15/50/24` model, a two-minute stability window, zero service restarts and
20/20 traffic. On success it prints:

```text
EasyMesh cold-boot reconstruction PASS: model=5/15/50 clients=20/20 metrics=20/20 associated=24 restarts=0
```

Run the independent audit and reopen the WebUI:

```sh
mkdir -p tmp/test-results/demo
gen/tests/health-audit.sh | tee tmp/test-results/demo/post-reconstruction.txt
```

The reconstructed graph must contain the same six mesh nodes and ten named
clients. The AP BSSIDs and device identities are preserved because this is a
warm reconstruction of existing containers. Use the fresh-build/deployment
procedure in [lab-setup.md](lab-setup.md) only when new images or new logical
identities are required.

## Recovery if a demo is interrupted incorrectly

The carousel handles one `Ctrl-C`, and the other runners restore the medium in
their normal error paths. If a terminal or host is killed before cleanup can
run, stop all experiments and restore the known all-strong baseline once:

```sh
cd /home/rev/easymesh-lab/0824-clean/meta-cmf-bananapi-vcpe
SNR=40 gen/wmediumd/wmediumd-up.sh up
gen/tests/health-audit.sh
```

This recovery restarts wmediumd, so it is not part of a successful demo. Do not
restart EasyMesh or OneWifi merely to hide a failed convergence gate; preserve
the scenario evidence and logs for diagnosis.
