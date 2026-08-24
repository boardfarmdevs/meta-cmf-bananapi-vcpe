# Duration-bound churn acceptance

## Purpose

The long soak is a requirements-driven characterization of the same small lab
on rev130, the rev120 VM and the rev150 VM. It is not a passive uptime check.
Each run alternates controlled RF churn with complete health, traffic,
state-restoration and memory gates. A 12-hour memory-growth acceptance remains
defined below but is deliberately deferred; shorter shakedowns are not labeled
as long-duration acceptance.

The executable definition is `gen/tests/p0-churn-soak.py`. Every sample and
workload writes machine-readable evidence under `/var/tmp/easymesh-soak` on
the target running the lab.

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

Create a writable evidence namespace and start one persistent transient
systemd unit per target. Run it as the lab account so LXD and the wmediumd
control socket use the same permissions as normal scenarios:

```sh
SOAK_ID=current
SOAK_OUTPUT=/var/tmp/easymesh-soak/$SOAK_ID
SOAK_REPO=/path/to/meta-cmf-bananapi-vcpe

sudo install -d -o "$(id -un)" -g "$(id -gn)" -m 0755 "$SOAK_OUTPUT"
sudo systemd-run \
  --unit="easymesh-soak-$SOAK_ID" \
  --description="EasyMesh 12-hour RF churn acceptance $SOAK_ID" \
  --uid="$(id -un)" \
  --property="WorkingDirectory=$SOAK_REPO" \
  --setenv="EASYMESH_REPO=$SOAK_REPO" \
  /usr/bin/python3 "$SOAK_REPO/gen/tests/p0-churn-soak.py" \
    --duration 43200 \
    --sample-interval 60 \
    --settle 30 \
    --workload alternating \
    --outage-every 3 \
    --output-root "$SOAK_OUTPUT"

sudo systemctl status "easymesh-soak-$SOAK_ID.service"
sudo journalctl -fu "easymesh-soak-$SOAK_ID.service"
```

For foreground diagnosis, the underlying command is:

```sh
sudo /usr/bin/python3 <repo>/gen/tests/p0-churn-soak.py \
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

## Candidate measurement boundary

The optimizer still never reads wmediumd. The test writes one stimulus through
the configurator socket; the BPI HAL independently reads a separately mounted,
read-only metrics socket and presents the result through OneWifi and the
standard EasyMesh Unassociated STA Link Metrics transaction. API responses are
marked `simulated: true` and `provider: hwsim-wmediumd-read-only` so lab radio
truth cannot be mistaken for a physical off-channel scan.
