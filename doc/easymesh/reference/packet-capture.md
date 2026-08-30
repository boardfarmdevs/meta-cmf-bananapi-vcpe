# Packet capture

## Capture points

The lab has two different views of a packet. Choose the view that answers the
question rather than collecting an unnecessarily large trace.

| Capture point | Link type | What it shows | Current status |
| --- | --- | --- | --- |
| `brlan0` in `bpibroadband` | Ethernet | plaintext IEEE 1905/EasyMesh CMDUs from the controller and agents | supported and preferred |
| `brlan0` in one `bpiap*` | Ethernet | the selected agent's local EasyMesh and bridged client traffic | supported |
| `wlan0` in one `wlan-client*` | Ethernet | that client's decrypted data-plane traffic and EAPOL | supported |
| host `hwsim0` | radiotap/802.11 | all simulated management, control and data frames | not safe to enable dynamically with the current launcher |
| wmediumd `-p FILE` | pcapng | frames scheduled by the simulated medium, including modeled ACKs | daemon capability; not enabled by the launcher |

For onboarding, metrics, topology and steering diagnosis, start with the
controller's `brlan0`. It aggregates the 2.4, 5 and 6 GHz EasyMesh transport
after 802.11 decapsulation, so Wireshark can decode the unencrypted IEEE 1905
header and TLVs. A capture on host `any` is less useful because it records the
same frame at several internal virtual interfaces and uses Linux cooked
encapsulation.

The RDK-B containers do not contain `tcpdump`. The host has `dumpcap`,
`tshark` and `tcpdump`; enter only the container's network namespace with
`nsenter`. The host mount namespace is retained. Capture into host `/tmp`
first, then install the completed file under `/home/rev/captures`. This is
necessary because the privileged capture programs drop privileges before
opening their output and cannot create a file below `/home/rev` on the
accepted host configuration.

## Recommended EasyMesh capture

This records five minutes of IEEE 1905/EasyMesh traffic from the controller
bridge as pcapng:

```sh
capture_dir=/home/rev/captures
capture_stamp=$(date +%Y%m%d-%H%M%S)
capture_file=${capture_dir}/easymesh-${capture_stamp}.pcapng
capture_tmp=/tmp/$(basename "$capture_file")
controller_pid=$(lxc info bpibroadband | awk '/^PID:/ {print $2}')

mkdir -p "$capture_dir"
test -n "$controller_pid"

sudo nsenter --target "$controller_pid" --net \
  dumpcap \
    -i brlan0 \
    -f 'ether proto 0x893a' \
    -s 0 \
    -a duration:300 \
    -w "$capture_tmp"

sudo install -o "$(id -u)" -g "$(id -g)" -m 0640 \
  "$capture_tmp" "$capture_file"
sudo rm -f "$capture_tmp"
printf '%s\n' "$capture_file"
```

`0x893a` is the IEEE 1905 EtherType. The trace includes autoconfiguration,
topology discovery/notification, policy configuration, AP Metrics Responses,
client association events, steering requests, steering reports and 1905 ACKs.
The exact set depends on what happens during the capture interval.

To stop an open-ended capture manually, omit `-a duration:300` and press
Ctrl-C. `dumpcap` is preferred for pcapng output and long-running ring buffers.

## tcpdump equivalent

Use this when a classic pcap is preferable:

```sh
capture_dir=/home/rev/captures
capture_stamp=$(date +%Y%m%d-%H%M%S)
capture_file=${capture_dir}/easymesh-${capture_stamp}.pcap
capture_tmp=/tmp/$(basename "$capture_file")
controller_pid=$(lxc info bpibroadband | awk '/^PID:/ {print $2}')

mkdir -p "$capture_dir"
sudo timeout --signal=INT 300 \
  nsenter --target "$controller_pid" --net \
  tcpdump -i brlan0 -nn -e -s 0 -B 8192 -U \
    -w "$capture_tmp" 'ether proto 0x893a'

sudo install -o "$(id -u)" -g "$(id -g)" -m 0640 \
  "$capture_tmp" "$capture_file"
sudo rm -f "$capture_tmp"
```

`-s 0` retains complete CMDUs and TLVs. `-B 8192` gives libpcap an 8 MiB
buffer. `timeout --signal=INT` stops tcpdump cleanly so it writes the final pcap
trailer and statistics.

## Capture one agent or client

Replace the namespace owner and interface while keeping the output on the
host. This example captures all Ethernet traffic on `bpiap-002`'s LAN bridge:

```sh
node=bpiap-002
node_pid=$(lxc info "$node" | awk '/^PID:/ {print $2}')
node_tmp=/tmp/${node}-brlan0.pcapng
node_file=/home/rev/captures/${node}-brlan0.pcapng

sudo nsenter --target "$node_pid" --net \
  dumpcap -i brlan0 -s 0 -a duration:120 \
    -w "$node_tmp"
sudo install -o "$(id -u)" -g "$(id -g)" -m 0640 \
  "$node_tmp" "$node_file"
sudo rm -f "$node_tmp"
```

This example captures the decrypted data plane of one WLAN client:

```sh
client=wlan-client
client_pid=$(lxc info "$client" | awk '/^PID:/ {print $2}')
client_tmp=/tmp/${client}-wlan0.pcapng
client_file=/home/rev/captures/${client}-wlan0.pcapng

sudo nsenter --target "$client_pid" --net \
  dumpcap -i wlan0 -s 0 -a duration:120 \
    -w "$client_tmp"
sudo install -o "$(id -u)" -g "$(id -g)" -m 0640 \
  "$client_tmp" "$client_file"
sudo rm -f "$client_tmp"
```

Add a capture filter when appropriate. Useful examples are:

```text
ether proto 0x893a                         EasyMesh/IEEE 1905 only
ether proto 0x888e                         EAPOL only
host 10.0.0.73                             one client IPv4 address
(ether proto 0x893a) or (ether proto 0x888e)
```

## Correlate a wmediumd scenario

Run the capture and scenario from separate terminals. Start the capture first:

```sh
# Terminal 1: use the recommended five-minute EasyMesh capture above.

# Terminal 2:
cd /home/rev/easymesh-lab/0829-lxd-primary/meta-cmf-bananapi-vcpe/gen/wmediumd/configurator
./run-rcpi-monitor.sh wlan-client
```

Keep the configurator run directory under `/tmp/wmdcfg-runs`. Its event times,
applied generations and restore result provide the RF timeline to compare with
CMDU timestamps in Wireshark.

## Raw 802.11 capture boundary

`hwsim0` is the global mac80211_hwsim monitor and produces radiotap/802.11
frames. It includes beacons, probe/authentication/association exchanges,
EAPOL, data, retries and traffic on every simulated channel. Backhaul data can
still be encrypted, whereas the `brlan0` capture shows its decapsulated
EasyMesh payload.

Do **not** run this on an active lab:

```sh
sudo ip link set hwsim0 up
```

Changing `hwsim0` while patched wmediumd owns the hwsim netlink transport can
terminate wmediumd and block subsequent `iw` operations in the kernel. Raw
capture must therefore be established as part of a tested cold-start sequence,
not added dynamically to a running lab.

wmediumd itself supports `-p FILE` and writes scheduled medium traffic as
pcapng, including modeled ACKs. The current `wmediumd-up.sh` deliberately does
not enable it. Do not start a second daemon or manually replace the managed
daemon during a test. Adding an opt-in capture argument to the launcher,
followed by cold-start, multichannel and restore acceptance, is the preferred
way to make raw WLAN capture operational.

## Read and transfer the trace

Perform a quick host-side check:

```sh
tshark -r "$capture_file" \
  -Y 'eth.type == 0x893a' \
  -T fields \
  -e frame.number -e frame.time -e eth.src -e eth.dst -e frame.len \
  | head
```

Copy the trace to the Wireshark workstation:

```sh
scp rev130:/home/rev/captures/easymesh-YYYYMMDD-HHMMSS.pcapng .
```

Useful Wireshark display filters are:

```text
eth.type == 0x893a
eapol
wlan.fc.type == 0
wlan.addr == 02:00:00:00:03:00
```

The last two apply only to a radiotap/802.11 trace. Wireshark decodes the base
IEEE 1905 header and standardized TLVs; decoding of newer EasyMesh profile TLVs
depends on the installed Wireshark version.

## Acceptance checks

Before relying on a trace:

1. Confirm `controller_pid` is non-empty and `brlan0` exists in that namespace.
2. Confirm dumpcap reports zero kernel drops at exit.
3. Open the file with `tshark -r` before transferring it.
4. Retain the corresponding configurator run directory and controller/agent
   logs when the trace supports a defect report.
5. Record the source commit, boot ID and node MAC identities; hwsim identities
   are regenerated when the lab is redeployed.
