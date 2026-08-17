# Thin Ubuntu 24.04/Linux 7 lab installation

This is the recommended handoff for a new lab user. The small base box contains
Ubuntu 24.04, the accepted `7.0.0-28-generic` kernel and patched hwsim module,
an approximately 62 GB root filesystem, 8 GiB RAM and 8 virtual CPUs. The full
lab is installed once after the VM starts.

## 1. Prepare the Linux host

The host must provide:

- an x86-64 CPU with VT-x or AMD-V enabled;
- VirtualBox 7.x and Vagrant 2.4 or later;
- at least 8 GiB available for the VM; and
- enough disk for a dynamically allocated 64 GB guest.

Verify the tools before importing anything:

```sh
VBoxManage --version
vagrant --version
```

## 2. Import and start the thin VM

```sh
vagrant box add --name cmf/easymesh-thin \
  easymesh-ubuntu24-linux7-*.box

mkdir easymesh-lab
cd easymesh-lab
cp /path/to/gen/vm/consumer/Vagrantfile Vagrantfile

EASYMESH_BOX_NAME=cmf/easymesh-thin vagrant up
vagrant ssh
```

For LAN WebUI access, add `EASYMESH_WEBUI_HOST_IP=0.0.0.0` and the desired
`EASYMESH_WEBUI_PORT` to every Vagrant invocation.

## 3. Configure private inputs

Inside the VM, clone the bootstrap repository using forwarded SSH credentials:

```sh
git clone --branch codex/0815-clean \
  git@github.com:robvogelaar/meta-cmf-bananapi-vcpe.git
cd meta-cmf-bananapi-vcpe
```

Create the root-owned download configuration:

```sh
sudo install -m 0600 gen/vm/thin/online.env.example \
  /etc/easymesh-online.env
sudo editor /etc/easymesh-online.env
```

The four URLs are for the controller rootfs, AP rootfs, and the Alpine 3.19
metadata/rootfs pair. They must be accessible from inside the VM. The custom
Linux archive was already verified while building the thin box. Public URLs,
time-limited signed URLs, or an authenticated corporate artifact service are
suitable. Every downloaded file is checked against its accepted SHA-256 value.

The five Boardfarm repositories are private. Vagrant enables SSH agent
forwarding so no private key is copied into the box.

## 4. Run the one-time full installation

```sh
sudo --preserve-env=SSH_AUTH_SOCK gen/vm/thin/install-lab.sh
```

This phase installs Docker, pinned LXD and uv revisions, CPython 3.13.15, the
locked Python environment, Boardfarm, LXD images, EasyMesh, hwsim and
wmediumd. It creates four extenders and ten clients, performs the complete
acceptance audit, and leaves the accepted lab running. Re-running the installer
reuses valid downloads and exact Git checkouts.

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
