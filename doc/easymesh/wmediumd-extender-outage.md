# Extender RF-outage and live-topology test

## Purpose

This test makes an extender unreachable by changing wmediumd's live SNR matrix.
It does not stop an LXD container, restart OneWifi, or synthesize a client link
event. It answers three separate questions:

1. Do clients naturally detect RF loss and associate with another AP?
2. Do the controller API and WebUI move those clients to the correct parent?
3. Does complete RF isolation remove the extender from controller topology, and
   does its backhaul recover after the medium is restored?

The distinction matters. Client-only RF loss is a steering and roaming test.
Complete isolation is an agent-liveness and topology-aging test.

## Medium and topology flow

```text
                     Unix SOCK_SEQPACKET
test or configurator ------------------------------+
       APPLY generation / readback / restore       |
                                                   v
client hwsim <-------- SNR matrix -----------> wmediumd
     |                                             ^
     | beacons, data and link-loss                 |
     v                                             |
wpa_supplicant -> reassociation -> OneWifi agent --+
                                      |
                                      | association notification
                                      v
                              EasyMesh controller
                                      |
                                      v
                         /api/v1/topology (live data)
                                      |
                               two-second polling
                                      v
                                WebUI topology
```

The control socket is `/run/wmediumd-control.sock`. `APPLY` replaces all
specified directed pairs as one generation. The test reads the generation back
and restores every touched pair in a `finally` path. The wmediumd PID is not
changed.

## Dedicated acceptance test

Run this inside the VM after the normal lab health check:

```sh
cd /home/vagrant/git/meta-cmf-bananapi-vcpe
sudo gen/tests/wmediumd-extender-outage.py --extender bpiap-003
```

The test discovers the active hwsim transmitter identities and the extender's
private BSSIDs; no MAC address is hard-coded. If the selected extender owns no
client, the test first uses one temporary atomic RF generation to place a
client there, requires the physical and API owners to agree, and restores the
original matrix before starting the measured outage.

The sequence is:

```text
preflight
  -> find every client currently associated with the selected extender
  -> capture all touched directed links from the control socket

client RF outage
  -> atomically set client <-> selected-extender pairs to -20 dB
  -> require each affected client to select a different BSSID
  -> require actual iw link and /api/v1/topology parent to agree

complete extender RF outage
  -> atomically isolate the extender from every other active hwsim radio
  -> require the wireless backhaul to report Not connected
  -> observe whether the extender node ages out of /api/v1/topology

restore
  -> atomically restore captured values and verify every readback
  -> require the extender backhaul and topology presence to recover
```

Useful options are:

```text
--skip-full-outage       run only the client movement test
--outage-snr -20         unreachable link value
--prepare-snr 55         temporary advantage when the extender owns no client
--prepare-timeout 90     preconditioning convergence deadline
--client-timeout 120     client/API convergence deadline
--node-timeout 90        controller aging observation interval
--recovery-timeout 150   restored-backhaul deadline
--output-root PATH       JSON evidence directory
```

Each run writes the frozen inventory, topology before and after, an event JSONL
stream, and `summary.json` under a timestamped directory.

## Configurator version

The existing configurator can run the client-only experiment because it changes
station/fronthaul pairs and protects backhaul:

```sh
cd gen/wmediumd/configurator
python3 -m wmdcfg.cli inventory -o /tmp/inventory.json
python3 -m wmdcfg.cli compile scenarios/client-extender-outage.wmd \
    --inventory /tmp/inventory.json \
    --bind client=wlan-client-005 \
    --bind source_ap=bpiap-003 \
    --bind recovery_ap=bpiap-002 \
    -o /tmp/client-extender-outage.plan.json
sudo python3 -m wmdcfg.cli run /tmp/client-extender-outage.plan.json \
    --output-root /tmp/wmdcfg-runs
```

`source_ap` must be the client's current AP at preflight. The destination is not
selected by EasyMesh during autonomous recovery; the supplicant selects from
the RF candidates. Give `recovery_ap` a clear advantage and verify the observed
BSSID. Configurator language v1 deliberately cannot isolate mesh backhaul, so
the dedicated acceptance test uses `ControlClient` directly for that phase.

## Verified behavior

Live rev120 VM runs on 2026-08-17 produced:

| Run | Result |
| --- | --- |
| `bpiap-003`, client-only | 2/2 clients moved; actual and API parents agreed in 6.6 s |
| `bpiap-001`, complete | 2/2 clients moved in 6.7 s; node retained for 90 s; restored backhaul in 16.2 s |
| `bpiap-002`, complete | 2/2 clients moved in 10.7 s; backhaul lost in 1.4 s; node retained for 60 s; restored in 17.5 s |
| `bpiap-003`, browser observed | 3/3 clients moved in 11.0 s; 15 polls saw 3 topology states without reload |

The client-side experiment works as intended: dropped beacons cause natural
link loss, clients reassociate, and the controller publishes the new parent.
No `ip link` toggle is necessary.

Those runs established the original controller limitation; they are retained
as boundary evidence rather than the current result. The end-to-end liveness
path was completed and tested on rev130 on 2026-08-19. A full `bpiap-003` RF
outage produced:

| Observation | Result |
| --- | --- |
| affected client selected another AP | 5.464 s; physical and API parents agreed |
| extender wireless backhaul loss | 2.011 s |
| extender removed from active API/WebUI topology | 59.181 s after full isolation |
| exact 210-link medium restoration | verified through control-socket readback |
| same extender returned to active topology | 15.198 s after restoration |
| all ten physical/API client parents | agreed continuously for 75 s |
| client traffic and controller processes | 10/10 pass; same PIDs and zero restarts |

The device identity and database records remain persistent while the node is
unreachable. Only its active topology publication is suppressed. A returning
AL-MAC is therefore the same logical extender rather than a newly provisioned
device.

## Root localization in the current stack

The behavior spans two implementation boundaries; it is not a WebUI timer and
not a direct administrative `RemoveDevice` operation.

The built `ieee1905-em` v0.6 source at commit
`9eb6127c05250f0174a113688d7e577e1af35732` already:

- transmits Topology Discovery every 30 seconds;
- timestamps topology nodes with monotonic `last_seen` state;
- runs topology garbage collection every five seconds; and
- removes a node from its private topology map after 60 seconds without an
  update.

The completed chain is:

1. IEEE 1905 refreshes `last_seen` only from received remote evidence. Local
   query/response/notification state no longer keeps an isolated neighbor
   alive.
2. Garbage collection publishes a typed `NeighborExpired` event after 60
   seconds and sends the normal multicast Topology Notification.
3. Because the local IEEE 1905 transmitter does not receive its own multicast,
   it also delivers the same standard notification through its normal AL-SAP
   indication. Endpoint metadata identifies the changed neighbor; no private
   TLV is placed on the network.
4. Unified Wi-Fi Mesh starts one bounded standard Topology Query probe. If the
   agent does not answer within ten seconds, controller-owned reachability is
   false and the device is omitted from active topology without deleting
   runtime or MariaDB identity.
5. IEEE 1905 publishes `NeighborAdded` when received evidence recreates a
   neighbor. Any valid returning EasyMesh frame clears the probe, restores
   reachability, and republishes the same logical device.
6. Periodic Topology Responses repair association placement through the
   standard Associated Clients TLV. An ambiguous old-AP snapshot cannot
   overwrite a newer association notification, preventing a recovered
   extender from replaying a stale client owner.

A WebUI-only filter or direct call to `RemoveDevice` would bypass this
controller contract and is intentionally not used.

### IEEE 1905 publication acceptance

A targeted rev130 run on 2026-08-19 isolated every directed wmediumd pair for
`bpiap-003` while capturing inside the controller network namespace. The exact
baseline matrix was restored and verified through the control socket. The
relevant sequence was:

```text
14:54:49.667  remove expired neighbor 02:00:00:00:04:20 (61.9 s)
14:54:49.668  publish NeighborExpired and invoke normal notification worker
14:54:49.670  Topology Notification sent on eth0_virt_peer, message ID 132
```

The packet capture independently decoded frame 92 as message type `0x0001`,
source `00:60:2f:da:68:d4`, destination `01:80:c2:00:00:13`, message ID
`0x0084`. That capture proved the IEEE 1905 publication boundary. The later
full-path run above separately proved controller suppression and restoration:
the node count changed from six to five after 59.181 seconds and returned to
six 15.198 seconds after exact RF restoration.

## Automatic WebUI refresh

Patch `0038-cli-refresh-topology-on-live-change.patch` changes the visible
topology tab from a 60-second refresh to a two-second poll. It:

- permits only one request at a time;
- compares network data while ignoring D3 presentation coordinates;
- redraws only when the topology has actually changed;
- retains cached node positions and an optimized manual layout; and
- cache-busts the JavaScript asset.

The browser acceptance test wrapped the real topology fetch, ran a live
wmediumd outage, and recorded 15 responses with three distinct association
snapshots. The SVG retained six mesh nodes and the browser navigation count
remained one, proving that the visual update occurred without a page reload.

The page must be loaded once after installing the new image so the browser
receives the cache-busted asset. Subsequent association changes are automatic.
