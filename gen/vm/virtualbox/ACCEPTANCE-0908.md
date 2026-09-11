# RDK 0908 VirtualBox qualification

Qualification date: 2026-09-08 PDT / 2026-09-09 UTC.

## Scope and identity

This is a deployment/browser qualification on **Linux-host VirtualBox**, not
firsthand Windows-host validation or an optimizer performance certification.
The Windows installation procedure is in [README.md](README.md).

- Box: `rdkeasymesh-0908-virtualbox.box`.
- SHA256: `ecde5996aeed257f59ea0616a140af34aeaae4585675104cdd40e95bfd4cf59b`.
- Native RDK source: `c1f163c1f8f44ef68bd3d2806d54ea7a7c4cad11`, unchanged.
- VirtualBox: `7.2.14r174565`; Vagrant: `2.4.9` on temporary host rev120.
- Guest: Ubuntu 24.04, kernel `7.0.0-30-generic`, virtualization type `oracle`.
- Resources: six vCPUs, 8192 MiB RAM, sparse 96-GiB disk, about 92 GiB root filesystem.
- Default-user stale VirtualBox registrations were preserved. Testing used
  an isolated, temporary non-root host account.

## Verified

- Actual fresh `vagrant up --provider=virtualbox` imports the shipped box,
  boots via EFI/NAT and replaces the public bootstrap SSH key with a new key.
- Offline first provisioning passes: zero initial nested instances become
  25 instances, comprising five physical mesh devices and twenty clients.
  The first-boot report spans 05:32:12–05:53:06 UTC, about 21 minutes.
- The initial default room reaches a measured 20-client/80-comparison
  snapshot. Web topology reports six logical mesh roles and twenty clients.
- Chromium browser checks pass: clean interactive URL, both fullscreen
  controls, embedded manual, Play/Pause and changing the traffic-probe client
  through the live API. No JavaScript page errors occur. Screenshots are
  retained with the release evidence. The physical Ctrl-click gesture was
  not separately automated.
- `home-a-band-walk-small` passes the ten-client measured convergence check
  in 90.17 seconds, including the test's stability window. All ten excluded
  clients are also verified disconnected in the guest kernel. This is not a
  per-client roaming latency measurement.
- All five mesh containers' native agent/OneWifi services remain active with
  zero automatic restarts during the room check.
- All six host forwards, including SSH, bind only to `127.0.0.1`.
  VirtualBox autostart and exposed nested hardware virtualization are off.
- Ten adapter contract tests pass, including SSH service ordering, local
  checksum-based box identity, resource/port validation, shell syntax and
  exclusion of `.vagrant`, private test keys and build disks from packaging.

## Restart

Graceful `vagrant halt` passes in 35 seconds. The following `vagrant up`
passes in 8 minutes 40 seconds without recreating the existing 25 instances.
Native reconstruction reports model `5/15/50`, clients `20/20`, fresh link
metrics `20/20`, 24 associations and zero service restarts. All twenty clients
reach `10.0.0.1`; the room returns to its default twenty-client world and the
three HTTP services return. Subsequent starts still perform native lab
reconstruction and acceptance; they are not instantaneous.

This restart result verifies lab readiness, not complete optimizer candidate
convergence. The post-restart room is still collecting/steering when sampled.

## Known limitations

The complete world-switch smoke test **does not pass** its 180-second default
room convergence gate after switching back from the smaller room. The exact
twenty-client roster returns, but a continuously complete, fresh candidate
snapshot is not maintained for the required stability window. The final
restoration check also times out. These failures are retained, not relabeled
as successful convergence.

The captured native API responses include HTTP 503 with
`Error_Prev_Cmd_In_Progress`. This does not establish that the issue is
VirtualBox-specific. No native stack changes, freshness-threshold relaxation,
synthetic metrics or manual metrics-policy replay were used to pass the
deployment checks. Treat unavailable/stale measurements as unavailable and
do not use this qualification to claim instant or reliable all-room optimizer
convergence. The release is suitable for deployment/UI evaluation with this
known runtime limitation.

Optional LXD UI/Grafana installation is documented but was not exercised
inside this VirtualBox guest. No Windows host, full room soak or physical
Wi-Fi hardware was tested. The production RDK and prplMesh deployments were
not restarted or modified for this work.
