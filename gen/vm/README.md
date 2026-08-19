# EasyMesh VM distributions and operator flow

The EasyMesh steering lab is distributed in two forms. New engineers should
normally use the thin form; the precooked form is retained for offline and
recovery use.

| Distribution | Contents | Use case |
| --- | --- | --- |
| [`packaged/`](packaged/) | New-user manual for an already-installed, shareable Vagrant box | Import, operate, test, monitor, recover and repackage the complete lab |
| [`thin/`](thin/) | Ubuntu 24.04, Linux 7.0 and sizing; installs the lab once from GitHub and an artifact server | Normal engineering handoff |
| [`precooked/`](precooked/) | Complete installed lab and all build assets; currently an 11.1 GB box | Offline demonstration, recovery and appliance-builder acceptance |

Shared Boardfarm configuration and lifecycle scripts live in `config/` and
`scripts/`. `consumer/Vagrantfile` runs either packaged box.

The thin handoff is one dated Dropbox tarball such as
`em-artifacts-0817.tar.bz2`. It contains the thin box, four runtime images,
checksums, local installer configuration and the consumer Vagrantfile.
`thin/package-artifacts.sh` creates this tarball for manual upload.

## End-to-end lifecycle

```text
Linux workstation
  -> install VirtualBox + Vagrant
  -> import thin Ubuntu 24.04/Linux 7 box
  -> vagrant up; vagrant ssh
  -> clone codex/0815-clean bootstrap repository
  -> one-time install + first cold start (downloads, builds, deploys, verifies)
  -> check -> WebUI -> steering tests
  -> optional VM snapshot
  -> later VM halt/reboot/reload
  -> automatic warm-start from installed/cached state
  -> check -> continue testing
```

The one-time installer creates the Docker and LXD images, performs the first
complete (cold) lab start, and proves that it works. It leaves the accepted lab
running. A later VM boot is the warm path: no repositories, packages, Python
environment, images or initial deployment are rebuilt.

## Operator commands inside either VM

All normal lifecycle operations use one command:

```sh
sudo easymesh-labctl warm-start       # wait for/complete normal boot start
sudo easymesh-labctl status
sudo easymesh-labctl check
sudo easymesh-labctl steer-return
sudo easymesh-labctl steer-scale 3
```

The installer performs the first cold start in dependency order. A reboot
starts the same installed service chain automatically. Running `warm-start`
after SSH login is safe and waits for any boot-time start already in progress.
For a lab restart use `vagrant reload` on the host. Manual service stop/start is
not an operator workflow because it can preserve stale controller topology.

## WebUI

The default host URL is:

```text
http://127.0.0.1:18888/
```

To make it reachable from a trusted LAN, set the bind address when invoking
Vagrant:

```sh
EASYMESH_WEBUI_HOST_IP=0.0.0.0 \
EASYMESH_WEBUI_PORT=18888 \
vagrant up
```

Then use `http://<virtualbox-host-address>:18888/`. Do not expose this port to
an untrusted network; the lab WebUI is an engineering interface, not a hardened
Internet service.

## Readiness gate

Do not begin steering work until `sudo easymesh-labctl check` passes:

- Boardfarm: 60/60 connectivity checks;
- EasyMesh database: `5/15/50/14`;
- WebUI: controller, colocated agent, four extenders and 10/10 clients;
- zero OneWifi/EasyMesh service restarts; and
- WLAN gateway traffic from all ten clients.

## Operational details that must be decided before handoff

- Host compatibility means x86-64 hardware virtualization, at least 8 logical
  CPU threads, at least 8 GiB allocatable VM memory and enough disk for a
  dynamically allocated 64 GB VM. Installation of VirtualBox and Vagrant is
  part of the thin workflow, not an assumed prerequisite.
- The thin installer needs Internet/DNS/time synchronization, access to the
  private GitHub repositories, and authenticated or signed URLs for four
  checksum-pinned runtime artifacts. The fifth artifact, the custom kernel, is
  already baked into the thin box.
- Avoid host-port collisions when running multiple labs.
- Preserve the generated acceptance logs before destructive experiments.
- Take an optional VirtualBox snapshot only after the one-time installer and
  acceptance check pass; snapshots are recovery aids, not source control.
- Use `vagrant halt` for orderly shutdown. A forced host power-off is recovered
  by the boot service, but is not the normal workflow.

See [`packaged/README.md`](packaged/README.md) when receiving a complete box,
[`thin/README.md`](thin/README.md) for installation from the small base image,
and [`precooked/README.md`](precooked/README.md) for building the complete
offline appliance.
