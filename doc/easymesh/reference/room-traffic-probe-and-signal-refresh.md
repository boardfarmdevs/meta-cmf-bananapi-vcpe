# Selectable room probe and continuous signal telemetry

This is a rev140-only room-service/source overlay on the deployed 0906 RDK
appliance. rev150, prplMesh/rev120 and the immutable 0906 thin tars are unchanged.

## Operation

Open `http://192.168.2.140:18891/viewer/?mode=interactive` and reload the viewer
after deployment. Ctrl+click any client (Command+click on Mac) to make it the
shared traffic probe. Alternatively select a client and press **Use selected
client as probe**, or use its right-click menu. No operator capability or prompt
is required; the browser acquires the normal exclusive interaction lease.
Read-only observers cannot
change the probe but see the accepted selection and results.

The updated interactive API has no built-in user authentication. Anyone who
can reach it can acquire control when the lease is free. Keep it on a trusted
lab network, SSH tunnel, or authenticated gateway; do not expose it directly
to the internet. Same-origin/JSON checks, lease ownership, command IDs and
revision validation remain enforced. `mode=live` is a read-only UI, not an
access-control boundary. Separate read-only server sessions still reject writes.
The CLI no longer generates an operator token file or capability-bearing URL.

The probe has a cyan outer ring. The optimizer's focus keeps its independent
yellow ring; both may appear together. Static/moving/cohort body colors are
unchanged. Extenders are warm orange-red (`#d65f27`); the controller stays red.

The selected bound container sends the existing lightweight gateway ping.
Selection does not move a device, change presence, rewrite wmediumd links,
change the RF environment epoch, or select a steering target. It is session
state, retained across world loads and reset to the manifest default on a new
server session. An offline selected client reports a paused probe, not an old
successful ping. In-flight samples carry the probe selection identity and are
discarded when that identity changes.

The endpoint is `POST /api/demo/traffic-probe` with `role`, lease `token`,
`command_id` and the existing `If-Match` world revision. It uses the serialized
RoomEngine queue and command-id deduplication. Mesh nodes and unbound roles
are rejected. Plain click and navigation still do not acquire a lease.

## Why the meters turned grey

The network worker previously stopped polling for the entire duration of
optimizer candidate collection. Those queries can outlast the viewer's
20-second freshness window, making otherwise working links all grey.
Some native controller client records also retained old receipt timestamps.
The browser additionally compared timestamps with its own wall clock, which
could reject valid measurements on a machine with clock skew.

The room now keeps passive telemetry polling independent of candidate
collection, with one network publisher so delayed optimizer snapshots cannot
overwrite fresh display samples. For missing or older-than-ten-second controller readings, the
interactive observer can use `read_client_link`: a successful ping through
`wlan0`, followed by `iw link`, requiring the observed BSSID and band to match
the controller. Samples are cached for ten seconds, invalidated by identity,
association or RF epoch changes, and labelled
`client_kernel_iw_link_after_wlan_traffic_probe`. Failed or mismatching samples
remain unknown/stale; no controller source data is rewritten and no simulated
geometry is presented as measured signal. The native EMCLI UI can consequently
remain grey while the room shows a separately sourced kernel measurement.

The viewer anchors freshness to server event time and ages it with monotonic
browser time. An interrupted event stream still greys measurements after the
same 20-second limit; increasing the limit or painting stale readings green
is not the fix. The inspector reports the measurement source and age.

## Regression checks

From the repository root:

```bash
PYTHONPATH=gen/demo:gen/wmediumd/configurator:gen/optimizer python3 -m unittest discover -s gen/demo/tests
PYTHONPATH=gen/optimizer:gen/wmediumd/configurator python3 -m pytest gen/optimizer/tests
node gen/tests/signal-meter-test.js
node gen/tests/viewer-play-drag-test.js
node gen/tests/viewer-traffic-probe-test.js
node gen/tests/viewer-world-loading-test.js
```

Live acceptance checks both client cohorts, observer synchronization, cyan
probe/orange extender colors, unchanged RF state during selection, genuine
traffic from the selected container, and continuous signal freshness across
multiple candidate-collection cycles. Only the room service needs a restart;
the native lab and its 25 containers remain running. The deployment stores an
overlay checksum manifest separately from the original release manifest.
