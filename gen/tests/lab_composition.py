#!/usr/bin/env python3
"""The lab's mesh, counted from the lab itself: what its tests expect of the controller.

The RDK lab's five Wi-Fi nodes (the gateway and four Wi-Fi extenders, a fixed design: the
room's backhaul adapter requires them), its extenders on a wired backhaul
(gen/wired-extender.sh: user.easymesh.backhaul=wired) and the OpenSync pods EMOSA presents
(user.emosa.role=pod), all read from LXD in the lab VM, as health-audit.sh counts them.
A test compares the controller's model with these, never with a constant.

    python3 gen/tests/lab_composition.py              the composition, as JSON
    python3 gen/tests/lab_composition.py --native     the lab's own agents (Wi-Fi + wired)
    python3 gen/tests/lab_composition.py --devices    every device in the controller's model
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, field

WIFI_NODES = ("bpibroadband", "bpiap", "bpiap-001", "bpiap-002", "bpiap-003")
EXTENDER = re.compile(r"^bpiap-[0-9]{3}$")


def _lxc(*arguments: str) -> str:
    return subprocess.run(["lxc", *arguments], capture_output=True, text=True, check=True,
                          timeout=30).stdout


@dataclass(frozen=True)
class Composition:
    wifi: int = len(WIFI_NODES)
    wired: tuple[str, ...] = field(default_factory=tuple)
    pods: tuple[str, ...] = field(default_factory=tuple)

    @property
    def native(self) -> int:
        """The lab's own EasyMesh agents: its Wi-Fi nodes and its wired extenders."""
        return self.wifi + len(self.wired)

    @property
    def devices(self) -> int:
        """Every device in the controller's model: the lab's agents and the pods' agents."""
        return self.native + len(self.pods)

    def native_model(self, clients: int) -> dict[str, int]:
        """The controller's model of the lab's own agents (health-audit.sh's counts, the pods
        and their rows left out): three radios and ten BSSes an agent, the clients and each
        Wi-Fi extender's backhaul station associated."""
        return {"devices": self.native, "radios": 3 * self.native, "bss": 10 * self.native,
                "associated": clients + self.wifi - 1}

    def topology(self, clients: int) -> dict[str, int]:
        """The WebUI topology: the controller and every device a node, every device but the
        gateway's agent one edge to its parent (a wired extender's an Ethernet one), the
        gateway's agent one to the controller."""
        return {"nodes": 1 + self.devices, "clients": clients, "edges": self.devices}

    def as_dict(self) -> dict:
        return {"wifi": self.wifi, "wired": list(self.wired), "pods": list(self.pods),
                "native": self.native, "devices": self.devices}


def composition(lxc=_lxc) -> Composition:
    """The lab VM's composition, from LXD: its running instances and their settings."""
    running = [line.split(",")[0] for line in lxc("list", "-c", "ns", "--format", "csv").splitlines()
               if line.endswith(",RUNNING")]
    wired = tuple(sorted(
        (name for name in running
         if EXTENDER.match(name) and lxc("config", "get", name, "user.easymesh.backhaul").strip() == "wired"),
        key=lambda name: int(name.rsplit("-", 1)[1])))
    pods = tuple(sorted(name for name in running
                        if lxc("config", "get", name, "user.emosa.role").strip() == "pod"))
    return Composition(wired=wired, pods=pods)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--native", action="store_true", help="the lab's own agents (Wi-Fi + wired)")
    group.add_argument("--devices", action="store_true", help="every device in the controller's model")
    args = parser.parse_args()
    lab = composition()
    print(lab.native if args.native else lab.devices if args.devices else json.dumps(lab.as_dict()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
