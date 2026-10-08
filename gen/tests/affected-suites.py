#!/usr/bin/env python3
"""What a change needs: the lab VM's step and the suite sections that can see it.

    gen/tests/affected-suites.py BASE [HEAD] [--json]

BASE and HEAD are commits of this layer (HEAD defaults to HEAD). A changed submodule
(gen/medium, gen/optimizer) is followed into its own history when both of its commits
are present, and counts as wholly changed when not.

The lab VM's step is the least that brings an accepted lab to HEAD: nothing (documents
only), `build.sh update` (the checkout and its submodules in place, and what a build
installs from them: the medium's daemon, console and radio module, the guest's services
and tools, with a VM restart), `build.sh build` (the VM's other stages), or new BPI
images first (what bitbake reads). The sections are those of run-easymesh-suite.sh that
the changed paths can affect; the static section runs for any change that is not only
documents, and an unknown path runs every section. The soak (12 hours) is never chosen
for one change: it belongs to release points (docs/guides/test-suite.md).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECTIONS = ["static", "webui", "browser", "live", "rooms", "rf", "rf-actions"]
STEPS = ["none", "update", "build", "images"]
SUBMODULES = ("gen/medium", "gen/optimizer")

# (pattern, step, sections): the first pattern that matches a path decides it. Patterns
# match the path from the layer's root (fnmatch: * also crosses "/").
RULES: list[tuple[str, str, tuple[str, ...]]] = [
    # documents and the site: nothing to run
    ("docs/*", "none", ()),
    ("pages/*", "none", ()),
    ("*.md", "none", ()),
    ("gen/medium/docs/*", "none", ()),
    ("gen/optimizer/docs/*", "none", ()),
    # what bitbake reads: new BPI images, then everything
    ("recipes-*", "images", tuple(SECTIONS)),
    ("conf/*", "images", tuple(SECTIONS)),
    ("classes/*", "images", tuple(SECTIONS)),
    ("gen/build/*", "images", tuple(SECTIONS)),
    ("gen/medium/topology-ui/*", "images", ("static", "webui", "browser", "rooms")),
    # the medium: an update makes its daemon, console and radio module and restarts the VM
    ("gen/medium/hwsim/*", "update", ("static", "live", "rooms", "rf", "rf-actions")),
    ("gen/medium/wmediumd/*", "update", ("static", "live", "rooms", "rf", "rf-actions")),
    ("gen/medium/observer/*", "update", ("static", "browser", "live", "rf")),
    ("gen/medium/configurator/worlds/viewer/*", "update", ("static", "browser", "rooms", "rf")),
    ("gen/medium/configurator/*", "update", ("static", "rooms", "rf", "rf-actions")),
    ("gen/medium/*", "update", ("static", "rf")),
    # the optimizer and the rooms
    ("gen/optimizer/acceptance/*", "update", ("static", "rooms", "rf-actions")),
    ("gen/optimizer/*", "update", ("static", "live", "rooms", "rf", "rf-actions")),
    ("gen/rooms/*", "update", ("static", "rooms", "rf")),
    # the guest's services and tools: an update installs them and restarts the VM
    ("gen/vm/scripts/guest/*", "update", ("static", "live", "rooms")),
    ("gen/vm/scripts/30-boardfarm-wan.sh", "update", ("static", "live")),
    ("gen/vm/scripts/50-runtime-service.sh", "update", ("static", "live", "rooms")),
    ("gen/vm/scripts/55-scale-topology.sh", "update", ("static", "live", "rooms")),
    ("gen/vm/scripts/60-scale-steering-test.sh", "update", ("static", "live")),
    ("gen/vm/scripts/61-return-steering-regression.sh", "update", ("static", "live")),
    # the rest of the VM: what only a build makes
    ("gen/vm/scripts/*", "build", ("static", "live", "rooms")),
    ("gen/vm/lxd/*", "build", ("static", "live")),
    ("gen/vm/*", "build", ("static", "live")),
    # the lab's tools, run in the guest from its checkout
    ("gen/tests/*browser*", "update", ("static", "browser")),
    ("gen/tests/*", "update", ("static",)),
    ("gen/explorer/*", "update", ("static", "browser")),
    ("gen/wlan-client*", "update", ("static", "live", "rooms")),
    ("gen/wpa_supplicant/*", "build", ("static", "live", "rooms")),
    ("gen/*", "update", ("static", "live", "rooms")),
    ("tools/*", "update", ("static",)),
    ("examples/*", "none", ()),
]


def classify(path: str) -> tuple[str, tuple[str, ...]]:
    for pattern, step, sections in RULES:
        if fnmatch.fnmatch(path, pattern):
            return step, sections
    return "build", tuple(SECTIONS)        # unknown: everything


def plan(paths: list[str]) -> dict:
    """The step and sections for a list of changed paths."""
    step = "none"
    sections: set[str] = set()
    reasons: dict[str, list[str]] = {}
    for path in paths:
        path_step, path_sections = classify(path)
        if STEPS.index(path_step) > STEPS.index(step):
            step = path_step
        sections.update(path_sections)
        for section in path_sections:
            reasons.setdefault(section, []).append(path)
    if any(classify(p)[0] != "none" for p in paths):
        sections.add("static")
    ordered = [s for s in SECTIONS if s in sections]
    return {"step": step, "sections": ordered, "paths": len(paths),
            "because": {s: sorted(reasons.get(s, []))[:5] for s in ordered}}


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout


def changed_paths(base: str, head: str) -> list[str]:
    paths = []
    for line in git("diff", "--name-only", base, head).splitlines():
        if line in SUBMODULES:
            paths += submodule_paths(line, base, head)
        else:
            paths.append(line)
    return paths


def submodule_paths(submodule: str, base: str, head: str) -> list[str]:
    def pinned(commit: str) -> str | None:
        try:
            return git("rev-parse", f"{commit}:{submodule}").strip()
        except subprocess.CalledProcessError:
            return None
    old, new = pinned(base), pinned(head)
    repository = ROOT / submodule
    if old and new and (repository / ".git").exists():
        try:
            return [f"{submodule}/{p}" for p in
                    git("diff", "--name-only", old, new, cwd=repository).splitlines()]
        except subprocess.CalledProcessError:
            pass
    return [f"{submodule}/<unknown>"]      # not comparable here: wholly changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base")
    parser.add_argument("head", nargs="?", default="HEAD")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = plan(changed_paths(args.base, args.head))
    result["range"] = f"{args.base}..{args.head}"
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    step = {"none": "nothing (documents only)", "update": "gen/vm/lxd/build.sh update",
            "build": "gen/vm/lxd/build.sh build", "images":
            "gen/build/build-images.sh, then gen/vm/lxd/build.sh build"}[result["step"]]
    print(f"{result['range']}: {result['paths']} changed path(s)")
    print(f"lab VM: {step}")
    if result["sections"]:
        acting = " --yes-act" if set(result["sections"]) & {"live", "rooms", "rf", "rf-actions"} else ""
        print(f"suite:  gen/tests/run-easymesh-suite.sh {' '.join(result['sections'])}{acting}")
        for section, paths in result["because"].items():
            print(f"  {section:<10} {', '.join(paths)}")
    else:
        print("suite:  nothing")
    print("soak:   at release points only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
