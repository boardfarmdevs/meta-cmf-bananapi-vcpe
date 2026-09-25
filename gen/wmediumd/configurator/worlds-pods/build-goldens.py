#!/usr/bin/env python3
"""Build or check the pod-variant rooms: every native Golden World with two
OpenSync pods (EMOSA adapter) added as APs.

    python3 worlds-pods/build-goldens.py [--check|--write]

Each native golden (../worlds/golden/ID.world.json) names its layout and
mobility. The pod variant uses the same mobility, the native layout plus the
pods at pod-positions.json, as layout NAME-pods, and keeps the world ID, so a
test that addresses a room by ID runs the pod variant when pointed at this root.
"""
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from wmdcfg.world import compile_world, load_json  # noqa: E402

NATIVE = HERE.parent / "worlds"


def pod_layout(native: dict, positions: dict) -> dict:
    layout = copy.deepcopy(native)
    layout["name"] = native["name"] + "-pods"
    layout["tags"] = sorted(set(native.get("tags", [])) | {"opensync-pods"})
    for role in ("pod_1", "pod_2"):
        layout["nodes"].append({"role": role, "kind": "fronthaul_ap", "position": positions[role]})
    return layout


def build() -> dict[str, str]:
    positions = load_json(HERE / "pod-positions.json")["layouts"]
    files = {}
    for path in sorted((NATIVE / "golden").glob("*.world.json")):
        native = load_json(path)
        layout = pod_layout(load_json(NATIVE / "layouts" / f"{native['layout']}.json"), positions[native["layout"]])
        files[f"layouts/{layout['name']}.json"] = json.dumps(layout, indent=2) + "\n"
        world = compile_world(layout, load_json(NATIVE / "mobility" / f"{native['mobility']}.json"))
        files[f"golden/{path.name}"] = json.dumps(world, separators=(",", ":"), sort_keys=True) + "\n"
    return files


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if mode not in ("--check", "--write"):
        print(__doc__, file=sys.stderr)
        return 2
    stale = []
    for name, text in build().items():
        target = HERE / name
        if mode == "--write":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        elif not target.exists() or target.read_text(encoding="utf-8") != text:
            stale.append(name)
    for name in stale:
        print(f"stale pod world: {name}", file=sys.stderr)
    print(f"pod rooms: {mode[2:]} {'failed' if stale else 'passed'}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
