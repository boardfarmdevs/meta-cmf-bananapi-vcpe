# RDK EasyMesh on Windows with Vagrant and VirtualBox

This is the **RDK-only, 20-client** alternative to the outer LXD VM. It uses
the same 0908 Ubuntu 24.04/Linux 7 guest, native BPI images, userspace wmediumd,
interactive room and EM CLI WebUI. prplMesh is not included or changed.

```text
Windows x86-64 + Vagrant + VirtualBox
  └─ Ubuntu appliance: 6 vCPUs, 8 GiB RAM, sparse 96-GiB disk
       ├─ nested LXD: controller/root agent + 4 extenders + 20 clients
       ├─ Docker: Boardfarm WAN/DHCP
       ├─ hwsim virtual radios + userspace wmediumd
       └─ WebUI, console, interactive room; optional LXD UI/Grafana
```

There are **five physical mesh containers and six logical UI roles**: the
controller and Agent-1 share the root container. Windows needs neither LXD,
Docker Desktop, WSL, physical Wi-Fi adapters nor exposed nested VT-x/AMD-V.
The inner lab uses Linux containers, not nested VMs. Hardware virtualization
is still required to run the outer VirtualBox VM.

## 1. What to download

Download `rdkeasymesh-0908-virtualbox.tar` and its adjacent `.tar.sha256` from
the release host. Windows' built-in `tar` extracts the complete
`rdkeasymesh-0908-virtualbox` release directory:

```text
Vagrantfile
README.md
release.json
rdkeasymesh-0908-virtualbox.box
rdkeasymesh-0908-virtualbox.box.sha256
SHA256SUMS
source-release.json
adapter-files.sha256
adapter-source.tar.gz
package-release.sh
```

A `.vbox` file is only VirtualBox's local machine configuration and cannot
carry this lab on its own. The supplied **`.box`** contains `box.ovf`, its
virtual disk, provider metadata and base configuration. Vagrant creates the
local `.vbox` automatically. Do not import the LXD `.tar` into VirtualBox or
double-click an isolated `.vbox`; use the accompanying `Vagrantfile`.

## 2. Windows prerequisites

1. Use an Intel/AMD x86-64 Windows host, not Windows on ARM. Enable hardware
   virtualization in firmware if Task Manager reports it disabled.
2. Install [Oracle VirtualBox](https://www.virtualbox.org/wiki/Downloads) and
   [HashiCorp Vagrant](https://developer.hashicorp.com/vagrant/install) using
   their Windows installers. The release's Linux-host qualification uses
   VirtualBox 7.2.14 and Vagrant 2.4.9; use compatible 7.2/2.4 releases.
3. Reboot if requested. Open a new **native Windows PowerShell**, not WSL.
   Run `VBoxManage --version` and `vagrant --version`. If `VBoxManage` is not
   on PATH, use `& "$env:ProgramFiles\Oracle\VirtualBox\VBoxManage.exe" --version`.
4. Allow at least 8 GiB for the guest plus Windows headroom: a 16-GiB host is
   the minimum practical demo machine; 24 GiB or more is preferable. Use an
   SSD with about 150 GiB free for the box cache, imported sparse disk and
   future writes. Vagrant and VirtualBox each keep an artifact/disk copy.
5. Keep the directory on a local NTFS disk, for example `C:\labs\rdk-0908`,
   outside OneDrive and network shares. Guest Additions, shared folders and
   the VirtualBox Extension Pack are not required for this lab.

Hyper-V/VBS/Memory Integrity can affect VirtualBox's execution engine and
performance. Check the [VirtualBox manual](https://www.virtualbox.org/manual/)
if startup fails or performance is poor; do not blindly disable Windows
security features or change an employer-managed configuration. Windows-host
timings must not be treated as equivalent to the Linux/KVM reference host.

## 3. Start it

Copy the release tar and checksum to `C:\labs`, then in PowerShell:

```powershell
cd C:\labs
$expectedTar = ((Get-Content .\rdkeasymesh-0908-virtualbox.tar.sha256 -Raw).Trim() -split '\s+')[0]
if ((Get-FileHash .\rdkeasymesh-0908-virtualbox.tar -Algorithm SHA256).Hash -ine $expectedTar) { throw 'Release checksum mismatch' }
tar -xf .\rdkeasymesh-0908-virtualbox.tar
cd .\rdkeasymesh-0908-virtualbox
$expected = ((Get-Content .\rdkeasymesh-0908-virtualbox.box.sha256 -Raw).Trim() -split '\s+')[0]
$actual = (Get-FileHash .\rdkeasymesh-0908-virtualbox.box -Algorithm SHA256).Hash
if ($actual -ine $expected) { throw 'Box checksum mismatch' }
vagrant up --provider=virtualbox
```

No Vagrant Cloud download or Internet access is needed for default lab
provisioning once the software and complete release are installed. Vagrant
verifies the local box checksum, imports the VM, replaces its bootstrap SSH
key, selects the immutable 20-client profile and waits for the native lab and
HTTP services. First boot creates 25 nested instances from the offline image
inputs; allow roughly 20–40 minutes on a suitable SSD, possibly longer on a
slower host. Progress is printed every thirty seconds. This is provisioning
time, not roaming or optimizer response time.

The box remains thin until the first `up`: it contains no provisioned mesh or
client containers. Later starts reuse those instances and reconstruct runtime
state. The default live room returns with twenty clients; smaller rooms can
make clients unavailable without deleting their containers.

## 4. Browser URLs

| View | Windows URL |
| --- | --- |
| EM CLI / network topology | <http://127.0.0.1:18889/> |
| wmediumd console | <http://127.0.0.1:18890/> |
| Interactive live room | <http://127.0.0.1:18891/> |
| Optional nested LXD UI | <https://127.0.0.1:18892/ui/> |
| Optional Grafana | <https://127.0.0.1:18893/> |

Open the topology and room side by side. The room needs no `?mode=` and has
its embedded manual, fullscreen, Play/Pause, dragging, world switching and
Ctrl-click client traffic-probe selection. Room steering converges after
startup; HTTP readiness does not claim that convergence is already complete.

Only adapter 1/NAT is used. Every host forward binds to **127.0.0.1**, not the
LAN. The unauthenticated room/WebUI must not be exposed directly to the
Internet. Avoid adding bridged or host-only adapters. Use a deliberate VPN or
authenticated tunnel for remote demonstrations. Guest ports are 8888, 8890,
8891, 8443 and 3000; the last two have no listener until monitoring is enabled.

Change a conflicting host port before `up` or `reload`, for example:

```powershell
$env:EASYMESH_WEBUI_PORT = '28889'
$env:WMEDIUMD_CONSOLE_PORT = '28890'
$env:EASYMESH_ROOM_DEMO_PORT = '28891'
vagrant up --provider=virtualbox
```

The Vagrantfile refuses duplicate/colliding service ports instead of silently
renumbering them. Optional variables are `EASYMESH_LXD_UI_PORT`,
`EASYMESH_GRAFANA_PORT`, `EASYMESH_CPUS` (minimum 6) and
`EASYMESH_MEMORY_MB` (minimum 8192). Changing resources requires a halt/reload.
Profile 50/100 support remains with the separately qualified LXD appliance.

## 5. Daily operation and diagnosis

```powershell
vagrant status
vagrant ssh
vagrant halt
vagrant up --provider=virtualbox
vagrant reload
```

These commands operate from the release directory. `halt` performs a graceful
guest shutdown; do not routinely save VM state or power it off during native
steering. Neither the supplied VM nor Vagrant is registered for Windows
autostart. If interrupted during first provisioning, run `vagrant provision`
to resume the idempotent readiness path; retain the failed VM for diagnosis.

Inside `vagrant ssh`, use:

```sh
sudo easymesh-labctl status
sudo cat /var/lib/easymesh-lab/thin-firstboot-report.json
sudo journalctl -b -u easymesh-thin-firstboot -u easymesh-lab -u easymesh-room-demo -n 60
sudo lxc list
curl -fsS http://127.0.0.1:8891/api/demo/current | jq '.health, .optimizer.fleet'
```

The first-boot report must say `pass`, 20 clients and 25 final instances.
Measured default-room convergence additionally requires twenty clients
checked, eighty fresh candidate comparisons and `measurement_complete=true`.
The console and viewer expose simulated RF separately from native measurements;
unknown/stale native measurements must not be interpreted as good signal.

The original RDK 0908 LXD import needed one metrics-policy replay for an
extender. If that known native activation weakness occurs, inspect the logs
and use this idempotent recovery inside the guest, then verify fresh metrics:

```sh
curl -fsS --max-time 90 -X POST http://127.0.0.1:8888/api/v1/metricsreporting/enable \
  -H 'Content-Type: application/json' -d '{"interval":5}'
```

This is recovery, not proof that native policy acknowledgement is fixed.
Do not run the baseline zero-loss audit concurrently with a moving live room.
For a deliberate baseline check, stop the room first and always restore it:

```sh
sudo systemctl stop easymesh-room-demo
sudo easymesh-labctl check; result=$?
sudo systemctl start easymesh-room-demo
echo "health audit exit status: $result"
```

If Vagrant fails while inspecting an unrelated inaccessible VirtualBox VM,
inspect `VBoxManage list vms`. Repair that VM's registration deliberately or
use a separate Windows user account with its own VirtualBox registry. The lab
scripts do not unregister other people's VMs to work around this host issue.

To delete this deployment, first preserve any evidence you need, then run
`vagrant destroy` in its directory. This deletes the guest and all nested lab
data. Run `vagrant box list`, then `vagrant box remove NAME --provider=virtualbox`
with this release's exact name to remove its reusable cache separately. Box
names include twelve checksum characters, so a replacement 0908 download
cannot silently reuse an older cached disk. Downloading a new box does not
upgrade an existing VM: preserve its evidence and explicitly destroy/recreate
it if an upgrade is wanted. Removing the cache does not delete your downloaded
release. Do not remove unrelated VirtualBox or LXD machines.

## 6. Optional LXD UI and Grafana

The default offline start does not download monitoring images. To enable
monitoring, provide guest Internet access and open `vagrant ssh`. During a
maintenance window, use the existing monitoring installer inside the guest:

```sh
cd /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/vm/lxd/observability
sudo env LAB_MONITORING_BIND_ADDRESS=10.0.2.15 \
  LAB_MONITORING_PUBLIC_HOST=127.0.0.1 LAB_GRAFANA_PORT=18893 \
  LAB_MONITORING_ALLOW_RESTART=1 bash setup.sh rdk-virtualbox-0908
```

`10.0.2.15` is the default adapter-1 NAT guest address; confirm with
`ip -4 address show enp0s3` if you customized networking. Match `LAB_GRAFANA_PORT`
to your forwarded host port. The first install may restart lab dependencies;
do not run it during a demo. Follow the repository's LXD UI/monitoring manual
for browser TLS trust and enrollment. In the guest, create an enrollment token
with `sudo lxc auth identity create local:tls/lab-browser --group admins`.
Retrieve the newly generated Grafana password locally with
`sudo cat /opt/easymesh-observability/secrets/grafana-admin-password`; username
is `admin`. Do not publish the password or export a credential-bearing box.
Prometheus remains guest-loopback-only and is not forwarded to Windows.
Outer LXD-VM metrics do not apply to this VirtualBox host.

## 7. Rebuild the box (Linux release maintainer)

Conversion does not touch a running RDK/prplMesh deployment. It consumes the
verified, **unprovisioned universal RDK thin bundle**, not a live VM disk. On a
temporary Linux VirtualBox host with passwordless sudo, install `qemu-utils`,
`cloud-guest-utils`, `e2fsprogs`, `jq`, `zstd` and the normal VirtualBox/Vagrant host dependencies. Do not use
Windows for this offline disk conversion.

```sh
cd gen/vm/virtualbox
bash build.sh /absolute/path/rdkeasymesh-0908-thin /absolute/path/rdkeasymesh-0908-virtualbox
cd /absolute/path/rdkeasymesh-0908-virtualbox
vagrant validate
vagrant up --provider=virtualbox
```

The builder verifies the source checksums/provider, sparsely extracts only the
copied RAW/QCOW2 disk, converts it to a work QCOW2 and grows its disk/root
filesystem to 96 GiB. It uses an unused NBD device under a lock, mounts the
labeled root/boot/EFI partitions and adapts DHCP/SSH/cloud-init. It disables only the outer
LXD agent, not nested LXD. SSH host keys, machine ID and nested LXD server
certificates are regenerated per appliance; Vagrant rotates its well-known
bootstrap user key on first connection. No private host keys are copied in.
The guest kernel, native BPI images and lab source remain those identified in
`source-release.json`; adapter changes have their own checksum manifest.

The resulting VirtualBox VM is exported as OVF/VMDK and wrapped in the
[Vagrant box format](https://developer.hashicorp.com/vagrant/docs/boxes/format).
The [VirtualBox provider requirements](https://developer.hashicorp.com/vagrant/docs/providers/virtualbox/boxes)
explain adapter-1 NAT and the base MAC. The builder's temporary VM is
unregistered; intermediate disks are retained in `build.*` for diagnosis and
can be removed deliberately after acceptance. It does not stop/delete any
existing VM or unload another hypervisor's kernel modules.

Qualify an actual import from the resulting `.box`, not only the conversion:
first-boot report, 25 nested instances, browser views, twenty-client native
metrics and room convergence, a small room and restoration, then a graceful
halt/up cycle. Record versions, timings, checksums and failures beside the box.
Testing on a Linux VirtualBox host demonstrates the provider/disk/bootstrap
path, **not firsthand Windows-host validation**. Keep that distinction in
release notes. No full all-room soak is required for this packaging change.
After recording qualification in optional `acceptance.json`/`ACCEPTANCE.md`,
create the Windows download with:

```sh
bash package-release.sh /absolute/path/rdkeasymesh-0908-virtualbox
```

This packages only the explicit release files, never `.vagrant`, test SSH keys,
running VM disks or `build.*` intermediates. The exact adapter sources are
included separately in `adapter-source.tar.gz` and match `adapter-files.sha256`.
