# EasyMesh lab deployment models

This reference compares the three supported ways to host the EasyMesh research
lab: directly on a Linux host, in a VirtualBox VM managed by Vagrant, and in an
LXD virtual machine. The EasyMesh experiment is intentionally the same in all
three cases. The deployment model changes isolation, lifecycle, portability,
performance, and who owns the simulated-radio kernel.

For the currently accepted source revision, image hashes, topology, and known
limitations, see [current state](../current-state.md).

## One lab, three outer boundaries

```mermaid
flowchart TB
    EXP["Same EasyMesh experiment<br/>controller + colocated agent<br/>four extender agents<br/>10 private + 10 IoT clients<br/>hwsim + wmediumd"]

    BM["Bare-metal host<br/>Ubuntu + Linux 7<br/>LXD system containers"]
    VB["VirtualBox guest<br/>Ubuntu 24 + Linux 7<br/>nested LXD containers"]
    LV["LXD VM guest<br/>Ubuntu 24 + Linux 7<br/>nested LXD containers"]

    H1["Host kernel owns hwsim"]
    H2["Guest kernel owns hwsim"]
    H3["Guest kernel owns hwsim"]

    BM --> H1 --> EXP
    VB --> H2 --> EXP
    LV --> H3 --> EXP
```

The invariant lab inside the selected boundary contains:

- Docker with the lean Boardfarm `ca-desk6` DHCP/NAT service and `br-wan101`;
- LXD system containers for `bpibroadband`, four extenders, and 20 clients;
- Linux 7 with the patched 32-radio, three-channel `mac80211_hwsim` module;
- patched multichannel wmediumd, its configurator, and the wmediumd Console;
- the EasyMesh WebUI/API, steering tools, optimizer, and acceptance tests; and
- persistent node identities and `/nvram` data across ordinary restarts.

This common inner shape is important. Results can be compared across deployment
models only when the source revision, BPI images, kernel, radio identities,
wmediumd build and configuration, topology, and scenario inputs are identical.

## Configuration at a glance

| Property | Bare metal | VirtualBox/Vagrant | LXD VM |
| --- | --- | --- | --- |
| Outer host | Ubuntu 24.04 with Linux 7 | Ubuntu 22.04 or 24.04 with VirtualBox and Vagrant | Ubuntu 24.04 with LXD VM support |
| Lab kernel | Host kernel | Ubuntu 24.04/Linux 7 guest kernel | Ubuntu 24.04/Linux 7 guest kernel |
| BPI/client boundary | LXD system containers on the host | LXD system containers nested in the guest | LXD system containers nested in the guest |
| VM implementation | None | VirtualBox `VBoxHeadless` | LXD-managed QEMU/KVM |
| Default allocation | Uses host resources directly | 6 vCPUs, 6144 MiB RAM, dynamic 64 GB disk | 6 vCPUs, 6 GiB RAM, dynamic 64 GiB disk |
| UI exposure | Host ports 8888 and 8890 | Vagrant forwards host 18889 and 18890 | LXD NAT proxy devices expose host 18889 and 18890 |
| Boot policy | Lab does not automatically reconstruct after a host reboot | Guest automatically reconstructs the lab | Guest automatically reconstructs the lab |
| Portable artifact | No single-machine image | Vagrant `.box` release bundle | LXD image export plus checksums |

The VM resource values are release defaults, not a claim that the lab consumes
all six CPUs continuously. They provide enough concurrency for Docker,
nested LXD, five EasyMesh nodes, 20 clients, wmediumd, both UIs, and acceptance
tests. Measurements, rather than the defaults, should drive a smaller profile.

## Bare-metal lab

### How it is configured

Ubuntu and Linux 7 run directly on the physical host. The host loads the
patched hwsim module, owns every simulated wiphy, runs wmediumd, Docker and
Boardfarm, and hosts all BPI and client LXD containers. The WebUI and Console
listen directly on host ports 8888 and 8890.

Provisioning follows the direct-runtime procedure in
[lab setup and operation](../guide/operations.md). The host must provide the
matching Linux headers/module, LXD, Docker, the single Boardfarm repository,
the controller and extender images, and the source checkout.

An ordinary physical-host reboot must not silently start the complete lab.
The operator starts or reconstructs it explicitly after confirming that host
networking, Boardfarm, hwsim, LXD, and the desired experiment state are ready.
This avoids an engineering workstation unexpectedly consuming radio, CPU, and
memory resources after every reboot.

### Advantages

- Lowest virtualization overhead and best packet-processing headroom.
- Direct access to the hwsim kernel, debugfs, netlink, namespaces, captures,
  wmediumd, and LXD state.
- Fastest environment for kernel, Wi-Fi HAL, wmediumd, and timing diagnosis.
- No outer VM agent, proxy, virtual disk, or nested-container control path.
- Best performance reference when comparing another deployment model.

### Disadvantages

- The host kernel and networking are part of the experiment and are easier to
  disturb with unrelated host changes.
- hwsim identities, Docker bridges, LXD networks, and host services share one
  operating system and require disciplined ownership.
- It is not distributed as one importable appliance; a new host needs a full
  installation and provisioning pass.
- Host reboot recovery is intentionally operator-driven.
- A failed or destructive experiment has the largest blast radius.

### Best use

Use bare metal for development, maximum scale, performance baselines, kernel
and medium debugging, and diagnosis of failures that might be caused by an
outer hypervisor or nested LXD.

## VirtualBox/Vagrant appliance

### How it is configured

VirtualBox provides an Ubuntu 24.04/Linux 7 guest. Vagrant owns VM creation,
SSH, resource settings, and host-to-guest port forwarding. Inside the guest,
Docker provides Boardfarm and nested LXD owns the same BPI and client system
containers as the bare-metal lab. The guest kernel, not the workstation
kernel, owns hwsim and wmediumd.

The complete release is a `.box` plus a generic `Vagrantfile`, checksums,
release notes, and an operator README. Installation and operation are described
in the [packaged VirtualBox guide](../../../gen/vm/packaged/README.md). Host
addresses and ports are environment overrides; they are not baked into the
box.

The guest's systemd chain reconstructs Boardfarm, the hwsim pool, controller,
extenders, wmediumd, and clients after a VM boot. The physical host itself does
not run those inner services.

### Advantages

- Most familiar portable handoff for engineers who do not operate LXD hosts.
- A release bundle contains the complete installed and accepted lab.
- The guest kernel and radio state are isolated from the workstation kernel.
- Vagrant gives a small, repeatable import/start/SSH/halt interface.
- VirtualBox snapshots and immutable base boxes make rollback straightforward.
- The same artifact works on supported Ubuntu 22.04 and 24.04 workstations.

### Disadvantages

- VirtualBox kernel modules must match the workstation kernel and can be
  blocked by Secure Boot.
- The complete `.box` is a multi-gigabyte artifact and each mutable VM consumes
  additional disk space.
- Virtual CPU scheduling and nested LXD add latency and reduce maximum packet
  throughput compared with bare metal.
- Fixed VM resource allocation can reserve substantially more memory than an
  idle experiment needs.
- Vagrant port-forward collisions must be managed when several labs run on one
  host.
- VirtualBox is a separate virtualization administration stack alongside LXD.

### Best use

Use VirtualBox/Vagrant as the broadly portable distribution and demonstration
baseline, particularly when the recipient has a supported Ubuntu workstation
but is not expected to administer a native LXD environment.

## LXD VM appliance

### How it is configured

The host's LXD launches an Ubuntu 24.04 virtual machine with KVM acceleration.
LXD manages the VM, but the running VM is still a QEMU/KVM process. Inside the
guest, a second LXD instance owns the BPI and client system containers. This is
a nested-LXD design, not an LXD system container with host-owned radios.

The guest kernel owns hwsim and wmediumd, preserving the same radio boundary as
the VirtualBox appliance. LXD NAT proxy devices expose the WebUI and Console.
The builder detects the host's default-route address unless the operator
overrides it, and it stores no site-specific host address inside the guest.

The current builder, lifecycle, port, snapshot, and export commands are in the
[native LXD appliance guide](../../../gen/vm/lxd/README.md). A clean build uses
commit-bounded Git bundles and checksum-verified images, reboots the appliance,
runs its health gate, and only then creates the accepted snapshot.

### Advantages

- Uses one host management system for VM lifecycle, storage, networks,
  snapshots, images, and port proxying.
- Keeps the Linux 7/hwsim kernel isolated inside the appliance.
- Avoids VirtualBox kernel modules, Vagrant state, and a second host VM tool.
- LXD commands give concise automated start, stop, snapshot, publish, export,
  and delete operations.
- Fits naturally on existing LXD build and lab hosts.
- Preserves the same nested container names and operator experience as the
  VirtualBox guest.

### Disadvantages and qualification risks

- It still pays VM and nested-LXD overhead; replacing VirtualBox with LXD does
  not remove QEMU/KVM or make the guest a system container.
- The outer LXD agent and the inner LXD daemon add a control path that does not
  exist on bare metal.
- Command bursts must not create unbounded nested `lxc exec` websocket
  sessions. Lifecycle and test tools must reuse or bound executor calls and
  fail cleanly if the inner daemon is unavailable.
- Recovery ordering spans the outer VM, guest systemd, Docker, guest LXD,
  hwsim, wmediumd, and EasyMesh. Timeouts and stop behavior must remain bounded
  at every layer.
- An LXD image is convenient for LXD users but is a less universal external
  handoff than a Vagrant box.
- The host needs working KVM virtualization and enough memory and storage for
  the VM in addition to any other LXD workloads.

### Best use

Use the LXD VM on LXD-native engineering infrastructure after it passes the
same behavioral gates as the portable VirtualBox release. It is the strongest
candidate for the canonical managed appliance, while bare metal remains the
debug/performance reference and VirtualBox remains the general handoff format.

## Why an LXD system container is not the selected appliance

A privileged outer LXD system container would share the host kernel. Its
hwsim wiphys would therefore be created by the host and would have to cross an
outer container namespace and then an inner BPI container namespace. Kernel
version, module lifetime, radio ownership, device permissions, and recovery
would no longer be appliance-local.

That design may use fewer resources, but it changes the experimental boundary
and increases radio-lifecycle fragility. It should be evaluated separately; it
must not be treated as a smaller implementation of the LXD VM.

## Comparative decision matrix

| Criterion | Bare metal | VirtualBox/Vagrant | LXD VM |
| --- | --- | --- | --- |
| Runtime performance | Best | Good; hypervisor overhead | Good; QEMU/KVM overhead |
| Kernel/radio isolation | Low | High | High |
| Wi-Fi/kernel debugging | Best | Requires guest access | Requires guest access |
| External portability | Installation procedure | Best current appliance bundle | Good for LXD-equipped hosts |
| Clean rollback | Host-specific | Box plus snapshot | Image plus snapshot |
| Host tool complexity | Docker + LXD | VirtualBox + Vagrant | LXD only on host |
| Inner orchestration | Direct LXD | Nested LXD | Nested LXD |
| Automatic lab start | Deliberately disabled | Enabled in guest | Enabled in guest |
| Maximum scale potential | Highest | Resource constrained by VM | Resource constrained by VM |
| Failure isolation | Lowest | High | High |
| Current strategic role | Debug/performance reference | Portable release baseline | Candidate managed appliance |

No optimizer or steering result should depend on the deployment model. A
repeatable difference between models is a lab defect or a measurement that
must be explained before the result is used.

## LXD VM viability gate

LXD VM is viable only when it passes all of the following from a clean image
and after an export/import onto a second LXD host:

1. Boot the VM and automatically reach the complete manifest-defined topology
   without an operator entering the guest.
2. Report healthy Boardfarm WAN/DHCP, 32 stable hwsim radios, one wmediumd,
   both UIs, all EasyMesh nodes, every client association, and every client
   data path.
3. Preserve permanent PHY, MAC, AL-MAC, RUID, client, and `/nvram` identities
   across VM and individual-node restarts.
4. Start, stop, and restart each provisioned node without regenerating the
   medium, restarting unrelated nodes, or creating duplicate controller model
   records.
5. Pass the steering matrix, manual named steering, multihop, RF scenario,
   outage/recovery, optimizer, and topology restoration tests.
6. Survive repeated outer VM reboot and warm-start cycles with bounded startup
   time and no manual repair.
7. Exercise sustained sequential and controlled-concurrency nested LXD
   operations without websocket timeouts, stuck executor processes, leaked
   systemd scopes, or an unresponsive inner daemon.
8. Complete the required soak profile without service restarts, controller
   model drift, process growth, memory growth, journal growth, or cumulative
   packet-processing degradation.
9. Keep WebUI, Console, steering, and health-check command latency within the
   declared release limits while wmediumd carries the selected traffic load.
10. Export, import, configure site-local proxy addresses, start, check, and
    delete using only the documented outer-host commands.

Record wall-clock startup time, CPU time, peak and steady-state memory, disk
usage, wmediumd packet rates/drops, command latency, container restart counts,
and failed operations for all three models. Bare metal is the performance
control; VirtualBox is the portability control. The LXD VM should be selected
as the default managed appliance only after functional parity and acceptable
resource deltas are demonstrated.

## 0828 qualification campaign

The 0828 comparison uses four physical systems. Two direct deployments are
required because a result from the small rev130 system alone cannot distinguish
deployment overhead from CPU or memory pressure. rev120 is the like-for-like
bare-metal performance control for the VM profiles; rev130 is the constrained
host acceptance target.

| Target | Deployment under test | Product / board | CPU | Logical CPUs | RAM | Host OS and kernel |
| --- | --- | --- | --- | ---: | ---: | --- |
| rev120 | Bare metal | Intel NUC10i7FNH / NUC10i7FNB | Core i7-10710U, 6 cores / 12 threads | 12 | 62 GiB | Ubuntu 24.04.4, Linux 7.0.0-30 |
| rev130 | Bare metal | Intel NUC6CAYH / NUC6CAYB | Celeron J3455, 4 cores / 4 threads | 4 | 7 GiB | Ubuntu 22.04.4, Linux 7.0.0-28 |
| rev140 | LXD VM | Intel NUC12WSKi7 / NUC12WSBi7 | Core i7-1260P, 12 cores / 16 threads | 16 | 62 GiB | host Ubuntu 20.04; guest Ubuntu 24.04/Linux 7.0.0-30 |
| rev150 | VirtualBox/Vagrant | x86-64 host | Ryzen 7 8745HS, 8 cores / 16 threads | 16 | 25 GiB | host Ubuntu 22.04; guest Ubuntu 24.04/Linux 7.0.0-30 |

The rev140 host OS is not part of the radio experiment: Linux 7 and hwsim run
inside the LXD VM. It remains relevant to outer LXD/QEMU resource and lifecycle
behavior. The same distinction applies to rev150 and its VirtualBox guest.

### Pinned inputs

Every result row must name, rather than imply, these inputs:

| Input | Required 0828 value |
| --- | --- |
| Source branch | `codex/0828-clean` |
| Source commit | Record the exact 40-character commit for the campaign |
| Controller image | `X86EMLTRBPIBB_rdk-next_20260828160826.rootfs.lxc.tar.bz2` |
| Controller SHA-256 | `9a4c432c857dbbf80a68c5b7835d7d0ba39327919dc53becc3c5a9eeb78d51cd` |
| Extender image | `X86EMLTRBPIAP_rdk-next_20260828161337.rootfs.lxc.tar.bz2` |
| Extender SHA-256 | `8e8ffbfe4b2404dfc9ae19ab27b0eab6243d3bc55d443ceca0d269d36b3e5d18` |
| Boardfarm | single `boardfarm-lab-staging` repository, `ca-desk6.json` |
| hwsim | 32 radios, three channels, `regtest=5`, patched module hash recorded per kernel |
| Topology | controller plus colocated agent, four extenders, 10 private clients, 10 IoT clients |

If a fix changes the source commit during the campaign, update every target to
that commit and rerun the affected gates. Do not combine results from a dirty
checkout with release results.

### Measurement phases

Each target is measured in the same order:

1. **Outer idle:** lab stopped; record host load, memory, swap, disk, temperature
   when available, and hypervisor processes.
2. **Cold start:** start from all lab nodes stopped and measure time to the full
   health gate. VM targets start from a powered-off VM and use automatic guest
   reconstruction. Bare-metal targets use an explicit operator start.
3. **Ready idle:** hold the complete lab without a scenario and sample CPU,
   memory, process PSS/RSS, LXD instance use, disk, journal growth, wmediumd
   counters, and API latency.
4. **Traffic:** run the same 20-client gateway traffic profile and record loss,
   throughput where selected, host CPU, guest CPU, and wmediumd packet/drop
   rates.
5. **Control:** run named steering, the steering matrix, star/branch/chain
   multihop transitions, and optimizer smoke tests. Record command latency,
   physical association, controller convergence, WebUI convergence, and
   restoration.
6. **Lifecycle:** restart individual nodes and the complete runtime. For VM
   targets also reboot the outer guest and verify automatic reconstruction.
7. **Soak:** run the declared bounded soak profile and compare initial/final
   process counts, PSS, database counts, journals, packet loss, and command
   responsiveness.

### Results table

The table is completed only from retained command output and machine-readable
evidence. `PASS` means every functional gate passed; it does not mean the host
had the lowest resource use.

| Result | rev120 bare metal | rev130 bare metal | rev140 LXD VM | rev150 VirtualBox |
| --- | --- | --- | --- | --- |
| Exact source/image/module provenance | Measurement in progress | Measurement in progress | Measurement in progress | Measurement in progress |
| Clean/cold start | Measurement in progress | Measurement in progress | Measurement in progress | Measurement in progress |
| Startup time to complete health | — | — | — | — |
| Model and live clients | — | — | — | — |
| 20/20 gateway traffic | — | — | — | — |
| Named steer and matrix | — | — | — | — |
| Star/branch/chain multihop | — | — | — | — |
| Optimizer smoke tests | — | — | — | — |
| Ready-idle host CPU | — | — | — | — |
| Ready-idle lab CPU | — | — | — | — |
| Host/guest memory delta | — | — | — | — |
| BPI EasyMesh process PSS | — | — | — | — |
| Disk/artifact footprint | — | — | — | — |
| Complete restart/reconstruction | — | — | — | — |
| Executor/lifecycle errors | — | — | — | — |
| Soak result | — | — | — | — |
| Overall 0828 result | In progress | In progress | In progress | In progress |

Report CPU both as consumed logical CPUs and as a percentage of total host
capacity. Report memory both in GiB and as a percentage of host RAM. VM rows
must separate the outer QEMU/VirtualBox process from measurements inside the
guest. These normalizations prevent the rev130 hardware limit from being
misreported as a bare-metal architectural cost.

### Follow-on prplMesh control

After the RDK campaign is complete, run the same LXD-VM, radio, topology,
traffic, lifecycle, and resource method against prplMesh. Keep those results in
a separate stack-comparison report. If prplMesh is stable under the same
LXD-VM, nested-LXD, hwsim, and wmediumd boundaries while RDK is not, the shared
virtualization boundary is less likely to be the root cause. The remaining
differences must then be isolated across OneWifi, the RDK Wi-Fi HAL adapters,
the EasyMesh controller/agent implementations, their database/model paths,
and the volume and pattern of management commands.

## Recommended operating policy

- Keep experiment manifests, source and image hashes, tests, and acceptance
  criteria identical across all deployment models.
- Use bare metal to determine whether a failure belongs to the EasyMesh stack,
  hwsim/wmediumd, or VM/nested-LXD orchestration.
- Keep VirtualBox/Vagrant releaseable while LXD VM qualification is in
  progress; do not make external users depend on an unaccepted candidate.
- Prefer the LXD VM for LXD-native infrastructure after the viability gate
  passes.
- Auto-start the complete lab only inside a dedicated lab VM. A bare-metal
  engineering host must require an explicit lab start after reboot.
- Treat snapshots and exported images as reproducible delivery artifacts, not
  as substitutes for source, image provenance, manifests, or acceptance logs.

The runtime resilience contract common to every model is defined in
[live lab resilience and radio inventory design](lab-resilience-design.md).
