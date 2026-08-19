# Packaged EasyMesh VirtualBox lab user guide

This guide is for an engineer receiving a complete, already-installed EasyMesh
Vagrant box. It starts with a new Ubuntu workstation and ends with a usable
five-AP, ten-client simulated WLAN. It also explains how to inspect the lab,
use the WebUI and controller interfaces, run steering and RF tests, collect
evidence, restart the VM and make another packaged copy.

The packaged box is different from the thin installer. Everything inside the
guest has already been installed and accepted: Ubuntu 24.04, Linux 7.0, the
patched hwsim module, multichannel wmediumd, LXD, Docker, Boardfarm, the
controller, four extenders, ten WLAN clients and the test checkout. A new user
imports the box and starts it; they do not run the one-time installer.

## 1. Understand the lab

```text
Ubuntu 22.04/24.04 workstation
`-- VirtualBox VM, managed by Vagrant
    |-- Ubuntu 24.04 + Linux 7.0 + patched mac80211_hwsim
    |-- Boardfarm/Docker
    |   |-- br-wan105                         simulated WAN bridge
    |   |-- dhcp-cpe5                         DHCP provider
    |   `-- wan-cpe5                          routed Internet side
    |-- LXD
    |   |-- bpibroadband                      EasyMesh controller + agent
    |   |-- bpiap ... bpiap-003               four EasyMesh extenders
    |   `-- wlan-client ... wlan-client-009   ten simulated stations
    |-- patched multichannel wmediumd         simulated RF medium
    `-- WebUI/API on guest port 8888
             `-- Vagrant forwards it to host port 18888
```

Boardfarm has a deliberately narrow infrastructure role in this lab. Its
Docker containers create the `br-wan105` bridge and provide DHCP and WAN
connectivity. The `bpibroadband` container attaches `erouter0` to that bridge,
receives IPv4 and IPv6 configuration and gets Internet access. Boardfarm does
not implement Wi-Fi, EasyMesh, steering, RF simulation or optimization. Those
functions belong to the LXD nodes, OneWifi/EasyMesh, hwsim, wmediumd and the
test tools.

The expected EasyMesh topology is:

- one controller model node;
- one colocated agent in `bpibroadband`;
- four extender agents;
- three radios per agent, representing 2.4, 5 and 6 GHz;
- ten BSSs per agent and 50 BSSs in total; and
- ten associated WLAN clients.

The controller database shorthand `5/15/50/14` means five EasyMesh devices,
15 radios, 50 BSSs and 14 associated station rows: ten fronthaul clients plus
four extender backhaul stations. The WebUI shows six mesh nodes because it
renders the controller model separately from its colocated agent.

## 2. Install VirtualBox and Vagrant on the workstation

The supported hosts are Ubuntu 22.04 and 24.04 on x86-64 hardware with VT-x or
AMD-V enabled. The accepted default VM allocation is six virtual CPUs and
6144 MiB RAM. Have at least eight logical host threads, 8 GiB of allocatable
RAM and sufficient space for a dynamically allocated 64 GB virtual disk.

Install current upstream packages:

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
sudo modprobe vboxdrv
VBoxManage list hostinfo
```

If Secure Boot blocks `vboxdrv`, complete the MOK enrollment shown by Ubuntu
during the next host reboot. If the workstation uses a custom kernel, install
its matching headers and rebuild the Oracle modules:

```sh
test -e "/lib/modules/$(uname -r)/build"
sudo /sbin/vboxconfig
sudo modprobe vboxdrv
find "/lib/modules/$(uname -r)" -type f -name 'vbox*.ko*' -print
```

Do not continue until `VBoxManage list hostinfo` succeeds.

## 3. Verify and import the packaged box

Create one working directory per VM. Copy the dated `.box`, its `.sha256` file
and the supplied `Vagrantfile` into it:

```sh
mkdir -p "$HOME/easymesh-lab/0818"
cd "$HOME/easymesh-lab/0818"
ls -lh
sha256sum -c easymesh-lab-0818.box.sha256
```

The exact filename and date may differ. A checksum failure means the transfer
is incomplete or the wrong checksum was supplied; do not import that file.

Register the verified box once under a clear local name:

```sh
vagrant box add --name cmf/easymesh-lab-0818 easymesh-lab-0818.box
vagrant box list | grep '^cmf/easymesh-lab-0818 '
```

Make sure the `Vagrantfile` selects the same name. The supplied consumer file
can also be selected with an environment variable:

```sh
export EASYMESH_BOX_NAME=cmf/easymesh-lab-0818
```

The import is a one-time operation. Later `vagrant up` commands use the local
registered box and the VM's own virtual disk.

## 4. Start the VM and the complete lab

From the directory containing the `Vagrantfile`:

```sh
cd "$HOME/easymesh-lab/0818"
export EASYMESH_BOX_NAME=cmf/easymesh-lab-0818
vagrant up
vagrant status
vagrant ssh
```

On every VM boot, systemd reconstructs the lab in dependency order:

```text
Boardfarm WAN/DHCP and br-wan105
  -> LXD-to-Docker forwarding
  -> hwsim radio pool
  -> controller
  -> extenders, one at a time with onboarding gates
  -> wmediumd
  -> WLAN clients, one at a time with association/export gates
  -> final health hold
```

The first startup on a new workstation can take several minutes. Do not
manually restart individual containers or EasyMesh processes while this is in
progress. Inside the guest, wait for the managed startup and run its acceptance
check:

```sh
sudo easymesh-labctl warm-start
sudo easymesh-labctl check
```

`warm-start` is safe even if the boot service is already running: it waits for
the same service chain instead of starting a competing deployment.

## 5. Know when it is ready

The normal high-level commands are:

```sh
sudo easymesh-labctl status
sudo easymesh-labctl check
```

A fully ready result has all of these properties:

- Boardfarm reports all 60 infrastructure checks passing;
- controller model is `5/15/50/14`;
- topology contains the controller, five agents and ten unique clients;
- `/api/v1/clients` reports ten active clients;
- all ten clients can ping `10.0.0.1` over WLAN;
- wmediumd and its control socket are active; and
- OneWifi, agents, controller and CLI have zero unexpected restarts.

Useful manual inspection commands inside the guest are:

```sh
systemctl --no-pager --full status \
  boardfarm-lab.service \
  easymesh-hwsim-pool.service \
  easymesh-lxd-docker-forward.service \
  easymesh-lab.service

sudo journalctl -u boardfarm-lab.service -b --no-pager
sudo journalctl -u easymesh-lab.service -b --no-pager

docker ps --format 'table {{.Names}}\t{{.Status}}'
ip link show br-wan105
lxc list
pgrep -af wmediumd.patched

curl -fsS http://127.0.0.1:8888/api/v1/topology | jq .
curl -fsS http://127.0.0.1:8888/api/v1/clients | jq .
```

To run Boardfarm's infrastructure-only status report directly:

```sh
cd /home/vagrant/boardfarm-open-0406/boardfarm-lab-staging/lab
BF_LAB_CONFIG=boardfarm-easymesh.json \
BF_INVENTORY=boardfarm-easymesh.json \
  ../../.venv/bin/bf-lab status
```

Do not use `bf-lab teardown,setup` during a Wi-Fi experiment. The managed boot
service uses that operation before EasyMesh starts because replacing
`br-wan105` while `bpibroadband` is attached would tear down its WAN path.

For live startup monitoring in another SSH terminal:

```sh
sudo journalctl -fu boardfarm-lab.service -fu easymesh-lab.service
```

Boardfarm's 60 checks concern its Docker WAN/DHCP environment. They do not by
themselves prove EasyMesh onboarding; the subsequent model, client, traffic
and restart checks provide that proof.

## 6. Open and use the WebUI

The default Vagrant forwarding is private to the workstation:

```text
http://127.0.0.1:18888/
```

To reach it from another trusted machine on the same LAN, bind the forwarded
port to the workstation's network interfaces when starting the VM:

```sh
EASYMESH_BOX_NAME=cmf/easymesh-lab-0818 \
EASYMESH_WEBUI_HOST_IP=0.0.0.0 \
EASYMESH_WEBUI_PORT=18888 \
vagrant up
```

Then browse to `http://WORKSTATION-IP:18888/`. This engineering UI is not
hardened for the public Internet; expose it only on a trusted lab network.
If port 18888 is already occupied, choose another unused host port and keep
guest port 8888 unchanged.

The principal pages are:

- **Network Topology** shows the controller, agents, radios/BSSs and current
  client parents. It polls live topology every two seconds. Dragging changes
  only the drawing. **Optimize Layout** rearranges the drawing; it does not
  optimize Wi-Fi or issue a steer. **Export** saves current topology as JSON,
  SVG or PNG.
- **Devices** lists current devices derived from the controller model.
- **Connected Clients** lists the ten live clients. Signal shows dBm and raw
  RCPI and refreshes every two seconds.
- **Policy Settings** reads and writes the controller's EasyMesh reporting and
  steering policy primitives. These values control reporting and permitted
  agent behavior; they are not a complete autonomous optimization algorithm.

The WebUI is served by the `em_cli` process in `bpibroadband`. For ordinary lab
use, interact with it through the pages and REST endpoints rather than trying
to invoke the daemon as a shell program. Useful read-only API calls are:

```sh
curl -fsS http://127.0.0.1:8888/api/v1/topology | jq .
curl -fsS http://127.0.0.1:8888/api/v1/devices | jq .
curl -fsS http://127.0.0.1:8888/api/v1/clients | jq .
curl -fsS http://127.0.0.1:8888/api/v1/wifipolicy | jq .
```

The topology and client API are good automation interfaces for observing and
verifying a test. `steer.sh` is the supported command-line adapter for an
explicit steering action.

## 7. Run the routine acceptance tests

Run these after every imported-box first boot or VM reboot:

```sh
sudo easymesh-labctl check
sudo easymesh-labctl steer-return
sudo easymesh-labctl steer-scale 3
sudo easymesh-labctl check
```

`steer-return` moves two clients away from and back to their original APs. It
requires command delivery, real client association, controller database and
WebUI topology to agree for all four moves.

`steer-scale 3` performs 30 commanded steers across all ten clients and five
agents while traffic runs. It records command status, link convergence,
database convergence, topology convergence and packet loss. The final `check`
ensures that the lab remains healthy after the test.

Results are retained inside the VM:

```text
/home/vagrant/.local/state/easymesh-vagrant/steering-return.csv
/home/vagrant/.local/state/easymesh-vagrant/steering-scale.csv
/home/vagrant/.local/state/easymesh-vagrant/reboot-acceptance/
```

## 8. Run one manual steering command

First discover the station MAC, its serving BSSID and current 5 GHz targets;
do not copy BSSIDs from another deployment:

```sh
client=wlan-client
lxc exec "$client" -- iw dev wlan0 info
lxc exec "$client" -- iw dev wlan0 link
curl -fsS http://127.0.0.1:8888/api/v1/topology \
  | jq -r '.nodes[] as $node | $node.haulTypes[]?
      | select(.name == "Fronthaul") | .BSSList[]
      | select(.Band == 1) | [$node.name, .BSSID] | @tsv'
```

Then issue the command from the controller:

```sh
sta=02:00:00:00:03:00       # replace with the discovered station MAC
target=02:00:00:51:38:4f    # replace with a current target BSSID
lxc exec bpibroadband -- /usr/bin/steer.sh "$sta" "$target"
```

Verify the actual client link and the WebUI/API parent. A successful command
response alone is not a complete steering pass.

## 9. Run wmediumd RF experiments

Run experiments from the installed repository:

```sh
cd /home/vagrant/git/meta-cmf-bananapi-vcpe
```

### Watch a client's live signal change

Open **Connected Clients**, then run:

```sh
cd gen/wmediumd/configurator
./run-rcpi-monitor.sh wlan-client
```

The wrapper oscillates the selected client's current RF link, keeps traffic
flowing and prints the same RCPI/dBm values fetched by the page every two
seconds. It restores the captured medium state when it exits.

### Watch clients move around the topology

Open **Network Topology**, optionally click **Optimize Layout**, then run:

```sh
cd /home/vagrant/git/meta-cmf-bananapi-vcpe
sudo gen/tests/wmediumd-client-carousel.py --rounds 2
```

The console announces each blackout and arrival using the same stable client
labels shown in the UI. Use `--rounds 0` for a continuous demonstration and
press Ctrl-C once to stop cleanly. This is an RF/reassociation scenario, not an
autonomous optimizer test. A nonzero exit can expose the known residual in
which the real client reaches its requested BSSID but the controller retains
the previous parent. The test preserves that disagreement and restores the
medium; retain its artifact and use the managed restart procedure rather than
retrying until it happens to pass.

### Simulate an extender RF outage and recovery

Choose an extender currently serving at least one client:

```sh
sudo gen/tests/wmediumd-extender-outage.py --extender bpiap-003
```

The test first removes client links to that extender, verifies real and
controller-visible client movement, then isolates the extender backhaul and
restores every touched SNR pair. A known RDK implementation limitation is that
the controller retains a completely isolated extender as known topology; it
does not age the node out during the observation window. Clients move and the
backhaul recovers, but the WebUI should not be expected to remove that node.

For only the client movement portion:

```sh
sudo gen/tests/wmediumd-extender-outage.py \
  --extender bpiap-003 --skip-full-outage
```

### Compile and inspect a configurator scenario

```sh
cd gen/wmediumd/configurator
python3 -m wmdcfg.cli inventory -o /tmp/inventory.json
python3 -m wmdcfg.cli compile scenarios/two-ap-crossover.wmd \
  --inventory /tmp/inventory.json \
  --bind client=wlan-client \
  --bind ap_a=bpibroadband \
  --bind ap_b=bpiap \
  -o /tmp/two-ap-crossover.plan.json
python3 -m wmdcfg.cli status
sudo python3 -m wmdcfg.cli run /tmp/two-ap-crossover.plan.json \
  --output-root /tmp/wmdcfg-runs
```

The configurator uses `/run/wmediumd-control.sock` to apply atomic live SNR
generations. A normal run does not restart wmediumd. It captures the baseline,
reads each generation back and restores all touched links on completion or a
handled interrupt.

## 10. Run developer and recovery tests

Run the configurator unit suite without changing the live medium:

```sh
cd /home/vagrant/git/meta-cmf-bananapi-vcpe/gen/wmediumd/configurator
python3 -m unittest discover -s tests -v
```

Cycle one extender and prove that its service chain, tri-band model, clients
and WebUI state recover:

```sh
cd /home/vagrant/git/meta-cmf-bananapi-vcpe
ap=bpiap                         # choose an extender serving a client
private_bssid=$(lxc exec "$ap" -- iw dev wifi1 info \
  | awk '/addr/{print $2; exit}')
test -n "$private_bssid"
for client in wlan-client wlan-client-{001..009}; do
  lxc exec "$client" -- iw dev wlan0 link \
    | grep -q "Connected to $private_bssid" && echo "$client uses $ap"
done
sudo gen/tests/ap-recovery.sh "$ap" "$private_bssid"
sudo easymesh-labctl check
```

`ap-recovery.sh` is disruptive. Run it only when a brief topology interruption
is acceptable. It requires at least one printed client and deliberately performs
an abrupt container stop. Retain its evidence if it fails. For a clean baseline
after arbitrary experimentation, use a full managed VM restart instead of a
sequence of partial process restarts.

## 11. Capture EasyMesh traffic for Wireshark

The preferred diagnostic capture is decapsulated IEEE 1905/EasyMesh traffic on
`brlan0` inside the controller network namespace. Run inside the VM:

```sh
capture_dir=/home/vagrant/captures
capture_stamp=$(date +%Y%m%d-%H%M%S)
capture_file=$capture_dir/easymesh-$capture_stamp.pcap
capture_tmp=/tmp/easymesh-$capture_stamp.pcap
controller_pid=$(lxc info bpibroadband | awk '/^PID:/ {print $2}')

mkdir -p "$capture_dir"
sudo timeout --signal=INT 300 \
  nsenter --target "$controller_pid" --net \
  tcpdump -i brlan0 -nn -e -s 0 -B 8192 -U \
    -w "$capture_tmp" 'ether proto 0x893a'
sudo install -o "$(id -u)" -g "$(id -g)" -m 0640 \
  "$capture_tmp" "$capture_file"
sudo rm -f "$capture_tmp"
printf '%s\n' "$capture_file"
```

Copy it from the workstation to another machine with `scp`, or use Vagrant's
SSH configuration. Do not bring `hwsim0` up dynamically on an active lab; that
raw 802.11 capture path can disrupt the managed wmediumd transport.

## 12. Shut down, reboot and recover

Run Vagrant lifecycle commands on the workstation in the VM directory:

```sh
vagrant status
vagrant halt       # orderly power-off
vagrant up         # later boot
vagrant reload     # orderly reboot
vagrant ssh
```

After `up` or `reload`:

```sh
sudo easymesh-labctl warm-start
sudo easymesh-labctl check
```

Do not rerun the thin one-time installer in a packaged VM. Do not treat
`vagrant suspend` as an RF-lab reset: it preserves process and kernel state.
Use `halt`/`up` or `reload` when a reconstructed baseline is required.

If a test or interrupted host shutdown leaves the system unclear, collect the
current journals first, then use `vagrant reload` and the two commands above.
The boot service deliberately reconstructs the hwsim, wmediumd, container and
client state in a known order.

## 13. Run more than one copy

Each copy needs its own working directory, VirtualBox VM name and forwarded
WebUI port:

```sh
mkdir -p "$HOME/easymesh-lab/copy-2"
cd "$HOME/easymesh-lab/copy-2"
cp /path/to/Vagrantfile .

EASYMESH_BOX_NAME=cmf/easymesh-lab-0818 \
EASYMESH_VM_NAME=easymesh-lab-copy-2 \
EASYMESH_WEBUI_PORT=18889 \
vagrant up
```

Do not copy another working directory's `.vagrant` directory. The registered
box is the reusable template; every `vagrant up` creates an independent VM.

## 14. Package an accepted VM again

First return the lab to a passing state, reboot-test it and shut it down:

```sh
sudo easymesh-labctl check
exit
vagrant reload
vagrant ssh -c 'sudo easymesh-labctl warm-start && sudo easymesh-labctl check'
vagrant halt
```

Then package and checksum it on the workstation:

```sh
package_stamp=$(date +%m%d)
package_file=easymesh-lab-$package_stamp.box
vagrant package --output "$package_file"
sha256sum "$package_file" | tee "$package_file.sha256"
```

Vagrant has no `vagrant export` command. `vagrant package` creates the portable
box that another user imports with `vagrant box add`. Share the box, checksum
and matching `Vagrantfile` together. A package contains the VM state at the
clean shutdown; it does not contain the workstation's Vagrant registration.

## 15. Remove a copy or uninstall the tools

Destroy only the VM represented by the current working directory:

```sh
cd "$HOME/easymesh-lab/0818"
vagrant destroy
vagrant box remove cmf/easymesh-lab-0818
```

`vagrant destroy` permanently deletes that VM and its mutable disk. The
original `.box` file and other VMs are unaffected.

To uninstall the workstation tools while retaining existing VM and Vagrant
data, use the procedure in [`../thin/README.md`](../thin/README.md#uninstall-from-the-ubuntu-host).

## 16. Where to read more

- [`../../../doc/easymesh/architecture.md`](../../../doc/easymesh/architecture.md): processes, APIs and data flow
- [`../../../doc/easymesh/lab-setup.md`](../../../doc/easymesh/lab-setup.md): direct-host deployment and detailed gates
- [`../../../doc/easymesh/steering.md`](../../../doc/easymesh/steering.md): steering and policy boundaries
- [`../../../doc/easymesh/wmediumd.md`](../../../doc/easymesh/wmediumd.md): medium internals and control interface
- [`../../../doc/easymesh/configurator.md`](../../../doc/easymesh/configurator.md): scenario language and implementation
- [`../../../doc/easymesh/metrics-reporting.md`](../../../doc/easymesh/metrics-reporting.md): policies and live RCPI
- [`../../../doc/easymesh/packet-capture.md`](../../../doc/easymesh/packet-capture.md): complete capture recipes
