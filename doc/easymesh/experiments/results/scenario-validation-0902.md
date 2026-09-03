# 0902 LXD-appliance scenario validation

## Scope

This record captures an operator-level validation of the 20-client RDK
EasyMesh appliance on `rev150`. The outer instance was
`rdkeasymesh-20-0902`; it contained 25 nested LXD containers: five mesh nodes
and 20 WLAN clients. The packaged runtime source was `2808942`, with userspace
wmediumd. Validation ran on 2026-09-02 PDT / 2026-09-03 UTC.

The purpose was to execute the published demonstration and scenario commands,
not to claim a new duration acceptance result.

## Results

| Exercise | Result | Observation |
| --- | --- | --- |
| baseline health audit | pass | 5 devices, 15 radios, 50 BSSs, 24 associated rows, 20 unique clients, 4/4 backhaul signals, zero restarts and 20/20 traffic |
| named same-band steer | pass | `STA-03` moved physically and in controller topology to Extender-1 |
| named 2.4 GHz band steer | pass | `STA-03` moved from 5 GHz to Extender-3 channel 6 |
| named 6 GHz band steer | correctly rejected | requested target was absent from the client's live 6135 MHz candidate scan; no BTM request was sent and RF bias was restored |
| RCPI monitor | pass | 130.4-second scenario reported the programmed `-46` through `-62` dBm changes and restored the medium |
| private carousel, first run | pass | all five two-client groups completed one rotation and restored |
| IoT carousel | pass | all five groups completed one rotation and restored; initial deterministic formation took about 39--43 seconds per group |
| extender RF outage | pass | two clients moved, the extender aged out in 59.4 seconds, returned 17.1 seconds after restoration, held 75-second consistency, and retained service PIDs |
| multihop star | pass | 20/20 clients reachable; exact 5/15/50/24 model |
| multihop branch | pass | requested parent tree, forwarding, model and backhaul metrics agreed |
| multihop chain | pass | four-hop chain, forwarding, model and backhaul metrics agreed |
| restore to star | pass | all four extenders returned to the controller backhaul BSSID |
| client profile plans | pass | `small`, `medium` and `stress` plans rendered without mutating the locked appliance profile |
| configurator client-outage plan | pass | current source AP was discovered dynamically; `wlan-client-005` recovered on the selected alternate AP and the plan restored |
| full lab stop | pass | all 25 nested lab containers and wmediumd stopped in 30 seconds; Boardfarm WAN/DHCP remained running by design |
| first full lab start | fail, bounded | after 383 seconds, `bpiap` and `bpiap-003` lacked their 5 GHz fronthaul configuration and the unit rejected the 35-BSS model |
| whole-unit start retry | pass | completed in 467 seconds with 5/15/50/24, metrics 20/20, zero restarts, traffic 20/20 and a 120-second stability window |
| one-workload carousel soak shakedown | fail, restored | 6 GHz-pinned `STA-0E` could not reach Agent-1 within 60 seconds; exact medium and original placement were restored |
| one-workload outage soak shakedown | pass | completed in 246.7 seconds with candidate RCPI 88, exact restoration, zero drops, stable services and clean final health |

## Corrections derived from the run

- Appliance commands run in a root shell inside the outer LXD VM. A non-root
  invocation of the snap-packaged nested `lxc` client failed process tracking,
  even though `easymesh` belonged to the `lxd` group.
- The appliance lifecycle is `systemctl start|stop easymesh-lab.service`; the
  older direct-runtime path and environment block are not an operator command.
- `Extender-N` cannot be inferred from a `bpiap-NNN` suffix. The live AL
  identity and topology API define the label.
- A configurator outage example must discover the client's current source AP;
  a fixed source container becomes wrong after any steer or carousel.
- A scenario `PASSED` result, verified restore and a fresh health audit are all
  required before the next scenario. Rapidly chained RF changes can expose
  stale or missing controller ownership even while physical traffic works.
- Same-band and 2.4 GHz cross-band steering are accepted demonstrations. A
  6 GHz command is conditional on the requested BSSID being scan-visible.
- The IoT carousel is the preferred audience-facing rotation. The private
  carousel is a stronger tri-band test because it includes band-fixed clients
  and may legitimately expose missing target visibility.
- A failed full reconstruction remains failed even when some containers are
  running. Preserve its evidence and retry the entire systemd transaction;
  never repair it with individual OneWifi or EasyMesh restarts during a demo.
- The 20/50/100 scale campaign mutates inventory and belongs on a dedicated
  engineering host. A distributable appliance keeps its import-selected
  profile immutable.

## Evidence locations in the validated VM

The scenario runners wrote their detailed JSON and logs below:

```text
/tmp/wmdcfg-runs/
/tmp/wmediumd-client-carousel/
/tmp/wmediumd-extender-outage/
/tmp/easymesh-soak-shakedown-post-reconstruction/
/tmp/easymesh-soak-outage-shakedown/
/home/easymesh/.local/state/easymesh-lab/reboot-acceptance/
```

These paths are runtime evidence inside the VM and are not durable after the
instance is deleted. The final outage shakedown and its final health gate
passed; the failed runs were retained to avoid converting real limitations
into undocumented retries.
