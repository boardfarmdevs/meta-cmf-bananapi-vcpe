# VM acceptance — 2026-08-17

## Scope

The canonical `gen/vm` builder was provisioned and cold-booted on rev150 using
the pinned inputs in `assets.lock`. The test covered Docker, Boardfarm, Linux
7.0, LXD, hwsim, multichannel wmediumd, the EasyMesh controller, four
extenders, ten WLAN clients, and WebUI topology reporting.

## Result

The final unattended cold-boot reconstruction passed. An earlier diagnostic
boot exposed the `em_cli` ordering defect described below. The accepted run
reported:

- Boardfarm: 20 containers and 60/60 connectivity checks;
- EasyMesh database: 5 devices, 15 radios, 50 BSSs, 14 associated STA rows;
- WebUI: controller, colocated agent, four extenders, and 10/10 live clients;
- traffic: 0% packet loss from each of ten WLAN clients to `10.0.0.1`;
- process stability: zero restarts for every OneWifi and EasyMesh agent, plus
  controller `em_ctrl` and `em_cli`;
- post-convergence hold: 120 seconds with topology and restart counts stable;
- wmediumd multichannel/Linux-7 self-test: all cases passed; and
- guest memory after acceptance: 2.3 GiB used of 5.8 GiB.

The existing ten-case steering matrix also remained 10/10 PASS after the
rebuild. It is reported by the health audit but is not a prerequisite for basic
bring-up acceptance.

## Defects exposed by reboot testing

The initial reboot showed that enabling `em_cli.service` alone did not put it
in the controller's boot transaction. The runtime then waited for a controller
that could never satisfy its complete readiness gate. Controller deployment
now adds an `em_agent.service` drop-in with `Wants=em_cli.service`. On the next
cold boot both jobs were queued together, `em_cli` waited for its agent, and
both became active automatically with zero restarts.

LXD had also auto-refreshed beyond the pinned revision. Its migrated database
was no longer readable after reverting only the executable. The base provisioner
now installs revision 38768 from its local assertion and snap, validates it, and
places an indefinite refresh hold before LXD state is created.

The runtime's previous restart audit crossed the LXC namespace once per unit,
and its nominal stability loop could greatly exceed 120 seconds under Docker
I/O. It now reads all relevant units with one `lxc exec` per container and uses
a wall-clock deadline.

## Boardfarm verification

The accepted environment uses CPython 3.13.15 and 195 installed packages: 190
third-party packages from `boardfarm-requirements.lock` plus five editable,
pinned Boardfarm repositories. `uv pip check` reports that all packages are
compatible.

`BF_LAB_CONFIG=boardfarm-easymesh.json` and
`BF_INVENTORY=boardfarm-easymesh.json` resolve to the staging repository's
`lab/` and `inventories/` trees respectively. `bf-cpe 5` loaded the new
inventory, reached `bpibroadband`, and reported its WAN address as
`10.105.0.100`. A repeated `bf-lab status` passed all 60 checks.

## Boot ownership

The persistent order is:

```text
Docker + LXD
  -> boardfarm-lab.service: bf-lab teardown,setup,status
  -> easymesh-lxd-docker-forward.service
  -> easymesh-lab.service: controller -> extenders -> clients -> wmediumd
  -> topology, stability, restart and traffic gates
```

No nudge or process restart was used during the final cold-boot run.
