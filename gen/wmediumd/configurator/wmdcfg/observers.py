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
    topology = json.loads(_run("curl", "-fsS", "http://127.0.0.1:8888/api/v1/topology"))
    nodes = topology.get("nodes", [])
    clients = {
        station.get("staMAC")
        for node in nodes
        for station in (node.get("STAList") or [])
        if station.get("staMAC")
    }
    return {
        # Retain the public keys for compatibility. Both now represent the
        # unique live associations in the topology; /api/v1/clients is a
        # packaged WebUI demonstration inventory, not controller state.
        "api_active": len(clients),
        "api_total": len(clients),
        "topology_nodes": len(nodes),
        "complete_nodes": sum(
            1 for node in nodes
            if node.get("name") == "Controller"
            or sum(
                len(haul.get("BSSList") or [])
                for haul in (node.get("haulTypes") or [])
            ) == 10
        ),
    }
