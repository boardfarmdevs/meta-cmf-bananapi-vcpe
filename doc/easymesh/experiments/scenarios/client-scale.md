# WLAN client cohorts and scale

## Purpose

The lab must grow without changing its operating model every time more clients
are required. Client count, SSID cohort and test intensity are therefore
separate inputs:

| Profile | Private clients | IoT clients | Total | State |
| --- | ---: | ---: | ---: | --- |
| `small` | 10 | 10 | 20 | routine accepted profile |
| `medium` | 25 | 25 | 50 | bounded cold reconstruction accepted in the isolated Linux 7 evaluation VM |
| `stress` | 50 | 50 | 100 | provisioner and 128-radio hwsim bound are ready; duration acceptance is pending |

Twenty clients remain the routine policy-development profile. Fifty clients
now pass bounded cold reconstruction with userspace wmediumd and the optional
kernel backend. That is not a duration soak. One hundred clients remain a
capacity milestone, not a claim of full-lab stability.

The profiles use the same deterministic global indexes:

```text
wlan-client       index 0
wlan-client-001   index 1
...
wlan-client-099   index 99
```

Each container also records `user.easymesh.cohort`, `ssid`, `security` and a
cohort-local `ordinal` in its LXD metadata. Tests and the WebUI use that intent
instead of guessing a role from a MAC address.

## Current 20-client topology

```text
                         EasyMesh controller
                                |
             +------------------+------------------+
             |                  |                  |
      colocated Agent       four extenders     external optimizer
             |                  |              observes all clients
             +---------+--------+                    |
                       |                             |
       private_ssid: STA-01 ... STA-0A               |
       iot_ssid:     IOT-01 ... IOT-0A               |
                       |                             |
              mac80211_hwsim radios <---- control --+
                       |
              one patched wmediumd
```

The WebUI renders `iot_ssid` stations with the IoT icon and `IOT-xx` label.
Private stations retain the client icon and `STA-xx` label. This is only a
presentation distinction; both cohorts remain ordinary EasyMesh fronthaul
stations and can be observed, steered and subjected to wmediumd RF scenarios.

## Provisioning

The distributable LXD appliance locks one profile during first import. Ordinary
operation must not convert a running 20-client appliance into 50 or 100 clients
with the pool helper. Import a separate VM and select the desired profile as
described in [portable lab releases](../../reference/portable-lab-releases.md).
The commands below are engineering/provisioning interfaces and are not the
normal appliance lifecycle.

To inspect plans in an appliance, enter the outer VM as root and then use its
repository:

```sh
VM=rdkeasymesh-20-0902
lxc exec "$VM" -- bash

cd /home/easymesh/git/meta-cmf-bananapi-vcpe/gen
```

The first two commands run on the outer host; the `cd` and all commands below
run inside the VM. Root is needed for the snap-packaged nested LXD client.

Preview a profile without changing the lab:

```sh
cd gen
./wlan-client-pool.sh plan --profile small
./wlan-client-pool.sh plan --profile medium
./wlan-client-pool.sh plan --profile stress
```

On a development host, create or resume the selected engineering profile:

```sh
./wlan-client-pool.sh up --profile small
./wlan-client-pool.sh status
```

The operation is intentionally resumable. A running client is retained only
when its cohort, SSID, security, live association and IPv4 address all match
the requested plan. A missing or inconsistent client is recreated. This keeps
its radio and identity stable when a partially completed 20- or 50-client run
is resumed.

wmediumd has a fixed registration set for each daemon invocation. The pool
helper therefore stops it, creates and verifies clients over hwsim's built-in
medium, and starts it once after the complete active-radio set exists. An exit
trap restores wmediumd after a failed or interrupted provisioning attempt.
Creating a single client with `wlan-client.sh` still refreshes wmediumd by
itself.

The client startup hook treats DHCP as a replacement transaction. It flushes
an old global WLAN address before invoking BusyBox `udhcpc`, preventing a
recovery retry from retaining the prior lease as a secondary address. The hook
is refreshed even when an older `wlan-client-base` image alias is reused.

On a development host, remove the selected profile's clients:

```sh
./wlan-client-pool.sh down --profile small
```

This is destructive for those disposable client containers, but does not
remove the controller, extenders or their preserved `/nvram` identities.

## IoT SSID security reality

The current HWSIM OneWifi build exposes `iot_ssid` as a hidden WPA2-PSK BSS.
The Reset model expresses the physical-platform SAE/PMF intent, while the HWSIM
compatibility patches deliberately downgrade unsupported WPA3 defaults.
Directed scan evidence from the live BSS consequently rejects an SAE network
for key-management and MFP mismatch. The client helper uses `scan_ssid=1` and
WPA2-PSK for the accepted IoT cohort. Explicit `--security sae` remains
available for a future HWSIM image that actually advertises SAE/PMF.

Do not describe the present IoT cohort as WPA3 until the beacon/probe response,
association and reconnect path have been independently accepted.

## Radio capacity

Five mesh nodes consume five hwsim radios. The current requirements are:

| Profile | Active radios required | Provisioned pool |
| --- | ---: | ---: |
| small | 25 | 32 |
| medium | 55 | 64 |
| stress | 105 | 128 with the optional lab patch; full profile not yet accepted |

wmediumd materializes directed pair state for the active radios even though the
generated configuration writes only non-default links. That state grows as
`N × (N - 1)`:

| Profile | Active radios | Directed pair cells |
| --- | ---: | ---: |
| small | 25 | 600 |
| medium | 55 | 2,970 |
| stress | 105 | 10,920 |

The pool must be selected while every hwsim-owning container is stopped; never
reload `mac80211_hwsim` underneath a running BPI or WLAN client. An already
loaded 32- or 64-radio pool is treated as authoritative by the helpers.

The optional lab patch now raises the static hwsim load bound to the existing
128-radio kernel-medium identity limit. A controlled 105-radio fan-out test
passed with both userspace wmediumd and the kernel backend at a paced 5 Mbit/s
broadcast load. That result proves radio creation and medium fan-out, not a
fully provisioned 100-client EasyMesh topology. Stable naming, LXD ownership,
onboarding, controller-model size, traffic, teardown and cold reconstruction
remain part of the full stress-profile gate.

## Acceptance gates

A profile passes only when all of the following agree:

1. every requested client container is running, associated to its intended
   SSID and owns exactly one global IPv4 address that no other client owns;
2. `/api/v1/topology` contains the exact unique private and IoT counts;
3. the controller `STAList` contains `clients + 4` associated records, where
   four are extender backhauls;
4. all clients reach `10.0.0.1` with no unexplained loss;
5. OneWifi, agent, controller and CLI restart counters remain zero;
6. private and IoT carousel scenarios each converge and restore the medium;
7. wmediumd RSS, CPU, netlink socket drops and scenario lateness remain inside
   the profile's recorded envelope; and
8. the duration-bound churn soak passes without topology drift, stale client
   ownership, coredumps, OOM events or restoration failure.

The accepted small-profile result is defined in
[current state](../../current-state.md). The bounded medium-profile evidence is
under [`kernel-medium-0829`](../results/kernel-medium-0829/scale-50/). Duration
and RF-churn acceptance remains a separate gate in
[soak acceptance](soak-acceptance.md).

## wmediumd capacity and overload

wmediumd is currently one process with one execution thread. Its default file
is sparse: it lists the active radio identities and only explicit baseline
links, while unspecified pairs use `default_snr`. Scenario control updates are
also sparse and batched into generations. This avoids constructing a complete
pair table for every movement, but frame delivery still has to consider the
eligible simulated receivers. Client count and offered WLAN traffic therefore
both matter.

The accepted 50-client profile produces 55 station identities and 2,970
directed links. Its bounded cold run does not establish sustained packet-rate
or duration capacity, and it does not establish capacity for 100 full client
containers. The soak sampler records peak RSS, lifetime CPU, thread count and
the matching netlink socket drop counter so overload becomes a test failure
instead of a visual impression.

If a larger profile approaches one full CPU, accumulates netlink drops or
misses scenario deadlines, apply remedies in this order:

1. keep RF overrides sparse and send one batched generation per scenario tick;
2. make traffic profiles explicit, avoiding accidental broadcast storms and
   unrealistic always-on traffic from every client;
3. dedicate/pin a host CPU to wmediumd and keep unrelated build or VM work off
   the runtime host;
4. profile the frame receive/delivery loop and optimize lookup, allocation and
   logging hot paths before changing semantics;
5. split independent experiments across lab VMs when they do not require one
   shared mesh; and
6. only then evaluate a more invasive parallel or sharded medium design.

CPU affinity can reduce scheduling jitter but cannot increase the capacity of
a saturated single-thread loop. Multiple wmediumd processes also cannot simply
share one hwsim radio set; that would require an explicit isolation design.

## Progression

The 64-radio, five-node, 50-client cold gate is complete. The next scale work
is to run declared private and IoT traffic with RF churn for a bounded duration,
record scenario lateness and netlink drops, and decide whether the medium
profile has enough margin for routine optimizer use.

Only then should a host with substantially more than 8 GiB available to the
lab attempt the complete 100-client profile. The 105-radio mechanism is
available and has passed a synthetic 5 Mbit/s fan-out test, but it must not be
confused with end-to-end client, controller-model or long-duration acceptance.
