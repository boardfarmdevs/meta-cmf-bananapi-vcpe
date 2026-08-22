#!/usr/bin/env python3
"""Run the long P0 EasyMesh churn acceptance gate.

The workload never treats wmediumd state as an optimizer observation.  Its
control socket is used here only to generate RF churn and to prove that every
scenario restores the exact starting medium.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIGURATOR = ROOT / "wmediumd" / "configurator"
if not CONFIGURATOR.is_dir():
    CONFIGURATOR = Path(
        os.environ.get("EASYMESH_REPO", "/home/vagrant/git/meta-cmf-bananapi-vcpe")
    ) / "gen" / "wmediumd" / "configurator"
sys.path.insert(0, str(CONFIGURATOR))

from wmdcfg.actuator import ControlClient  # noqa: E402
from wmdcfg.inventory import discover  # noqa: E402


MESH = ("bpibroadband", "bpiap", "bpiap-001", "bpiap-002", "bpiap-003")
CLIENTS = tuple(
    "wlan-client" if index == 0 else f"wlan-client-{index:03d}"
    for index in range(10)
)
UNITS = {
    "bpibroadband": (
        "onewifi.service",
        "ieee1905_em_ctrl.service",
        "em_ctrl.service",
        "ieee1905_em_agent.service",
        "em_agent.service",
        "em_cli.service",
    ),
    "bpiap": ("onewifi.service", "ieee1905_em_agent.service", "em_agent.service"),
    "bpiap-001": ("onewifi.service", "ieee1905_em_agent.service", "em_agent.service"),
    "bpiap-002": ("onewifi.service", "ieee1905_em_agent.service", "em_agent.service"),
    "bpiap-003": ("onewifi.service", "ieee1905_em_agent.service", "em_agent.service"),
}
TOPOLOGY_URL = "http://127.0.0.1:8888/api/v1/topology"
CLIENTS_URL = "http://127.0.0.1:8888/api/v1/clients"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run(*args: str, check: bool = True, timeout: float | None = None) -> str:
    result = subprocess.run(
        args, check=check, text=True, capture_output=True, timeout=timeout
    )
    return result.stdout.strip()


def lxc(container: str, command: str, check: bool = True) -> str:
    return run("lxc", "exec", container, "--", "sh", "-c", command, check=check)


def lxc_read(container: str, command: str, attempts: int = 3) -> str:
    """Retry a side-effect-free LXC probe when the exec transport is lost."""
    if attempts < 1:
        raise ValueError("attempts must be positive")
    for attempt in range(1, attempts + 1):
        try:
            return lxc(container, command)
        except subprocess.CalledProcessError:
            if attempt == attempts:
                raise
            time.sleep(0.5 * attempt)
    raise AssertionError("unreachable")


def fetch_json(url: str) -> dict:
    return json.loads(
        run(
            "curl", "-fsS", "--connect-timeout", "3", "--max-time", "15", url,
            timeout=20,
        )
    )


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


class Recorder:
    def __init__(self, path: Path):
        self.path = path

    def write(self, event: str, **fields: object) -> None:
        value = {"at": utc_now(), "event": event, **fields}
        with self.path.open("a") as stream:
            stream.write(json.dumps(value, sort_keys=True) + "\n")
        print(json.dumps(value, sort_keys=True), flush=True)


def service_states() -> dict[str, dict[str, dict[str, object]]]:
    result: dict[str, dict[str, dict[str, object]]] = {}
    for container, units in UNITS.items():
        quoted = " ".join(units)
        text = lxc_read(
            container,
            "for unit in " + quoted + "; do "
            "printf 'UNIT=%s\\n' \"$unit\"; "
            "systemctl show \"$unit\" -p ActiveState -p MainPID -p NRestarts; "
            "cg=$(systemctl show \"$unit\" -p ControlGroup --value); "
            "printf 'ProcessPIDs='; "
            "cat \"/sys/fs/cgroup$cg/cgroup.procs\" 2>/dev/null "
            "| sort -n | paste -sd, -; "
            "done",
        )
        current: dict[str, object] | None = None
        result[container] = {}
        for line in text.splitlines():
            if line.startswith("UNIT="):
                unit = line.split("=", 1)[1]
                current = {}
                result[container][unit] = current
            elif current is not None and "=" in line:
                key, value = line.split("=", 1)
                current[key] = int(value) if value.isdigit() else value
    return result


def validate_services(
    baseline: dict[str, dict[str, dict[str, object]]],
    current: dict[str, dict[str, dict[str, object]]],
) -> list[str]:
    errors = []
    for container, units in baseline.items():
        for unit, expected in units.items():
            actual = current.get(container, {}).get(unit)
            if actual is None:
                errors.append(f"{container}/{unit}: missing")
            elif actual.get("ActiveState") != "active":
                errors.append(f"{container}/{unit}: state={actual.get('ActiveState')}")
            elif actual.get("NRestarts") != expected.get("NRestarts"):
                errors.append(
                    f"{container}/{unit}: restarts "
                    f"{expected.get('NRestarts')}->{actual.get('NRestarts')}"
                )
            elif actual.get("MainPID") != expected.get("MainPID"):
                errors.append(
                    f"{container}/{unit}: pid "
                    f"{expected.get('MainPID')}->{actual.get('MainPID')}"
                )
    return errors


def process_memory(unit: str) -> dict[str, object]:
    command = r'''
unit=$1
pid=$(systemctl show "$unit" -p MainPID --value)
test "${pid:-0}" -gt 0
printf 'pid=%s\n' "$pid"
awk '/^(Rss|Pss|Private_Clean|Private_Dirty|Swap):/{gsub(":", "", $1); printf "%s=%s\n", $1, $2}' "/proc/$pid/smaps_rollup"
ps -p "$pid" -o pcpu=,etimes= | awk '{printf "cpu_percent=%s\nelapsed_seconds=%s\n", $1, $2}'
'''
    text = run(
        "lxc", "exec", "bpibroadband", "--", "sh", "-c", command, "sh", unit
    )
    values: dict[str, object] = {}
    for line in text.splitlines():
        key, value = line.split("=", 1)
        values[key] = float(value) if key == "cpu_percent" else int(value)
    return values


def wmediumd_process_sample(pidfile: Path) -> dict[str, object]:
    pid = int(pidfile.read_text().strip())
    status = Path(f"/proc/{pid}/status").read_text()
    values: dict[str, object] = {"pid": pid}
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            values["Rss"] = int(line.split()[1])
        elif line.startswith("Threads:"):
            values["Threads"] = int(line.split()[1])
    process = run("ps", "-p", str(pid), "-o", "pcpu=,etimes=")
    cpu, elapsed = process.split()
    values["cpu_percent"] = float(cpu)
    values["elapsed_seconds"] = int(elapsed)

    # Resolve this process's socket inodes before reading namespace-wide
    # /proc/<pid>/net/netlink, then sum only their receive-drop counters.
    command = r'''
pid=$1
drops=0
for inode in $(ls -l "/proc/$pid/fd" 2>/dev/null \
        | sed -n 's/.*socket:\[\([0-9]*\)\]/\1/p'); do
    value=$(awk -v inode="$inode" '$10 == inode {print $9}' \
        "/proc/$pid/net/netlink" 2>/dev/null)
    [ -n "$value" ] && drops=$((drops + value))
done
printf 'netlink_drops=%s\n' "$drops"
'''
    netlink = run(
        "sudo", "-n", "sh", "-c", command, "sh", str(pid), check=False
    )
    match = re.search(r"netlink_drops=(\d+)", netlink)
    if not match:
        raise RuntimeError("cannot read wmediumd netlink drop counters")
    values["netlink_drops"] = int(match.group(1))
    return values


def memory_sample(pidfile: Path) -> dict[str, dict[str, object]]:
    return {
        "em_ctrl": process_memory("em_ctrl.service"),
        "em_cli": process_memory("em_cli.service"),
        "wmediumd": wmediumd_process_sample(pidfile),
    }


def journal_usage() -> dict[str, object]:
    text = lxc("bpibroadband", "journalctl --disk-usage 2>/dev/null")
    match = re.search(r"take up ([0-9.]+)([KMG])", text)
    if not match:
        raise RuntimeError(f"cannot parse journal usage: {text!r}")
    scale = {"K": 1024, "M": 1024**2, "G": 1024**3}[match.group(2)]
    return {"bytes": round(float(match.group(1)) * scale), "reported": text}


def medium_snapshot(socket_path: str) -> dict[str, object]:
    with ControlClient(socket_path) as control:
        status = control.status()
        generation, links = control.dump_links()
        _, frequency_links = control.dump_frequency_links()
    links = sorted(
        links, key=lambda item: (item["source"], item["destination"], item["value"])
    )
    frequency_links = sorted(
        frequency_links,
        key=lambda item: (
            item["source"], item["destination"], item["frequency_mhz"],
            item["value"], item["override"],
        ),
    )
    encoded = json.dumps(
        {"links": links, "frequency_links": frequency_links},
        separators=(",", ":"), sort_keys=True,
    ).encode()
    return {
        "instance_id": status.instance_id,
        "generation": generation,
        "stations": status.num_stations,
        "link_count": len(links),
        "frequency_link_count": len(frequency_links),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "links": links,
        "frequency_links": frequency_links,
    }


def candidate_rcpi_check(socket_path: str, api_url: str) -> dict[str, object]:
    text = run(
        sys.executable,
        str(ROOT / "tests" / "candidate-rcpi-test.py"),
        "--socket", socket_path,
        "--api", api_url,
        timeout=30,
    )
    return json.loads(text)


def client_link(container: str) -> dict[str, str | None]:
    command = (
        "printf 'mac='; cat /sys/class/net/wlan0/address; "
        "iw dev wlan0 link 2>/dev/null | sed -n 's/^Connected to /bssid=/p' | cut -d' ' -f1"
    )
    values: dict[str, str | None] = {"client": container, "mac": None, "bssid": None}
    for line in lxc(container, command, check=False).splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.lower() or None
    return values


def topology_counts(document: dict) -> dict[str, int]:
    stas = {
        str(sta.get("staMAC", "")).lower()
        for node in document.get("nodes", [])
        for sta in (node.get("STAList") or [])
        if sta.get("staMAC")
    }
    return {
        "nodes": len(document.get("nodes", [])),
        "clients": len(stas),
        "edges": len(document.get("edges", [])),
    }


def association_consistency(
    document: dict, clients: tuple[str, ...] = CLIENTS
) -> list[dict[str, object]]:
    bssid_owners = {
        str(bss.get("BSSID", "")).lower(): str(node.get("id", "")).lower()
        for node in document.get("nodes", [])
        for haul in (node.get("haulTypes") or [])
        for bss in (haul.get("BSSList") or [])
        if bss.get("BSSID")
    }
    sta_owners = {
        str(sta.get("staMAC", "")).lower(): str(node.get("id", "")).lower()
        for node in document.get("nodes", [])
        for sta in (node.get("STAList") or [])
        if sta.get("staMAC")
    }
    result = []
    for client in clients:
        link = client_link(client)
        physical_owner = bssid_owners.get(str(link["bssid"])) if link["bssid"] else None
        api_owner = sta_owners.get(str(link["mac"])) if link["mac"] else None
        result.append(
            {
                **link,
                "physical_owner": physical_owner,
                "api_owner": api_owner,
                "agreed": bool(physical_owner and physical_owner == api_owner),
            }
        )
    return result


def traffic_one(client: str) -> dict[str, object]:
    started = time.monotonic()
    for attempt in range(1, 4):
        result = subprocess.run(
            (
                "lxc", "exec", client, "--", "ping", "-q", "-c", "3",
                "-W", "1", "10.0.0.1",
            ),
            text=True,
            capture_output=True,
        )
        if 0 <= result.returncode < 128:
            break
        if attempt < 3:
            time.sleep(0.5 * attempt)
    match = re.search(r"(\d+)% packet loss", result.stdout + result.stderr)
    return {
        "client": client,
        "returncode": result.returncode,
        "packet_loss_percent": int(match.group(1)) if match else None,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }


def traffic_check(clients: tuple[str, ...] = CLIENTS) -> list[dict[str, object]]:
    # Ten simultaneous ``lxc exec`` scopes can be terminated by LXD/systemd
    # before ping runs, producing ten false traffic failures at once.  Health
    # acceptance values determinism over speed, so probe clients sequentially.
    return [traffic_one(client) for client in clients]


def provisioned_clients() -> tuple[str, ...]:
    text = run("lxc", "list", "-c", "n", "--format", "csv")
    names = [
        line.strip() for line in text.splitlines()
        if re.fullmatch(r"wlan-client(?:-[0-9]{3})?", line.strip())
    ]
    return tuple(
        sorted(
            names,
            key=lambda name: 0 if name == "wlan-client" else int(name.rsplit("-", 1)[1]),
        )
    )


def provisioned_ssid_counts(clients: tuple[str, ...]) -> dict[str, int]:
    values = [
        run("lxc", "config", "get", client, "user.easymesh.ssid", check=False)
        or "unknown"
        for client in clients
    ]
    return dict(sorted(Counter(values).items()))


def topology_ssid_counts(document: dict) -> dict[str, int]:
    stations: dict[str, str] = {}
    for node in document.get("nodes", []):
        for sta in node.get("STAList") or []:
            mac = str(sta.get("staMAC", "")).lower()
            if mac:
                stations[mac] = str(sta.get("ssid") or "unknown")
    return dict(sorted(Counter(stations.values()).items()))


def model_counts() -> dict[str, int]:
    query = (
        "select (select count(*) from DeviceList),"
        "(select count(*) from RadioList),"
        "(select count(*) from BSSList),"
        "(select count(*) from STAList where Associated=1);"
    )
    text = lxc(
        "bpibroadband", f"mysql -N -ubpi -proot OneWifiMesh -e '{query}' 2>/dev/null"
    )
    values = [int(value) for value in text.split()]
    if len(values) != 4:
        raise RuntimeError(f"unexpected model counts: {text!r}")
    return dict(zip(("devices", "radios", "bss", "associated"), values))


def live_client_api_count(document: dict) -> int:
    clients = document.get("clients", [])
    return len(clients) if isinstance(clients, list) else int(document.get("total", 0))


def select_outage_extender(cursor: int) -> tuple[str, int]:
    inventory = discover()
    radios = {item["container"]: item for item in inventory["radios"]}
    candidates = []
    for container in MESH[1:]:
        bssids = {
            interface["mac"].lower()
            for interface in radios[container].get("interfaces", [])
            if interface.get("ssid") == "private_ssid" and interface.get("mac")
        }
        count = sum(
            item.get("associated_bssid") in bssids
            for item in radios.values()
            if item["kind"] == "station"
        )
        if count:
            candidates.append(container)
    # Clean bring-up commonly leaves every client on the colocated agent.  The
    # outage scenario can place a client on its selected extender through a
    # temporary RF generation and then restore the exact starting matrix.
    if not candidates:
        candidates = list(MESH[1:])
    selected = candidates[cursor % len(candidates)]
    return selected, cursor + 1


def workload_command(
    kind: str, output: Path, outage_cursor: int, ssid: str = "private_ssid"
) -> tuple[list[str], int]:
    if kind == "carousel":
        return [
            sys.executable,
            str(ROOT / "tests" / "wmediumd-client-carousel.py"),
            "--rounds", "1",
            "--ssid", ssid,
            "--output-root", str(output / "carousel"),
        ], outage_cursor
    extender, outage_cursor = select_outage_extender(outage_cursor)
    return [
        sys.executable,
        str(ROOT / "tests" / "wmediumd-extender-outage.py"),
        "--extender", extender,
        "--stability-window", "75",
        "--output-root", str(output / "outage"),
    ], outage_cursor


def new_kernel_failures(start_epoch: int) -> dict[str, list[str]]:
    patterns = "oom-kill|out of memory|killed process"
    result = {}
    for container in MESH:
        text = lxc(
            container,
            f"journalctl -k --since '@{start_epoch}' --no-pager 2>/dev/null "
            f"| grep -i -E '{patterns}' || true",
            check=False,
        )
        result[container] = [line for line in text.splitlines() if line]
    return result


def new_coredumps(start_epoch: int) -> dict[str, list[str]]:
    result = {}
    for container in MESH:
        text = lxc(
            container,
            f"command -v coredumpctl >/dev/null 2>&1 && "
            f"coredumpctl --since '@{start_epoch}' --no-pager --no-legend 2>/dev/null || true",
            check=False,
        )
        result[container] = [line for line in text.splitlines() if line]
    return result


class Soak:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.stop_requested = False
        self.output: Path | None = None
        self.recorder: Recorder | None = None
        self.baseline_services: dict[str, dict[str, dict[str, object]]] = {}
        self.baseline_medium: dict[str, object] = {}
        self.memory_samples: list[dict[str, object]] = []
        self.peak_rss_kib = {"em_ctrl": 0, "em_cli": 0, "wmediumd": 0}
        self.peak_cpu_percent = {"wmediumd": 0.0}
        self.baseline_netlink_drops: int | None = None
        self.workloads: list[dict[str, object]] = []
        self.outage_cursor = 0
        self.carousel_cursor = 0
        self.clients: tuple[str, ...] = ()
        self.expected_ssids: dict[str, int] = {}

    def request_stop(self, signum, frame) -> None:
        self.stop_requested = True
        if self.recorder:
            self.recorder.write("stop_requested", signal=signum)

    def sample_memory(self, elapsed: float, phase: str) -> None:
        memory = memory_sample(self.args.wmediumd_pidfile)
        item = {"elapsed_seconds": round(elapsed, 3), "phase": phase, "memory": memory}
        self.memory_samples.append(item)
        for process, values in memory.items():
            rss = int(values["Rss"])
            self.peak_rss_kib[process] = max(self.peak_rss_kib[process], rss)
        wmediumd_cpu = float(memory["wmediumd"]["cpu_percent"])
        self.peak_cpu_percent["wmediumd"] = max(
            self.peak_cpu_percent["wmediumd"], wmediumd_cpu
        )
        drops = int(memory["wmediumd"]["netlink_drops"])
        if self.baseline_netlink_drops is None:
            self.baseline_netlink_drops = drops
        assert self.recorder
        self.recorder.write("memory", **item)
        if self.peak_rss_kib["em_ctrl"] > self.args.max_ctrl_rss_mib * 1024:
            raise RuntimeError("em_ctrl exceeded its RSS limit")
        if self.peak_rss_kib["em_cli"] > self.args.max_cli_rss_mib * 1024:
            raise RuntimeError("em_cli exceeded its RSS limit")
        if self.peak_rss_kib["wmediumd"] > self.args.max_wmediumd_rss_mib * 1024:
            raise RuntimeError("wmediumd exceeded its RSS limit")
        if drops > self.baseline_netlink_drops:
            raise RuntimeError(
                "wmediumd netlink receive drops increased "
                f"{self.baseline_netlink_drops}->{drops}"
            )

    def health(self, elapsed: float, phase: str) -> dict[str, object]:
        topology = fetch_json(self.args.topology_url)
        clients_document = fetch_json(self.args.clients_url)
        counts = topology_counts(topology)
        model = model_counts()
        consistency = association_consistency(topology, self.clients)
        traffic = traffic_check(self.clients)
        services = service_states()
        journal = journal_usage()
        candidate = candidate_rcpi_check(self.args.socket, self.args.api_url)
        medium = medium_snapshot(self.args.socket)
        errors = []
        expected_clients = len(self.clients)
        if counts != {"nodes": 6, "clients": expected_clients, "edges": 5}:
            errors.append(f"topology={counts}")
        if model != {
            "devices": 5, "radios": 15, "bss": 50,
            "associated": expected_clients + 4,
        }:
            errors.append(f"model={model}")
        client_count = live_client_api_count(clients_document)
        if client_count != expected_clients:
            errors.append(f"client_api={client_count}")
        ssid_counts = topology_ssid_counts(topology)
        if ssid_counts != self.expected_ssids:
            errors.append(f"ssid_cohorts={ssid_counts}, expected={self.expected_ssids}")
        if any(not item["agreed"] for item in consistency):
            errors.append("physical/API association disagreement")
        if any(item["returncode"] or item["packet_loss_percent"] for item in traffic):
            errors.append("client traffic failure")
        errors.extend(validate_services(self.baseline_services, services))
        if journal["bytes"] > self.args.max_journal_mib * 1024**2:
            errors.append(f"journal={journal['reported']}")
        if medium["instance_id"] != self.baseline_medium["instance_id"]:
            errors.append("wmediumd instance changed")
        if medium["sha256"] != self.baseline_medium["sha256"]:
            errors.append("wmediumd links differ from the exact baseline")
        result = {
            "elapsed_seconds": round(elapsed, 3),
            "phase": phase,
            "topology": counts,
            "model": model,
            "client_api_count": client_count,
            "ssid_cohorts": ssid_counts,
            "consistency": consistency,
            "traffic": traffic,
            "services": services,
            "journal": journal,
            "candidate_rcpi": candidate,
            "medium": {
                key: value for key, value in medium.items()
                if key not in ("links", "frequency_links")
            },
            "errors": errors,
        }
        assert self.recorder
        self.recorder.write("health", **result)
        if errors:
            raise RuntimeError("; ".join(errors))
        return result

    def run_workload(self, kind: str, index: int, started: float, sample_due: float) -> float:
        assert self.output and self.recorder
        if kind == "carousel":
            cohorts = tuple(
                ssid for ssid in ("private_ssid", "iot_ssid")
                if self.expected_ssids.get(ssid, 0)
            )
            ssid = cohorts[self.carousel_cursor % len(cohorts)]
            self.carousel_cursor += 1
        else:
            ssid = "private_ssid"
        command, self.outage_cursor = workload_command(
            kind, self.output / "workloads", self.outage_cursor, ssid
        )
        log = self.output / "workloads" / f"{index:04d}-{kind}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        self.recorder.write("workload_start", index=index, kind=kind, command=command)
        workload_started = time.monotonic()
        deferred_error: RuntimeError | None = None
        with log.open("w") as stream:
            process = subprocess.Popen(
                command, text=True, stdout=stream, stderr=subprocess.STDOUT
            )
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed >= sample_due and deferred_error is None:
                    try:
                        self.sample_memory(elapsed, f"workload-{index}-{kind}")
                    except RuntimeError as error:
                        # Do not strand a modified medium.  Let the scenario's
                        # finally block perform its exact restore, then fail.
                        deferred_error = error
                        self.recorder.write(
                            "workload_deferred_failure", index=index, kind=kind,
                            error=str(error),
                        )
                    sample_due = elapsed + self.args.sample_interval
                time.sleep(min(1.0, max(0.1, sample_due - elapsed)))
        elapsed_ms = round((time.monotonic() - workload_started) * 1000)
        result = {
            "index": index,
            "kind": kind,
            "returncode": process.returncode,
            "elapsed_ms": elapsed_ms,
            "log": str(log),
        }
        self.workloads.append(result)
        self.recorder.write("workload_complete", **result)
        if process.returncode:
            raise RuntimeError(f"{kind} workload {index} failed; see {log}")
        if deferred_error is not None:
            raise deferred_error
        return sample_due

    def growth_result(self, total_elapsed: float) -> dict[str, object]:
        anchor_seconds = self.args.growth_anchor_hours * 3600
        eligible = (
            total_elapsed >= self.args.duration
            and self.args.duration >= 12 * 3600
            and self.args.max_workloads == 0
        )
        anchor = next(
            (
                item for item in self.memory_samples
                if float(item["elapsed_seconds"]) >= anchor_seconds
            ),
            self.memory_samples[0],
        )
        final = self.memory_samples[-1]
        growth = {}
        errors = []
        for process in ("em_ctrl", "em_cli"):
            before = int(anchor["memory"][process]["Pss"])
            after = int(final["memory"][process]["Pss"])
            delta = after - before
            growth[process] = {
                "anchor_pss_kib": before,
                "final_pss_kib": after,
                "growth_kib": delta,
            }
            if delta > self.args.max_pss_growth_mib * 1024:
                errors.append(f"{process} PSS growth={delta} KiB")
        return {
            "acceptance_eligible": eligible,
            "anchor_hours": self.args.growth_anchor_hours,
            "limit_mib": self.args.max_pss_growth_mib,
            "processes": growth,
            "errors": errors,
        }

    def execute(self) -> int:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.output = self.args.output_root / f"{stamp}-p0-churn-soak"
        self.output.mkdir(parents=True, exist_ok=False)
        self.recorder = Recorder(self.output / "events.jsonl")
        started_wall = int(time.time())
        started = time.monotonic()
        outcome = "failed"
        error_text = None
        try:
            self.clients = provisioned_clients()
            if not self.clients:
                raise RuntimeError("no provisioned WLAN clients")
            if self.args.expected_clients and len(self.clients) != self.args.expected_clients:
                raise RuntimeError(
                    f"provisioned clients={len(self.clients)}, "
                    f"expected={self.args.expected_clients}"
                )
            self.expected_ssids = provisioned_ssid_counts(self.clients)
            if "unknown" in self.expected_ssids:
                raise RuntimeError(
                    "client cohort metadata is incomplete: "
                    f"{self.expected_ssids}"
                )
            self.baseline_services = service_states()
            self.baseline_medium = medium_snapshot(self.args.socket)
            write_json(self.output / "services-baseline.json", self.baseline_services)
            write_json(self.output / "medium-baseline.json", self.baseline_medium)
            self.sample_memory(0, "preflight")
            self.health(0, "preflight")
            sample_due = self.args.sample_interval
            index = 0
            while (
                time.monotonic() - started < self.args.duration
                and not self.stop_requested
                and (self.args.max_workloads == 0 or index < self.args.max_workloads)
            ):
                index += 1
                if self.args.workload == "alternating":
                    kind = "outage" if index % self.args.outage_every == 0 else "carousel"
                else:
                    kind = self.args.workload
                sample_due = self.run_workload(kind, index, started, sample_due)
                elapsed = time.monotonic() - started
                self.sample_memory(elapsed, f"post-workload-{index}")
                self.health(elapsed, f"post-workload-{index}")
                deadline = min(started + self.args.duration, time.monotonic() + self.args.settle)
                while time.monotonic() < deadline and not self.stop_requested:
                    elapsed = time.monotonic() - started
                    if elapsed >= sample_due:
                        self.sample_memory(elapsed, f"settle-{index}")
                        sample_due = elapsed + self.args.sample_interval
                    time.sleep(min(1.0, deadline - time.monotonic()))

            elapsed = time.monotonic() - started
            self.sample_memory(elapsed, "final")
            final_health = self.health(elapsed, "final")
            growth = self.growth_result(elapsed)
            if growth["errors"]:
                raise RuntimeError("; ".join(growth["errors"]))
            oom = new_kernel_failures(started_wall)
            cores = new_coredumps(started_wall)
            if any(oom.values()):
                raise RuntimeError("new OOM evidence exists")
            if any(cores.values()):
                raise RuntimeError("new coredump evidence exists")
            outcome = "interrupted" if self.stop_requested else "passed"
            summary = {
                "outcome": outcome,
                "started_at_epoch": started_wall,
                "completed_at": utc_now(),
                "elapsed_seconds": round(elapsed, 3),
                "requested_seconds": self.args.duration,
                "workload_count": len(self.workloads),
                "workloads": self.workloads,
                "peak_rss_kib": self.peak_rss_kib,
                "peak_cpu_percent": self.peak_cpu_percent,
                "growth": growth,
                "oom": oom,
                "coredumps": cores,
                "final_health": final_health,
            }
            write_json(self.output / "summary.json", summary)
            print(f"{outcome.upper()} artifacts={self.output}", flush=True)
            return 130 if self.stop_requested else 0
        except Exception as error:
            error_text = str(error)
            self.recorder.write("failure", error=error_text)
            elapsed = time.monotonic() - started
            summary = {
                "outcome": outcome,
                "error": error_text,
                "elapsed_seconds": round(elapsed, 3),
                "requested_seconds": self.args.duration,
                "workload_count": len(self.workloads),
                "workloads": self.workloads,
                "peak_rss_kib": self.peak_rss_kib,
                "peak_cpu_percent": self.peak_cpu_percent,
            }
            write_json(self.output / "summary.json", summary)
            print(f"FAILED artifacts={self.output}: {error_text}", file=sys.stderr)
            return 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the 12-hour P0 RF churn soak")
    parser.add_argument("--duration", type=float, default=12 * 3600, help="seconds")
    parser.add_argument("--sample-interval", type=float, default=60)
    parser.add_argument("--settle", type=float, default=30)
    parser.add_argument(
        "--max-workloads", type=int, default=0,
        help="stop after N workloads for a shakedown; 0 is duration-bound",
    )
    parser.add_argument(
        "--workload", choices=("alternating", "carousel", "outage"),
        default="alternating",
    )
    parser.add_argument(
        "--outage-every", type=int, default=3,
        help="with alternating workload, make every Nth operation an extender outage",
    )
    parser.add_argument("--socket", default="/run/wmediumd-control.sock")
    parser.add_argument("--topology-url", default=TOPOLOGY_URL)
    parser.add_argument("--clients-url", default=CLIENTS_URL)
    parser.add_argument(
        "--expected-clients", type=int, default=0,
        help="require an exact provisioned client count; 0 auto-discovers it",
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8888/api/v1")
    parser.add_argument("--max-ctrl-rss-mib", type=int, default=256)
    parser.add_argument("--max-cli-rss-mib", type=int, default=192)
    parser.add_argument("--max-wmediumd-rss-mib", type=int, default=64)
    parser.add_argument(
        "--wmediumd-pidfile", type=Path,
        default=Path("/run/meta-cmf-wmediumd/wmediumd.pid"),
    )
    parser.add_argument("--max-pss-growth-mib", type=int, default=64)
    parser.add_argument("--growth-anchor-hours", type=float, default=1)
    parser.add_argument("--max-journal-mib", type=int, default=24)
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/easymesh-p0-soak"))
    args = parser.parse_args()
    if args.duration <= 0 or args.sample_interval <= 0 or args.settle < 0:
        parser.error("duration and sample interval must be positive; settle cannot be negative")
    if args.max_workloads < 0:
        parser.error("--max-workloads cannot be negative")
    if args.expected_clients < 0:
        parser.error("--expected-clients cannot be negative")
    if args.outage_every <= 0:
        parser.error("--outage-every must be positive")
    soak = Soak(args)
    handlers = {
        signum: signal.signal(signum, soak.request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        return soak.execute()
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
