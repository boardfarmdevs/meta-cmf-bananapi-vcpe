from __future__ import annotations

import datetime as dt
import json
import subprocess


def _run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def snapshot(plan: dict) -> dict:
    stations = []
    for role, binding in plan["bindings"].items():
        if binding["role_type"] != "station":
            continue
        container = binding["container"]
        link = _run("lxc", "exec", container, "--", "iw", "dev", "wlan0", "link")
        connected = None
        for line in link.splitlines():
            if line.strip().startswith("Connected to "):
                connected = line.strip().split()[2].lower()
                break
        stations.append({"role": role, "container": container, "bssid": connected})
    return {
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stations": stations,
    }


def mesh_health() -> dict:
    clients = json.loads(_run("curl", "-fsS", "http://127.0.0.1:8888/api/v1/clients"))
    topology = json.loads(_run("curl", "-fsS", "http://127.0.0.1:8888/api/v1/topology"))
    nodes = topology.get("nodes", [])
    return {
        "api_active": clients.get("active"),
        "api_total": clients.get("total"),
        "topology_nodes": len(nodes),
        "complete_nodes": sum(
            1 for node in nodes
            if node.get("name") == "Controller"
            or sum(len(haul.get("BSSList", [])) for haul in node.get("haulTypes", [])) == 10
        ),
    }
