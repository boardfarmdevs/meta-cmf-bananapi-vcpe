#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def command(*arguments):
    return subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=30).stdout.strip()


def identities():
    instances = json.loads(command("lxc", "list", "--format", "json"))
    result = {}
    for instance in instances:
        name = instance["name"]
        if not name.startswith(("wlan-client", "bpiap", "bpibroadband")):
            continue
        state = json.loads(command("lxc", "query", f"/1.0/instances/{name}/state"))
        if state["status"] != "Running":
            raise RuntimeError(f"{name} is not running")
        result[name] = state["pid"]
        if not name.startswith("wlan-client"):
            result[name + "/services"] = command("lxc", "exec", name, "--", "systemctl", "show",
                "onewifi", "em_agent", "-p", "MainPID", "-p", "NRestarts", "-p", "ActiveState")
    if sum(name.startswith("wlan-client") for name in result) != 20:
        raise RuntimeError("requires the default 20-client pool")
    result["controller-services"] = command("lxc", "exec", "bpibroadband", "--", "systemctl", "show",
        "em_ctrl", "em_cli", "-p", "MainPID", "-p", "NRestarts", "-p", "ActiveState")
    medium_pid = Path("/run/meta-cmf-wmediumd/wmediumd.pid").read_text().strip()
    result["medium-process"] = command("ps", "-p", medium_pid, "-o", "pid=,lstart=,args=")
    return result


def main():
    parser = argparse.ArgumentParser(description="Opt-in fixed-pool world switching acceptance; restores default in finally")
    parser.add_argument("--yes-act", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8891")
    parser.add_argument("--controller-url", default="http://127.0.0.1:8888")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--all-worlds", action="store_true", help="test every compatible installed room")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.yes_act:
        parser.error("--yes-act is required: this changes live room RF")
    lease = None
    lease_renewed = 0.0
    report = {"worlds": [], "restored_default": False, "passed": False}

    def request(path, body=None, *, controller=False, revision=None, method=None):
        headers = {"Content-Type": "application/json"}
        if body is not None:
            body = {**body, "command_id": "smoke-" + uuid.uuid4().hex}
        if revision is not None:
            headers["If-Match"] = f'"world-revision-{revision}"'
        target = (args.controller_url if controller else args.base_url) + path
        query = urllib.request.Request(target, data=None if body is None else json.dumps(body).encode(), headers=headers, method=method)
        try:
            with urllib.request.urlopen(query, timeout=120 if body is not None or path == "/api/demo/interactions" else 8) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if controller and error.code >= 500:
                raise urllib.error.URLError(f"controller HTTP {error.code}") from None
            detail = json.load(error)
            raise RuntimeError(f"{path}: {detail.get('error')}: {detail.get('message')}") from None

    def renew():
        nonlocal lease_renewed
        if time.monotonic() - lease_renewed >= 8:
            request("/api/demo/interactions/lease", {"token": lease})
            lease_renewed = time.monotonic()

    def apply(name):
        renew()
        snapshot = request("/api/demo/interactions")
        result = request("/api/demo/world/apply", {"token": lease, "world": name}, revision=snapshot["revision"])
        print(json.dumps({"applied": name, "target": result["expected_online_clients"],
                          "generation": result["daemon_generation"]}), flush=True)
        return result

    def wait_for_world(name, expected, require_convergence=True):
        started = time.monotonic()
        stable_since = None
        while time.monotonic() - started < args.timeout:
            renew()
            try:
                current = request("/api/demo/current")
                topology = request("/api/v1/topology", controller=True)
            except (TimeoutError, urllib.error.URLError) as error:
                stable_since = None
                print(json.dumps({"waiting": name, "telemetry_unavailable": str(error)}), flush=True)
                time.sleep(2)
                continue
            actual = {station["staMAC"].lower() for node in topology["nodes"]
                      for station in node.get("STAList", []) or []}
            desired = {mac for role, mac in mac_by_role.items() if current["roles"].get(role, {}).get("present")}
            health = current.get("health", {})
            optimizer = current.get("optimizer", {})
            fleet = optimizer.get("fleet", {})
            rows = optimizer.get("client_decisions", [])
            clients = {client["sta_mac"]: client for client in current.get("network", {}).get("clients", [])}
            best_ap_checked = len(rows) == expected and all(
                row.get("current_rcpi") is not None
                and row.get("source_bssid") == clients.get(row["sta_mac"], {}).get("connected_bssid")
                and all(score.get("gain_rcpi", 0) <= 0 for score in row.get("scores", [])
                        if score.get("band") == row.get("current_band"))
                for row in rows
            )
            evaluated_at = optimizer.get("evaluated_at")
            evaluation_age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(
                evaluated_at.replace("Z", "+00:00"))).total_seconds() if evaluated_at else float("inf")
            mesh = current.get("network", {}).get("mesh", {})
            control = mesh.get("backhaul_control", {})
            reported_parents = {edge["child_role"]: edge["parent_role"] for edge in mesh.get("backhaul_edges", [])}
            backhaul_settled = not control or (
                control.get("status") == "stable" and control.get("parents") == reported_parents
                and len(reported_parents) == 4
            )
            converged = (optimizer.get("expected_online_clients") == expected
                         and optimizer.get("environment_epoch") == current.get("environment_epoch")
                         and fleet.get("converged") is True
                         and fleet.get("measurement_complete") is True
                         and fleet.get("clients_checked") == expected
                         and fleet.get("clients_evaluated") == expected
                         and fleet.get("clients_with_stronger_ap") == 0
                         and best_ap_checked and -5 <= evaluation_age <= 60 and backhaul_settled)
            if (actual == desired and len(actual) == expected and len(topology["nodes"]) == 6
                    and health.get("healthy") is True and health.get("expected_online_clients") == expected
                    and (converged or not require_convergence)):
                offline = [role for role in mac_by_role if not current["roles"][role]["present"]]
                for role in offline:
                    link = command("lxc", "exec", containers_by_role[role], "--", "iw", "dev", "wlan0", "link")
                    if "Not connected" not in link:
                        raise RuntimeError(f"{role}: controller roster converged but isolated client remains connected")
                if stable_since is None:
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since < 10:
                    time.sleep(3)
                    continue
                result = {"world": name, "clients": len(actual), "mesh_nodes": len(topology["nodes"]),
                          "elapsed_seconds": round(time.monotonic() - started, 2), "healthy": True,
                          "kernel_offline_clients_verified": len(offline),
                          "passed": True, "fleet_converged": converged,
                          "best_eligible_same_band_ap_verified": best_ap_checked,
                          "backhaul_settled": backhaul_settled, "backhaul_parents": reported_parents,
                          "evaluation_age_seconds": round(evaluation_age, 3),
                          "client_decisions": rows,
                          "clients_checked": fleet.get("clients_checked"),
                          "actions_used": optimizer.get("actions_used"),
                          "kernel_current_link_measurements": optimizer.get("kernel_current_link_measurements", []),
                          "associations": [{"sta_mac": client["sta_mac"],
                                            "ap": client["connected_device_name"],
                                            "bssid": client["connected_bssid"],
                                            "rssi_dbm": client["rssi_dbm"]}
                                           for client in current.get("network", {}).get("clients", [])]}
                print(json.dumps(result), flush=True)
                return result
            stable_since = None
            print(json.dumps({"waiting": name, "actual": len(actual), "expected": expected,
                              "healthy": health.get("healthy"), "fleet_converged": converged,
                              "stronger_ap_clients": fleet.get("clients_with_stronger_ap"),
                              "best_ap_checked": best_ap_checked, "backhaul_settled": backhaul_settled,
                              "decision": optimizer.get("decision", {}).get("reason"),
                              "actions_used": optimizer.get("actions_used"),
                              "elapsed": round(time.monotonic() - started)}), flush=True)
            time.sleep(3)
        raise RuntimeError(f"{name}: exact {expected}-client roster and measured best-AP convergence not achieved")

    before = identities()
    preflight_deadline = time.monotonic() + args.timeout
    while True:
        current = request("/api/demo/current")
        if current.get("scenario") != "home-five-agent--private-client-room-walk":
            raise RuntimeError("start acceptance from the default room")
        mac_by_role = {client["role"]: client["sta_mac"].lower() for client in current.get("network", {}).get("clients", [])}
        containers_by_role = {client["role"]: client["container"] for client in current.get("network", {}).get("clients", [])}
        if len(mac_by_role) == 20 and current.get("health", {}).get("healthy") is True:
            break
        if time.monotonic() >= preflight_deadline:
            raise RuntimeError("start acceptance from a healthy default 20-client room")
        time.sleep(2)
    report["run_id"] = current["run_id"]
    original_room = request("/api/demo/interactions")
    if original_room.get("movement_active") or original_room.get("recording", {}).get("active"):
        raise RuntimeError("pause movement and recording before acceptance")
    if original_room.get("playback", {}).get("time_ms") != 0 or original_room.get("lease", {}).get("held"):
        raise RuntimeError("requires paused initial playback and no existing control lease")
    report["original_room"] = original_room
    try:
        lease = request("/api/demo/interactions/lease", {"owner": "rev140-world-switch-acceptance"})["token"]
        lease_renewed = time.monotonic()
        names = ([world["id"] for world in request("/api/demo/worlds")["worlds"]] if args.all_worlds else
                 ["home-a-border-hover", "home-a-stationary", "home-b-slow-walk-ten", "home-a-flash-crowd"])
        for name in [*names, "default"]:
            expected = apply(name)["expected_online_clients"]
            try:
                result = wait_for_world(name, expected)
            except RuntimeError as error:
                if not args.all_worlds:
                    raise
                current = request("/api/demo/current")
                if current.get("error") or current.get("state") != "running":
                    raise
                result = {"world": name, "expected_clients": expected, "passed": False,
                          "error": str(error), "health": current.get("health"),
                          "optimizer": current.get("optimizer")}
            report["worlds"].append(result)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        for present, expected in ((False, 19), (True, 20)):
            renew()
            snapshot = request("/api/demo/interactions")
            request("/api/demo/roles/sta_mobile_01/presence", {"token": lease, "present": present},
                    revision=snapshot["revision"], method="PUT")
            report["worlds"].append(wait_for_world("client-reappear" if present else "client-disappear", expected))
        report["containers_and_services_unchanged"] = identities() == before
        if not report["containers_and_services_unchanged"]:
            raise RuntimeError("container, service or medium process identity changed")
        report["passed"] = all(world.get("passed") for world in report["worlds"])
        if not report["passed"]:
            raise RuntimeError("one or more rooms failed measured convergence; see per-room results")
    except Exception as error:
        report["error"] = str(error)
        print(json.dumps({"failed": str(error)}), flush=True)
        raise
    finally:
        try:
            if lease is not None:
                if not request("/api/demo/interactions").get("lease", {}).get("held"):
                    lease = request("/api/demo/interactions/lease", {"owner": "rev140-world-switch-acceptance"})["token"]
                    lease_renewed = time.monotonic()
                apply("default")
                for role, saved in original_room["roles"].items():
                    snapshot = request("/api/demo/interactions")
                    if snapshot["roles"][role]["position"] != saved["position"]:
                        renew()
                        request("/api/demo/roles/" + role + "/position",
                                {"token": lease, "position": saved["position"], "final": True},
                                revision=snapshot["revision"], method="PUT")
                report["final_restoration"] = wait_for_world("default-restore", 20)
                report["restored_default"] = True
                query = urllib.request.Request(args.base_url + "/api/demo/interactions/lease", method="DELETE",
                    data=json.dumps({"token": lease, "command_id": "release-" + uuid.uuid4().hex}).encode(),
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(query, timeout=20):
                    pass
        except Exception as error:
            report["restore_error"] = str(error)
            print(json.dumps({"restore_failed": str(error)}), flush=True)
        finally:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        if not report["restored_default"] and report["passed"]:
            raise RuntimeError("acceptance did not restore the default room")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
