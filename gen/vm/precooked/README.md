# Precooked EasyMesh Vagrant Lab

This project tests whether the complete simulated EasyMesh steering lab can be
recreated on another engineer's workstation as one VirtualBox guest managed by
Vagrant.

This directory builds and stores the complete offline appliance. The preferred
new-user installation is described in [`../thin/README.md`](../thin/README.md);
the distribution overview is [`../README.md`](../README.md).

The intended guest boundary is:

```text
VirtualBox Ubuntu 24.04 guest
|-- Linux 7.0 + patched mac80211_hwsim
|-- patched multichannel wmediumd
|-- LXD
|   |-- bpibroadband (controller)
|   |-- bpiap and bpiap-001 (baseline extenders)
|   |-- bpiap-002 and bpiap-003 (scale-test extenders)
|   `-- twenty WLAN clients (ten private + ten IoT)
`-- Boardfarm Docker services
    |-- dhcp-cpe1
    `-- wan-cpe1
```

The guest uses VirtualBox NAT for provisioning and Internet access. The RDK-B
controller connects `erouter0` to the guest-local Boardfarm `br-wan101` bridge.
The EasyMesh WebUI is forwarded to `http://127.0.0.1:18888` on the host so it
does not collide with rev150's native lab on port 8888.

## Host installation and sizing

On an Ubuntu 22.04 or 24.04 host, install the VM tools from their upstream
repositories:

```sh
. /etc/os-release
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

The remaining host requirements are:

- x86-64 CPU with VT-x or AMD-V
- at least 8 logical CPU threads; the VM uses 6 by default
- 6 GiB RAM recommended (the accepted rev150 run also fits in 4 GiB)
- approximately 30 GiB free disk while preparing the appliance

The Yocto build environment is deliberately outside the appliance. It consumes
prebuilt controller and extender images with recorded SHA-256 hashes.

## Bring-up and acceptance

The default provisioner creates the complete controller, four-extender and
twenty-client topology. It gates every extender before starting the next one
and then admits ten private and ten IoT clients.

```sh
vagrant up
vagrant ssh -c 'bash /home/vagrant/return-steering-test.sh'
vagrant ssh -c 'bash /home/vagrant/scale-steering-test.sh 3'
vagrant ssh -c 'bash /home/vagrant/health-audit.sh'
```

The WebUI is available at `http://127.0.0.1:18888`. Test CSV files are written
under `/home/vagrant/.local/state/easymesh-vagrant/` in the guest. Reboot
acceptance evidence is grouped by kernel boot ID beneath
`reboot-acceptance/`.

After provisioning, `easymesh-lab.service` owns boot order. It stops any state
restored by LXD, reclaims OneWifi VAPs from host-returned hwsim wiphys, and then
starts controller, extenders and clients in order. A PASS requires:

- model `5/15/50/24` and WebUI API `20/20`;
- all twenty clients able to reach the WLAN gateway;
- zero OneWifi, agent, controller and CLI service restarts; and
- a 120-second stable hold after final convergence.

## Boardfarm installation and boot ownership

The guest installs Docker and `astral-uv`, creates
`/home/vagrant/boardfarm-open-0406/.venv` with Python 3.13, and installs only
the pinned `boardfarm-lab-staging` repository as an editable package. That
repository now contains the `bf-lab` command and the complete `ca-desk6`
configuration.

The builder uses a Git bundle rather than forwarding an engineer's SSH key into
the appliance. `assets.lock` records the source commit and
`prepare-assets.sh` constructs that bundle and the combined SHA-256 manifest.

`BF_LAB_CONFIG` and `BF_INVENTORY` select files below different directories:

```text
BF_LAB_CONFIG=ca-desk6.json
  -> boardfarm-lab-staging/lab/ca-desk6.json
BF_INVENTORY=ca-desk6.json
  -> boardfarm-lab-staging/inventories/ca-desk6.json
```

This profile provides only the DHCP/NAT functions needed by `bpibroadband`.
It does not build or run Oktopus, telemetry, XConf, GenieACS, WebConfig, LAN
clients, or unrelated Boardfarm services.

On every boot, `boardfarm-lab.service` runs:

```sh
bf-lab teardown,setup,status
```

This creates `br-wan101`, starts only `dhcp-cpe1` and `wan-cpe1`, and performs
the six `ca-desk6` health checks. The forwarding and EasyMesh services are
ordered after it, so `bpibroadband` cannot attach `erouter0` until those two
containers and `br-wan101` are ready.

## Build commands

Supply the binary inputs and private repository workspace, then use the single
entry point:

```sh
cd gen/vm/precooked
BOARDFARM_WORKSPACE=$HOME/git/boardfarm-open-0406 \
EASYMESH_VM_BINARY_ASSETS=/path/to/binary-assets \
  ./build.sh all
```

Available phases are `prepare`, `up`, `test`, `reboot-test`, `package`, and
`all`. `all` prepares the immutable inputs, provisions the VM, performs a cold
reboot acceptance test, and packages the passing VM. `package` writes a
timestamped, shareable Vagrant box and adjacent SHA-256 file below
`gen/vm/precooked/artifacts/`; it does not publish or upload them. Set
`EASYMESH_BOX_OUTPUT` when a particular output path is required.

`package` is the terminal build phase. It stops the lab, removes copied
provisioning archives, prunes unused Docker build layers and images, cleans
package/log caches, zeroes and trims free space, and halts the VM before
capture. The two Boardfarm images referenced by `dhcp-cpe1` and `wan-cpe1`
remain in the appliance. These steps ensure the smaller `ca-desk6` installation
also produces a smaller compressed `.box` instead of only showing more free
space inside the guest.

The receiving engineer needs only the box and `../consumer/Vagrantfile`:

```sh
vagrant box add --force --name cmf/easymesh-lab easymesh-lab-*.box
mkdir easymesh-lab && cd easymesh-lab
cp /path/to/gen/vm/consumer/Vagrantfile .
vagrant up
```

That first boot runs the same persistent Boardfarm and EasyMesh reconstruction
services as the build acceptance. It does not need the source repositories,
GitHub credentials, or the original asset directory.

To expose the UI on a trusted lab LAN instead of host loopback:

```sh
EASYMESH_WEBUI_HOST_IP=0.0.0.0 EASYMESH_WEBUI_PORT=18888 ./build.sh up
```

The working VMDK is not downloaded as a bespoke appliance. Vagrant imports the
pinned Bento base box into VirtualBox, VirtualBox clones its disk below
`~/VirtualBox VMs/<EASYMESH_VM_NAME>/`, and the provisioners transform that
clone. `vagrant package` then captures the provisioned VM as the distributable
box; consumers do not copy the mutable working VMDK directly.

## Manual Boardfarm installation

For an online development installation, use the same single-repository layout
as the appliance:

```sh
mkdir -p "$HOME/boardfarm-open-0406"
cd "$HOME/boardfarm-open-0406"
uv venv --python 3.13 --prompt bf-venv .venv
. .venv/bin/activate
git clone git@github.com:robvogelaar/boardfarm-lab-staging.git
uv pip install -e boardfarm-lab-staging

export BF_LAB_CONFIG=ca-desk6.json
export BF_INVENTORY=ca-desk6.json
cd boardfarm-lab-staging/lab
bf-lab teardown,setup,status
```

The appliance build uses a pinned bundle of this repository so that a shared
box contains no GitHub key and does not change when its source branch moves.

## Uninstall

The package-preserving and optional lab-data removal procedures for an Ubuntu
host are documented in [`../thin/README.md`](../thin/README.md#uninstall-from-the-ubuntu-host).
The same procedure applies to the precooked distribution; use its registered
box name, normally `cmf/easymesh-lab`, when removing the Vagrant box.
