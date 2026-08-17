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
|   `-- ten WLAN clients
`-- Boardfarm Docker services
    |-- five DHCP providers
    |-- five WAN gateways
    `-- ten LAN clients
```

The guest uses VirtualBox NAT for provisioning and Internet access. The RDK-B
controller connects `erouter0` to the guest-local Boardfarm `br-wan105` bridge.
The EasyMesh WebUI is forwarded to `http://127.0.0.1:18888` on the host so it
does not collide with rev150's native lab on port 8888.

## Host requirements

- x86-64 CPU with VT-x or AMD-V
- VirtualBox 7.2
- Vagrant 2.4
- 6 CPU threads
- 6 GiB RAM recommended (the accepted rev150 run also fits in 4 GiB)
- approximately 30 GiB free disk while preparing the appliance

The Yocto build environment is deliberately outside the appliance. It consumes
prebuilt controller and extender images with recorded SHA-256 hashes.

## Bring-up and acceptance

The default provisioner creates the complete controller, four-extender and
ten-client topology. It gates every extender before starting the next one and
gates the first five clients before applying the scale step.

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

- model `5/15/50/14` and WebUI API `10/10`;
- all ten clients able to reach the WLAN gateway;
- zero OneWifi, agent, controller and CLI service restarts; and
- a 120-second stable hold after final convergence.

## Boardfarm installation and boot ownership

The guest installs Docker and a locally asserted, pinned `astral-uv` snap, creates
`/home/vagrant/boardfarm-open-0406/.venv` with Python 3.13.15, and installs the
locked `boardfarm`, `pytest-boardfarm`, `boardfarm-docsis`,
`boardfarm-charter`, and `boardfarm-lab-staging` repositories as editable
packages.

The builder uses Git bundles rather than forwarding an engineer's SSH key into
the appliance. `assets.lock` records the source commits and
`prepare-assets.sh` constructs those bundles and the combined SHA-256
manifest. `config/boardfarm-requirements.lock` pins the accepted third-party
Python environment; editable packages are then built without dependency
re-resolution or isolated build-environment downloads.

`BF_LAB_CONFIG` and `BF_INVENTORY` are not two names for one JSON file. In the
current Boardfarm trees they resolve below different directories:

```text
BF_LAB_CONFIG=boardfarm-easymesh.json
  -> boardfarm-lab-staging/lab/boardfarm-easymesh.json
BF_INVENTORY=boardfarm-easymesh.json
  -> boardfarm-lab-staging/inventories/boardfarm-easymesh.json
```

The proposed `co/ca-desk/lab5.json` path does not exist in the pinned staging
repository. The builder supplies distinct, VM-specific infrastructure and
inventory documents. They have no physical switch or host VLAN interface and
disable optional service containers.

On every boot, `boardfarm-lab.service` runs:

```sh
bf-lab teardown,setup,status
```

This creates `br-wan101` through `br-wan105`, starts all 20 containers defined
by the five-CPE configuration, and performs 60 container, direct-SSH and
forwarded-port checks. The forwarding and EasyMesh services are ordered after
it, so `bpibroadband` cannot attach `erouter0` until `br-wan105`, `dhcp-cpe5`,
and `wan-cpe5` are ready.

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

## Review of the manual Boardfarm recipe

The proposed five editable installs are valid for the pinned repositories, and
all four `doc,dev,test` extra sets exist. For an interactive checkout, quote
each extras expression so the shell cannot expand the brackets:

```sh
uv pip install \
  -e 'boardfarm[doc,dev,test]' \
  -e 'pytest-boardfarm[doc,dev,test]' \
  -e 'boardfarm-docsis[doc,dev,test]' \
  -e 'boardfarm-charter[doc,dev,test]' \
  -e boardfarm-lab-staging
```

There are three important appliance-specific corrections. The builder pins the
repository commits, Python patch release, uv snap revision, and all transitive
Python packages instead of resolving current branches on every build. It uses
local Git bundles rather than requiring GitHub credentials inside a shared VM.
Finally, the lab configuration and device inventory are separate documents;
the suggested `co/ca-desk/lab5.json` is not present in the pinned staging
repository. The supplied `boardfarm-easymesh.json` pair replaces it.

## Current status

The accepted images are the `20260817135730` controller and `20260817140053`
extender pair. Their
scale-safe EasyMesh agent fixes the deterministic AP Metrics Response stack
overflow exposed by the fourth extender and associated stations.

The current acceptance requires Boardfarm `60/60`, model `5/15/50/14`, six
topology nodes, 50 BSSs, 10/10 clients, ten-client WLAN traffic and zero
EasyMesh service restarts. The captured evidence and defects found during the
accepted run are in `docs/acceptance-2026-08-17.md`.
