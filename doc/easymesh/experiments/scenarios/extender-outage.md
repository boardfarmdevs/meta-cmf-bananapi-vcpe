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

From the outer host, enter the appliance VM as root, then run the test after the
normal lab health check. Substitute the actual VM name when necessary:

```sh
VM=rdkeasymesh-20-0902
lxc exec "$VM" -- bash

cd /home/easymesh/git/meta-cmf-bananapi-vcpe
gen/tests/health-audit.sh
gen/tests/wmediumd-extender-outage.py --extender bpiap-003
gen/tests/health-audit.sh
```

The first two commands run on the outer host; the commands after the blank line
run inside the VM. Root is required for nested LXD inspection. The LXD suffix
does not determine the WebUI `Extender-N` label; preflight prints the persistent
node identity and impacted clients.

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

client=wlan-client-005
bssid=$(jq -r --arg c "$client" \
  '.radios[] | select(.container == $c) | .associated_bssid' \
  /tmp/inventory.json)
source_ap=$(jq -r --arg b "$bssid" \
  '.radios[] | select(.kind == "mesh")
   | select(any(.interfaces[]; (.mac | ascii_downcase) ==
       ($b | ascii_downcase))) | .container' \
  /tmp/inventory.json | head -1)
recovery_ap=$(jq -r --arg source "$source_ap" \
  '.radios[] | select(.kind == "mesh" and .container != $source)
   | .container' /tmp/inventory.json | head -1)

printf 'client=%s source=%s recovery=%s\n' \
  "$client" "$source_ap" "$recovery_ap"
python3 -m wmdcfg.cli compile scenarios/client-extender-outage.wmd \
    --inventory /tmp/inventory.json \
    --bind client="$client" \
    --bind source_ap="$source_ap" \
    --bind recovery_ap="$recovery_ap" \
    -o /tmp/client-extender-outage.plan.json
python3 -m wmdcfg.cli run /tmp/client-extender-outage.plan.json \
    --output-root /tmp/wmdcfg-runs
```

`source_ap` must be the client's current AP at preflight, which is why the
example discovers it instead of hard-coding a container. The destination is
not selected by EasyMesh during autonomous recovery; the supplicant selects
from the RF candidates. Give `recovery_ap` a clear advantage and verify the
observed BSSID. Configurator language v1 deliberately cannot isolate mesh
backhaul, so the dedicated acceptance test uses `ControlClient` directly for
that phase.

## Required behavior

Dropped beacons must cause natural client link loss and reassociation without
an `ip link` toggle. The physical station link and controller parent must agree.
After complete isolation, the extender must lose backhaul and age out of active
topology while its persistent identity remains intact. Exact matrix restoration
must return the same logical extender, restore client traffic, and leave
controller services at the original PID and restart count.

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

## Automatic WebUI refresh

The visible topology tab polls every two seconds. It:

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
