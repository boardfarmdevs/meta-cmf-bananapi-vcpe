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

Choose an extender that currently owns at least one client. The test discovers
the active hwsim transmitter identities and the extender's private BSSIDs; no
MAC address is hard-coded.

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

The complete-isolation experiment establishes a current implementation limit:
the controller retains the known extender, radios, and BSSs after its wireless
backhaul is genuinely disconnected. The WebUI therefore cannot truthfully make
the extender disappear. It has no reliable device-liveness/aging value to use.
The node's presence means *known to the controller*, not *currently reachable*.
Restoration reconnects the real backhaul; it does not represent a visible node
being newly created.

Do not hide the node using LXD state, wmediumd truth, or browser timers. Those
are lab-only facts and would make the WebUI claim behavior that the EasyMesh
controller has not reported. Extender disappearance requires a separate
controller liveness/aging design and should be tested independently.

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
