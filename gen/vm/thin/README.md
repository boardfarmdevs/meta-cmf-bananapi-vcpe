# Thin Ubuntu 24.04/Linux 7 lab installation

This is the recommended handoff for a new lab user. The small base box contains
Ubuntu 24.04, the accepted `7.0.0-28-generic` kernel and patched hwsim module,
an approximately 62 GB root filesystem, 8 GiB RAM and 6 virtual CPUs. The full
lab is installed once after the VM starts.

## 1. Prepare the Linux host

The supported host installations are Ubuntu 22.04 and 24.04. Use the upstream
repositories because the distribution packages may not provide the VirtualBox
and Vagrant versions used by this lab:

```sh
. /etc/os-release
printf 'host: %s %s (%s)\n' "$NAME" "$VERSION_ID" "$VERSION_CODENAME"
case "$VERSION_ID:$VERSION_CODENAME" in
  22.04:jammy|24.04:noble) host_suite=$VERSION_CODENAME ;;
  *) echo 'Ubuntu 22.04 or 24.04 is required.' >&2; exit 1 ;;
esac

sudo apt update
sudo apt install -y ca-certificates curl gpg

curl -fsSL https://www.virtualbox.org/download/oracle_vbox_2016.asc \
  | sudo gpg --dearmor --yes \
      -o /usr/share/keyrings/oracle-virtualbox-2016.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/oracle-virtualbox-2016.gpg] https://download.virtualbox.org/virtualbox/debian $host_suite contrib" \
  | sudo tee /etc/apt/sources.list.d/virtualbox.list

curl -fsSL https://apt.releases.hashicorp.com/gpg \
  | sudo gpg --dearmor --yes \
      -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $host_suite main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list

sudo apt update
sudo apt install -y virtualbox-7.2 vagrant

VBoxManage --version
vagrant --version
```

If Secure Boot prevents the VirtualBox kernel modules from loading, complete
Ubuntu's displayed MOK enrollment procedure during the next host reboot. Then
verify the driver before continuing:

```sh
sudo modprobe vboxdrv
VBoxManage list hostinfo
```

If `vboxdrv` is missing after a custom-kernel installation, first verify the
matching headers and rebuild the Oracle modules:

```sh
test -e "/lib/modules/$(uname -r)/build"
sudo /sbin/vboxconfig
sudo modprobe vboxdrv
find "/lib/modules/$(uname -r)" -type f -name 'vbox*.ko*' -print
```

If another VirtualBox package is already installed, remove it and repeat the
upstream installation above so the modules are built by VirtualBox 7.2 against
the running kernel.

The host hardware must provide:

- an x86-64 CPU with VT-x or AMD-V enabled;
- at least 8 logical CPU threads, of which the VM uses 6 by default;
- at least 8 GiB allocatable memory for the VM; and
- enough disk for a dynamically allocated 64 GB guest.

Six vCPUs are used because this guest concurrently runs 20 Boardfarm Docker
containers, five EasyMesh LXD devices, ten WLAN-client containers, wmediumd,
hwsim and the WebUI/controller processes. Six is the accepted default, not a
protocol requirement. Eight vCPUs was an earlier conservative builder value
and is not required. On a larger host it can still be overridden explicitly:

```sh
EASYMESH_VM_CPUS=8 vagrant up
```

## 2. Import and start the thin VM

Obtain the dated Dropbox bundle URL from the maintainer. A bundle is named
`em-artifacts-0817.tar.bz2`, `em-artifacts-0818.tar.bz2`, and so on. Create a
new lab directory, download exactly one version, and extract it:

```sh
cd
mkdir -p easymesh-lab/artifacts
cd easymesh-lab

artifact_stamp=0817
curl --fail --location --retry 3 \
  'https://www.dropbox.com/scl/fi/dnbx8889mmndu9z03c5eo/em-artifacts-0817.tar.bz2?rlkey=bwxqhu4v9nj94a5ne1qmc141k&dl=1' \
  --output "artifacts/em-artifacts-$artifact_stamp.tar.bz2"
tar -xjf "artifacts/em-artifacts-$artifact_stamp.tar.bz2"
sha256sum -c "artifacts/SHA256SUMS-$artifact_stamp"
```

The accepted 0817 tarball is 1,209,103,460 bytes and has SHA-256
`cb0a6e62b9218ad8dd36d1f83ac96ba52d5b2466a072f442e88f30c9b5dc61f7`.
Its optional Dropbox checksum sidecar is:

```text
https://www.dropbox.com/scl/fi/809w5sv2c6n8nnrn7p3bn/em-artifacts-0817.tar.bz2.sha256?rlkey=d8uhmywq4pihwy7ekgj7dy8qh&dl=1
```

The archive supplies a `Vagrantfile` plus timestamped, clearly named files
under `artifacts/`. It is a binary handoff and is not stored in Git. Register
the box, then load the host's GitHub key into an SSH agent. The five private
Boardfarm repositories use agent forwarding so no private key is copied into
the VM.

```sh
vagrant box add --name cmf/easymesh-thin \
  "artifacts/easymesh-thin-$artifact_stamp.box"
vagrant box list | grep '^cmf/easymesh-thin '

eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_rsa
ssh-add -l

EASYMESH_BOX_NAME=cmf/easymesh-thin vagrant up
vagrant ssh
```

If an agent is already running, only `ssh-add` is required. Keep that terminal
for `vagrant up`, `vagrant ssh`, and the one-time installer.

For LAN WebUI access, add `EASYMESH_WEBUI_HOST_IP=0.0.0.0` and the desired
`EASYMESH_WEBUI_PORT` to every Vagrant invocation.

## 3. Configure private inputs

Inside the VM, clone the bootstrap repository using forwarded SSH credentials:

```sh
git clone --branch codex/0815-clean \
  git@github.com:robvogelaar/meta-cmf-bananapi-vcpe.git
cd meta-cmf-bananapi-vcpe
```

Install the generated root-owned configuration. It points to the bundle's four
runtime images through the read-only `/vagrant-artifacts` mount:

```sh
artifact_stamp=0817
sudo install -m 0600 "/vagrant-artifacts/easymesh-local-$artifact_stamp.env" \
  /etc/easymesh-online.env
```

The four local URLs cover the controller rootfs, AP rootfs and Alpine 3.19
metadata/rootfs pair. The thin box already contains the verified custom Linux
kernel. The installer checks every bundled input against its accepted SHA-256.

## 4. Run the one-time full installation

```sh
sudo --preserve-env=SSH_AUTH_SOCK gen/vm/thin/install-lab.sh
```

This phase installs Docker, pinned LXD and uv revisions, CPython 3.13.15, the
locked Python environment, Boardfarm, LXD images, EasyMesh, hwsim and
wmediumd. It creates four extenders and ten clients, performs the complete
acceptance audit, and leaves the accepted lab running. Re-running the installer
reuses valid downloads and exact Git checkouts.

The installer defaults the runtime checkout to the accepted `5f8cd4b` 0818
revision. A maintainer can select another full commit explicitly with
`EASYMESH_RUNTIME_COMMIT`, but an unqualified branch tip is never used as an
installation input.

Do not proceed unless it ends with:

```text
One-time installation and first cold-start PASS. The lab is ready.
```

This is the best point for an optional VM snapshot.

## 5. First cold start and optional reboot

The installer has already performed the first cold start. Confirm it before
opening the UI:

```sh
sudo easymesh-labctl check
```

Alternatively, reboot the VM. The enabled services start the installed lab
automatically; after reconnecting, wait for that warm start and check it:

```sh
sudo reboot
# reconnect with: vagrant ssh
sudo easymesh-labctl warm-start
sudo easymesh-labctl check
```

## 6. Open the WebUI

From the VirtualBox host, open:

```text
http://127.0.0.1:18888/
```

With LAN binding enabled, use the VirtualBox host's address instead of
`127.0.0.1`. The topology must show the controller, colocated agent, four
extenders and ten live clients before testing.

## 7. Run steering tests

```sh
sudo easymesh-labctl steer-return
sudo easymesh-labctl steer-scale 3
sudo easymesh-labctl check
```

CSV results and reboot evidence are stored below:

```text
/home/vagrant/.local/state/easymesh-vagrant/
```

## 8. Later operation and restart

```sh
sudo easymesh-labctl status
sudo easymesh-labctl warm-start
```

Use `vagrant halt` on the host for normal shutdown and `vagrant reload` to
restart the lab. After reconnecting, use `warm-start` and `check`; do not repeat
the one-time installer. Do not manually stop and restart only the EasyMesh
service chain: a partial restart can retain stale controller topology.

## Building the thin base box

This is for the maintainer, not the lab user:

```sh
cd gen/vm/thin
EASYMESH_KERNEL_URL=https://artifacts.example/linux-7.0.0-28-hwsim.tar.zst \
  ./build-thin.sh
```

`EASYMESH_KERNEL_ARCHIVE` may select a local archive instead. The builder
verifies the kernel after reboot and ensures the root filesystem is at least
60 GB before writing the box and checksum under `thin/artifacts/`.

Package the box and accepted runtime images into the dated Dropbox handoff:

```sh
cd gen/vm/thin
./package-artifacts.sh 0817 \
  artifacts/easymesh-ubuntu24-linux7-YYYYMMDDTHHMMSSZ.box
```

The optional third argument selects a different runtime-asset directory and
the fourth selects a different output directory. The script validates every
input, creates `artifacts/em-artifacts-0817.tar.bz2`, and writes an adjacent
tarball checksum for the maintainer. Upload the tarball to Dropbox manually.

## Uninstall from the Ubuntu host

First stop the lab from its Vagrant working directory:

```sh
vagrant halt
```

Remove the programs and the two repositories while preserving all VMs, boxes
and user configuration:

```sh
sudo apt remove -y virtualbox-7.2 vagrant
sudo rm -f \
  /etc/apt/sources.list.d/virtualbox.list \
  /etc/apt/sources.list.d/hashicorp.list \
  /usr/share/keyrings/oracle-virtualbox-2016.gpg \
  /usr/share/keyrings/hashicorp-archive-keyring.gpg
sudo apt update
sudo apt autoremove
```

The commands above are reversible by repeating the installation procedure.
They deliberately retain `~/VirtualBox VMs`, `~/.vagrant.d`, and each project
directory's `.vagrant` state.

Only when the lab data is no longer needed, remove it through Vagrant before
uninstalling the programs:

```sh
# Run in the lab's Vagrant working directory. This deletes that VM and disk.
vagrant destroy

# Remove only the imported EasyMesh boxes after confirming their exact names.
vagrant box list
vagrant box remove cmf/easymesh-thin
vagrant box remove cmf/easymesh-lab
```

Do not manually delete the complete `~/VirtualBox VMs` or `~/.vagrant.d`
directories: they may contain unrelated virtual machines and Vagrant projects.
