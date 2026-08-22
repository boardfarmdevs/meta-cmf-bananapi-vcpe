# Long-duration acceptance

## Purpose

The long soak is a 12-hour, requirements-driven characterization of the same
small lab on rev130, the rev120 VM and the rev150 VM. It is not a passive
uptime check. Each run alternates controlled RF churn with complete health,
traffic, state-restoration and memory gates.

The executable definition is `gen/tests/p0-churn-soak.py`. Every sample and
workload writes machine-readable evidence under `/var/tmp/easymesh-soak` on
the target running the lab.

## Acceptance requirements

Every preflight, post-workload and final gate must satisfy all of these:

| Area | Requirement |
| --- | --- |
| topology API | 6 rendered nodes, 5 edges and 10 unique WLAN clients |
| controller model | 5 devices, 15 radios, 50 BSS records and 14 associated records |
| association truth | all 10 physical client links agree with controller/API ownership |
| traffic | all 10 clients complete three pings to `10.0.0.1` with zero loss |
| processes | every monitored unit remains active with the same main PID and zero additional restarts; transient child commands in the unit cgroup are recorded but are not daemon restarts |
| medium | same wmediumd instance; pair matrix and sparse frequency overrides restore byte-equivalently |
| candidate RCPI | a standard query at controlled 25 dB SNR returns RCPI 88 through the read-only hwsim provider, then restores the exact override state |
| logs | controller journal remains at or below 24 MiB |
| memory | `em_ctrl` RSS <= 256 MiB and `em_cli` RSS <= 192 MiB |
| growth | hour-1 to hour-12 PSS growth <= 64 MiB for each of `em_ctrl` and `em_cli` |
| failures | no new OOM record or coredump in any BPI container |

The model count of 14 is intentional: ten fronthaul WLAN clients plus four
extender backhaul stations. The rendered node count of six includes the
network root plus the five EasyMesh devices.

## Workload

One carousel moves all ten WLAN clients through changing RF preferences. Every
third workload is a full RF isolation/recovery of an extender. Each scenario
must restore its medium in a `finally` path before the next health gate. The
candidate-RCPI check also uses a temporary frequency-qualified override and
proves that the sparse override set is identical before and after the query.

Extender recovery has two separate bounds: clients and controller ownership
must regain agreement within 120 seconds, and that agreement must then remain
continuous for 75 seconds. The stability interval is not subtracted from the
recovery allowance. Traffic probes are deliberately sequential. Running ten
simultaneous `lxc exec` scopes can cause LXD to terminate the transports before
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
SOAK_ID=0822
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

## 0822 campaign status

The first three-target attempt was diagnostically useful but is not an
acceptance result. It exposed three harness-boundary defects: exact cgroup PID
membership rejected legitimate OneWifi helper children, recovery and the
75-second stability window shared one undersized timeout, and VM LXD transport
terminations were sometimes reported as status 143 and misclassified as WLAN
traffic failure. Focused reruns proved exact medium restore, continuous client
ownership, 10/10 traffic and unchanged controller services after correcting
those boundaries.

The first corrected rerun under `easymesh-soak-0822-final.service` was stopped
deliberately after rev120 exposed one remaining VM transport boundary while
restoring an idempotent client link-up. Rev130 and rev150 were interrupted only
after their active workloads restored the medium. Those evidence roots remain
diagnostic records and are not acceptance results:

- rev130: `/var/tmp/easymesh-soak/0822-final/20260822T162313Z-p0-churn-soak`;
- rev150 VM: `/var/tmp/easymesh-soak/0822-final/20260822T162314Z-p0-churn-soak`;
- rev120 VM: `/var/tmp/easymesh-soak/0822-final/20260822T162315Z-p0-churn-soak`.

The link-state restore now retries only signal-derived LXD transport loss; a
real link command failure remains a hard failure. A focused rev120 carousel
then passed with both `placement_restored: true` and `medium_restored: true`.

The authoritative byte-identical rerun started from zero on 2026-08-22 at
commit `2a15c95` under `easymesh-soak-0822-final2.service`. Its evidence roots
are:

- rev130: `/var/tmp/easymesh-soak/0822-final2/20260822T163423Z-p0-churn-soak`;
- rev120 VM: `/var/tmp/easymesh-soak/0822-final2/20260822T163425Z-p0-churn-soak`;
- rev150 VM: `/var/tmp/easymesh-soak/0822-final2/20260822T163425Z-p0-churn-soak`.

All three passed preflight with the complete `5/15/50/14` model, ten clients,
10/10 physical/API ownership agreement, 10/10 traffic, a successful candidate
RCPI transaction, exact starting-medium fingerprints and no service errors.
They are running, not passed, until each final summary closes every acceptance
gate.

## Candidate measurement boundary

The optimizer still never reads wmediumd. The test writes one stimulus through
the configurator socket; the BPI HAL independently reads a separately mounted,
read-only metrics socket and presents the result through OneWifi and the
standard EasyMesh Unassociated STA Link Metrics transaction. API responses are
marked `simulated: true` and `provider: hwsim-wmediumd-read-only` so lab radio
truth cannot be mistaken for a physical off-channel scan.
