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
| processes | every monitored unit remains active with the same PID set and zero additional restarts |
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

The soak therefore exercises onboarding state, steering, association
reconciliation, extender liveness/aging, return onboarding, the candidate
measurement transaction, UI APIs, client traffic and long-term controller/CLI
memory behavior.

## Run and monitor

The deployment procedure starts one persistent systemd unit per target:

```sh
sudo systemctl status easymesh-soak.service
sudo journalctl -fu easymesh-soak.service
```

The underlying command is:

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
