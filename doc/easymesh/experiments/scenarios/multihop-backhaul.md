# Multi-hop EasyMesh backhaul

## Purpose

This lab can form deterministic wireless trees in which an extender uses
another extender, rather than Agent-1, as its backhaul parent.  The test proves
four separate things:

1. the requested 802.11 station association exists;
2. the parent owns the corresponding four-address AP/VLAN station;
3. traffic crosses every hop to `10.0.0.1`;
4. the controller and WebUI publish the same parent/child tree.

The checks are intentionally separate.  An `iw` link can be correct while a
stale EasyMesh data model still draws the previous tree.

## Available trees

`bpiap-003` is the anchor.  At least one extender must remain associated with
Agent-1 or the downstream tree has no path to the controller.

Star profile:

```text
             +-- bpiap-003
             +-- bpiap-002
Agent-1 -----+-- bpiap-001
             +-- bpiap
```

Chain profile:

```text
Agent-1
   |
bpiap-003
   |
bpiap-002
   |
bpiap-001
   |
bpiap
```

Branch profile:

```text
             Agent-1
                |
            bpiap-003
             /      \
    bpiap-002      bpiap-001
        |
      bpiap
```

The names above are LXD container names.  The WebUI assigns `Extender-N`
labels from persistent AL identities; it does not use the container suffix.

## Run the test

Run from the repository root on a lab host:

```sh
./gen/tests/multihop-backhaul.sh status
./gen/tests/multihop-backhaul-test.sh --help
MULTIHOP_MIN_CLIENTS=20 ./gen/tests/multihop-backhaul-test.sh star
MULTIHOP_MIN_CLIENTS=20 ./gen/tests/multihop-backhaul-test.sh branch
MULTIHOP_MIN_CLIENTS=20 ./gen/tests/multihop-backhaul-test.sh chain
```

The test wrapper requires an explicit profile; no argument prints its complete
operator help without changing the lab. `test` changes a running lab and
verifies convergence. `cold-test` stops the
extenders and controls their protocol-service start order, so downstream nodes
cannot register directly through Agent-1 before their selected parent exists:

```sh
MULTIHOP_MIN_CLIENTS=20 ./gen/tests/multihop-backhaul.sh cold-test star
MULTIHOP_MIN_CLIENTS=20 ./gen/tests/multihop-backhaul.sh cold-test chain
MULTIHOP_MIN_CLIENTS=20 ./gen/tests/multihop-backhaul.sh cold-test branch
```

Return all extenders to direct gateway backhaul with:

```sh
./gen/tests/multihop-backhaul.sh restore
```

The script discovers every current BSSID.  It does not embed generated hwsim
MAC addresses.  The principal timeouts can be overridden for slow hosts:

```sh
MULTIHOP_LINK_TIMEOUT=120 \
MULTIHOP_PARENT_TIMEOUT=90 \
MULTIHOP_MODEL_TIMEOUT=240 \
MULTIHOP_MIN_CLIENTS=20 \
  ./gen/tests/multihop-backhaul.sh test chain
```

## What the script changes

The 5 GHz mesh station is `Device.WiFi.STA.2` (`wifi1.3`) in the current image.
The script writes its selected BSSID through RBUS:

```text
Device.WiFi.STA.2.Bssid = <parent mesh-backhaul AP BSSID>
```

An extender's 5 GHz backhaul AP is `Device.WiFi.AccessPoint.14`
(`wifi1.1`).  The script applies `ForceApply` before using an extender as a
parent because that VAP can be created lazily after a cold start.

A successful live parent change follows this path:

```text
RBUS BSSID write
     |
     v
OneWifi mesh-ext state machine --> nl80211 association
     |                                  |
     | confirmed parent                 +--> parent AP/VLAN station
     v
mesh_sta publication
     |
     v
EasyMesh agent --> IEEE 1905 --> controller model --> topology API/WebUI
```

No EasyMesh process is restarted during a normal `test`.  That is an explicit
acceptance condition for live reparenting.

## Backhaul signal reporting

The signal shown for an extender is the measurement made by its parent AP for
the child's backhaul STA.  It is not the signal of one of the extender's
fronthaul clients and it is not a synthetic UI value.

```text
wmediumd path model
       |
       v
mac80211_hwsim NL80211_STA_INFO_SIGNAL
       |
       v
RDK Wi-Fi HAL associated-device RSSI
       |
       v
OneWifi AP metrics (RCPI)
       |
       v
parent Backhaul BSS STAList
       |
       +-- joined by child's Backhaul.STAAddress
       v
topology edge: rssi, rcpi --> extender/link hover
```

EasyMesh RCPI uses half-dB units:

```text
RCPI = 2 * (RSSI dBm + 110)
RSSI = RCPI / 2 - 110
```

For example, `-46 dBm` is RCPI `128`.  RCPI `255` means unavailable and must
remain `N/A`; the WebUI does not fabricate a replacement.

To compare the UI with the kernel measurement, first identify the child's
backhaul STA MAC and then inspect the parent's backhaul AP/VLAN station:

```sh
lxc exec bpiap-002 -- iw dev wifi1.3 info
lxc exec bpiap-003 -- iw dev
lxc exec bpiap-003 -- iw dev wifi1.1.sta1 station dump
```

The dynamic `.staN` suffix may differ, so use `iw dev` rather than assuming
`.sta1` in automation.

## WebUI interpretation

The container lab has a shared L2 path for IEEE 1905 control traffic, so the
Controller's transport hierarchy can remain a star while the Wi-Fi data plane
is multi-hop. The topology API resolves each wireless edge from the child's
current upstream BSSID to the unique AP-mode BSS owner in the live radio
inventory. Backhaul STA-mode rows are excluded because they repeat the parent
BSSID in each child. If the owner is missing or ambiguous, the API retains the
Controller edge and the multihop acceptance test fails rather than inventing a
parent.

The blue wireless edge is the actual reported backhaul relationship.  Hover
an extender or its incoming edge to see:

- parent name;
- media type;
- upstream BSSID;
- band and channel;
- measured RSSI and RCPI, or `N/A` when no valid report exists.

Hover cards flip and clamp within the topology viewport, including for nodes
near the right and bottom edges.

## Acceptance criteria

A profile passes only when:

- every child is associated with the profile's dynamically discovered BSSID;
- every parent reports the child's backhaul STA;
- every extender can ping `10.0.0.1`;
- every non-gateway parent/child edge appears in `/api/v1/topology`;
- all required WLAN clients remain associated and can ping `10.0.0.1`;
- valid parent-side RSSI reaches the matching topology edge;
- the controller database converges exactly to five devices, fifteen radios
  and fifty BSS rows, with at least the requested clients plus four associated
  backhaul STAs; and
- changing among star, branch and chain updates the model without restarting
  agents.

Timestamped command logs are written below
`tmp/test-results/multihop/` by default.
