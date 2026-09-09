# 0908 deployed release acceptance

Recorded on 2026-09-09 UTC (2026-09-08 Pacific). RDK runs on rev140;
prplMesh runs independently on rev150. This records an actual final thin-tar
import, not just the corrected builder's successful reconstruction.

## RDK identity and deployment

- Canonical branch: `codex/0908-clean`.
- Checkout: `rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0908-clean/meta-cmf-bananapi-vcpe`.
- Packaged source: `c1f163c1f8f44ef68bd3d2806d54ea7a7c4cad11`.
- Archive: `rev140:/home/rev/releases/0908/rdkeasymesh-0908-thin.tar`.
- SHA256: `520adb104252ba1119e05daa4d10b6b49fc802031f828713da119aa0618c332a`.
- Controller rootfs SHA256: `1f2f1ada9c86f9100072c3c073ca9d6ca437f526d7c7871f50d3e92f3fa6fcf4`.
- Extender rootfs SHA256: `501e8584f3d5c53d25d92447cc3a7c3d547201f6f6fb5b36aec780f539e48ab2`.

Both native Yocto role images are rebuilt. Archive manifests retain the exact
rootfs names and source IDs. This clean-workspace proof deliberately uses
workspace-local download/sstate directories, not the shared `~/oe/` cache.
Later qualification-document commits do not alter the packaged source ID.

The bundled importer creates `rdkeasymesh-20-0908` with six vCPUs, 8 GiB RAM,
twenty clients and five physical mesh devices (six logical UI roles).
First-boot provisioning starts with zero nested instances at 04:03:40 UTC,
finishes with 25 at 04:19:45, and passes the native model/identity/service/
all-client traffic audit at 04:20:02. Lab and room systemd restart counters
remain zero. Outer VM `boot.autostart=false` is preserved.

## Live checks and important cold-start caveat

The fresh import exposed a remaining native reporting-activation weakness:
one extender had no periodic AP reporting task, although the controller's
desired policy said five seconds and the all-device activation API had
returned success. Initially the baseline clients did not exercise every AP;
room steering subsequently exposed missing measurements on that extender.
The room correctly kept these measurements unavailable instead of claiming
complete convergence or using simulated geometry as observed RSSI.

One explicit, idempotent replay through the existing API restored that
extender's reporting without restarting containers or native services:

```sh
curl -fsS --max-time 90 -X POST \
  http://192.168.2.140:48889/api/v1/metricsreporting/enable \
  -H 'Content-Type: application/json' -d '{"interval":5}'
```

After replay, the default room reaches twenty clients checked, eighty fresh
candidate comparisons, complete measured convergence and no stronger eligible
AP. Both fullscreen views, embedded manual, Play/Pause and probe selection/
restoration pass browser checks, with twenty clients, six logical roles and
no JavaScript errors. Physical canvas gestures have separate deterministic
tests; the browser smoke uses the probe API with its browser control lease.

**This is not an unconditional unattended cold-start reporting pass.** The
manual replay is a recovery, not a fix for native policy delivery/application
acknowledgement. A future activation gate should verify actual reporting from
every AP, including APs initially without clients, rather than only desired
controller state. Preserve this caveat when comparing release results.
No full room soak is claimed. Earlier corrected-builder cold reconstruction
and twenty-client/eighty-comparison convergence also pass; they do not erase
the fresh-import finding.

Detailed first-boot/browser/metrics evidence is beside the archive in
`rev140:/home/rev/releases/0908/rdkeasymesh-0908-acceptance/`.

## Browser access and monitoring

| View | RDK on rev140 | prplMesh on rev150 |
| --- | --- | --- |
| Live room | <http://192.168.2.140:48891/> | <http://192.168.2.150:18891/> |
| Network topology | <http://192.168.2.140:48889/> | <http://192.168.2.150:8091/> |
| Radio console | <http://192.168.2.140:48890/> | <http://192.168.2.150:8090/> |

The room URLs need no `?mode=`. These independent trusted-LAN/VPN services
can run side by side; neither UI drives the other lab.

RDK monitoring is enabled in the new VM:

- LXD UI: `https://192.168.2.140:48892/ui/` (HTTP 200).
- Grafana: `https://192.168.2.140:48893/` (HTTPS, not HTTP).
- Prometheus self/LXD targets are UP; CPU, memory and network series are
  present, including memory series for all 25 nested containers.
- Grafana's provisioned LXD dashboard and Prometheus data-source health pass.

Credentials are newly generated, not inherited from an old VM or archive.
Use the existing monitoring manual to enroll a browser in nested LXD and
retrieve the local Grafana admin password. Monitoring prplMesh and exporting
outer-host metrics remain opt-in; no new public Prometheus endpoint is opened.

After live qualification, obsolete RDK 0906/0907 and packaging/builder VMs
are deleted. The unrelated stopped `hwsim-kernel-dev-0829` VM is retained.
prplMesh's active rev140 resources remain retired; its new lab and stopped
native build container are on rev150. No rev120 changes are made.
