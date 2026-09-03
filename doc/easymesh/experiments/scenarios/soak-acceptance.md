# Duration-bound churn acceptance

## Purpose

The long soak is a requirements-driven characterization of the supported
bare-metal and LXD-VM execution models. It is not a passive uptime check. Each
run alternates controlled RF churn with complete health, traffic,
state-restoration and memory gates. A one-hour run of every scale profile is
the campaign qualification gate. A 12-hour profile remains the long-duration
acceptance unit; the one-hour qualification is not labeled as long-duration
acceptance.

The executable definition is `gen/tests/p0-churn-soak.py`. Every sample and
workload writes machine-readable evidence on the target running the lab.

## Acceptance requirements

Every preflight, post-workload and final gate must satisfy all of these:

| Area | Requirement |
| --- | --- |
| topology API | 6 rendered nodes, 5 edges and the profile's exact unique WLAN-client count; current small is 20 |
| SSID cohorts | topology counts exactly match provisioned metadata; current small is 10 `private_ssid` plus 10 `iot_ssid` |
| controller model | 5 devices, 15 radios, 50 BSS records and `clients + 4` associated records; current small is 24 |
| association truth | every physical client link agrees with controller/API ownership |
| traffic | every client completes three pings to `10.0.0.1` with zero loss |
| processes | every monitored unit remains active with the same main PID and zero additional restarts; transient child commands in the unit cgroup are recorded but are not daemon restarts |
| medium | same wmediumd instance; pair matrix and sparse frequency overrides restore byte-equivalently |
| candidate RCPI | a standard query at controlled 25 dB SNR returns RCPI 88 through the read-only hwsim provider, then restores the exact override state |
| logs | controller journal remains at or below 24 MiB |
| memory | `em_ctrl` RSS <= 256 MiB and `em_cli` RSS <= 192 MiB |
| growth | hour-1 to hour-12 PSS growth <= 64 MiB for each of `em_ctrl` and `em_cli` |
| failures | no new OOM record or coredump in any BPI container |

The additional four associated rows are the extender backhaul stations. The
rendered node count of six includes the network root plus the five EasyMesh
devices.

## Workload

Carousel workloads alternate between the complete private and IoT cohorts,
moving ten clients at a time through changing RF preferences. Every third
workload is a full RF isolation/recovery of an extender. Each scenario must
restore its medium in a `finally` path before the next health gate. The
candidate-RCPI check also uses a temporary frequency-qualified override and
proves that the sparse override set is identical before and after the query.

Extender recovery has two separate bounds: clients and controller ownership
must regain agreement within 120 seconds, and that agreement must then remain
continuous for 75 seconds. The stability interval is not subtracted from the
recovery allowance. Traffic probes use a bounded fan-out of four. Larger
simultaneous `lxc exec` bursts can cause LXD to terminate the transports before
their pings execute, which is not WLAN packet loss. Read-only probes retry only
signal-derived transport statuses (negative signal status or `128 + signal`);
ordinary command and ping failures retain their original status and fail the
gate.

The soak therefore exercises onboarding state, steering, association
reconciliation, extender liveness/aging, return onboarding, the candidate
measurement transaction, UI APIs, client traffic and long-term controller/CLI
memory behavior.

## Run and monitor

The portable lab has an outer LXD VM and nested lab containers. Enter the VM as
root before starting a soak; substitute the actual instance name:

```sh
VM=rdkeasymesh-20-0902
lxc exec "$VM" -- bash

cd /home/easymesh/git/meta-cmf-bananapi-vcpe
gen/tests/health-audit.sh
```

The first two commands run on the outer host. The remaining commands in this
document run inside the VM. Root is required because the snap-packaged nested
LXD client cannot reliably be invoked by a non-root systemd transient unit.

Before a duration campaign, run one bounded shakedown. This proves the complete
harness and one outage workload but is not duration acceptance:

```sh
gen/tests/p0-churn-soak.py \
  --duration 900 \
  --max-workloads 1 \
  --sample-interval 30 \
  --settle 5 \
  --workload outage \
  --expected-clients 20 \
  --output-root /var/tmp/easymesh-soak-shakedown
```

Create a writable evidence namespace and start one persistent transient
systemd unit per target:

```sh
SOAK_ID=current
SOAK_OUTPUT=/var/tmp/easymesh-soak/$SOAK_ID
SOAK_REPO=/home/easymesh/git/meta-cmf-bananapi-vcpe

install -d -o root -g root -m 0755 "$SOAK_OUTPUT"
systemd-run \
  --unit="easymesh-soak-$SOAK_ID" \
  --description="EasyMesh 12-hour RF churn acceptance $SOAK_ID" \
  --uid=root \
  --property="WorkingDirectory=$SOAK_REPO" \
  --setenv="EASYMESH_REPO=$SOAK_REPO" \
  /usr/bin/python3 "$SOAK_REPO/gen/tests/p0-churn-soak.py" \
    --duration 43200 \
    --sample-interval 60 \
    --settle 30 \
    --workload alternating \
    --outage-every 3 \
    --output-root "$SOAK_OUTPUT"

systemctl status "easymesh-soak-$SOAK_ID.service"
journalctl -fu "easymesh-soak-$SOAK_ID.service"
```

For foreground diagnosis, the underlying command is:

```sh
/usr/bin/python3 /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/tests/p0-churn-soak.py \
  --duration 43200 \
  --sample-interval 60 \
  --settle 30 \
  --workload alternating \
  --outage-every 3 \
  --output-root /var/tmp/easymesh-soak
```

Do not claim acceptance from a running unit. A run passes only when its final
`summary.json` says `outcome: passed` and `growth.acceptance_eligible: true`.
An interrupted run remains useful diagnostic evidence but is not acceptance.

## 20/50/100-client campaign

`gen/tests/scale-soak-campaign.sh` owns the complete sequence. It stops the
lab, selects the required 32-, 64-, or 128-radio pool, provisions the exact
client cohort, proves a clean reconstruction, runs the duration-bound soak,
and records every transition.

This campaign mutates the radio pool and client inventory. It is an engineering
host workflow and must not be run inside a profile-locked distributable
appliance. For portable use, import one independent VM for each 20-, 50-, or
100-client profile and run the single-profile soak above in each VM, changing
`--expected-clients` to the locked profile count. On a dedicated mutable
engineering host, set `ENGINEERING_REPO` to that checkout and qualify the
complete sequence with one hour per profile before starting the extended
campaign:

```sh
ENGINEERING_REPO=/path/to/meta-cmf-bananapi-vcpe
systemd-run \
  --unit=easymesh-scale-soak \
  --collect \
  --property=Type=exec \
  /usr/bin/env EASYMESH_SOAK_PROFILE_SECONDS=3600 \
  "$ENGINEERING_REPO/gen/tests/scale-soak-campaign.sh"
```

Only after all three one-hour summaries pass, run the 12-hour-per-profile,
36-hour long-duration campaign:

```sh
systemd-run \
  --unit=easymesh-scale-soak \
  --collect \
  --property=Type=exec \
  /usr/bin/env EASYMESH_SOAK_PROFILE_SECONDS=43200 \
  "$ENGINEERING_REPO/gen/tests/scale-soak-campaign.sh"

systemctl status easymesh-scale-soak.service
journalctl -fu easymesh-scale-soak.service
```

Evidence is written below the runner's configured evidence root. The `small`,
`medium`, and `stress` directories correspond to 20, 50, and 100 clients.
The runner attempts every requested profile even when an earlier profile
fails, then returns a failing campaign result with all failed profiles named.
Each profile must produce a passing `summary.json`; starting the campaign is
not itself an acceptance result.

## Candidate measurement boundary

The optimizer still never reads wmediumd. The test writes one stimulus through
the configurator socket; the BPI HAL independently reads a separately mounted,
read-only metrics socket and presents the result through OneWifi and the
standard EasyMesh Unassociated STA Link Metrics transaction. API responses are
marked `simulated: true` and `provider: hwsim-wmediumd-read-only` so lab radio
truth cannot be mistaken for a physical off-channel scan.
