#!/usr/bin/env python3
"""Profile process PSS/RSS and container memory while the EasyMesh lab changes.

Run this on the LXD host.  The probe executes entirely read-only commands in
bpibroadband and records enough process, cgroup, topology, model and storage
state to correlate memory with cold bring-up and onboarding phases.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import subprocess
import time
from collections import defaultdict
from pathlib import Path


MESH = ("bpibroadband", "bpiap", "bpiap-001", "bpiap-002", "bpiap-003")
CLIENTS = tuple(
    "wlan-client" if index == 0 else f"wlan-client-{index:03d}"
    for index in range(10)
)

CONTAINER_PROBE = r'''
import json, os, re, subprocess, sys, time

def read_text(path):
    try:
        with open(path, errors="replace") as stream:
            return stream.read()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return ""

def keyed_kib(text):
    values = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z_()]+):\s+(\d+)\s+kB$", line)
        if match:
            values[match.group(1)] = int(match.group(2))
    return values

def process(pid):
    status = read_text(f"/proc/{pid}/status")
    if not status:
        return None
    status_values = keyed_kib(status)
    name = next((line.split(":", 1)[1].strip() for line in status.splitlines()
                 if line.startswith("Name:")), "")
    threads = next((int(line.split(":", 1)[1]) for line in status.splitlines()
                    if line.startswith("Threads:")), 0)
    cmdline = read_text(f"/proc/{pid}/cmdline").replace("\0", " ").strip()
    cgroup = read_text(f"/proc/{pid}/cgroup")
    cgroup_path = next((line.split(":", 2)[2] for line in cgroup.splitlines()
                        if line.startswith("0::")), "")
    unit_match = re.search(r"/(?:system|user)\.slice/([^/]+\.service)(?:/|$)", cgroup_path)
    smaps = keyed_kib(read_text(f"/proc/{pid}/smaps_rollup"))
    return {
        "pid": pid,
        "ppid": next((int(line.split(":", 1)[1]) for line in status.splitlines()
                       if line.startswith("PPid:")), 0),
        "name": name,
        "cmdline": cmdline,
        "threads": threads,
        "unit": unit_match.group(1) if unit_match else None,
        "cgroup": cgroup_path,
        "vmsize_kib": status_values.get("VmSize", 0),
        "vmrss_kib": status_values.get("VmRSS", 0),
        "rss_kib": smaps.get("Rss", status_values.get("VmRSS", 0)),
        "pss_kib": smaps.get("Pss", 0),
        "pss_anon_kib": smaps.get("Pss_Anon", 0),
        "pss_file_kib": smaps.get("Pss_File", 0),
        "pss_shmem_kib": smaps.get("Pss_Shmem", 0),
        "private_clean_kib": smaps.get("Private_Clean", 0),
        "private_dirty_kib": smaps.get("Private_Dirty", 0),
        "shared_clean_kib": smaps.get("Shared_Clean", 0),
        "shared_dirty_kib": smaps.get("Shared_Dirty", 0),
        "swap_kib": smaps.get("Swap", 0),
    }

own_pid = os.getpid()
processes = []
for entry in os.listdir("/proc"):
    if not entry.isdigit() or int(entry) == own_pid:
        continue
    value = process(int(entry))
    if value is not None:
        processes.append(value)

def scalar(path):
    text = read_text(path).strip()
    return int(text) if text.isdigit() else None

meminfo = keyed_kib(read_text("/proc/meminfo"))
cgroup_stat = {}
for line in read_text("/sys/fs/cgroup/memory.stat").splitlines():
    fields = line.split()
    if len(fields) == 2 and fields[1].isdigit():
        cgroup_stat[fields[0]] = int(fields[1])

result = {
    "container_epoch": time.time(),
    "processes": sorted(processes, key=lambda item: (-item["pss_kib"], item["pid"])),
    "process_pss_kib": sum(item["pss_kib"] for item in processes),
    "process_rss_kib": sum(item["rss_kib"] for item in processes),
    "meminfo_kib": meminfo,
    "cgroup": {
        "memory_current_bytes": scalar("/sys/fs/cgroup/memory.current"),
        "memory_peak_bytes": scalar("/sys/fs/cgroup/memory.peak"),
        "memory_events": read_text("/sys/fs/cgroup/memory.events").strip(),
        "stat_bytes": cgroup_stat,
    },
}
print(json.dumps(result, separators=(",", ":")))
'''


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run(*args: str, check: bool = True, timeout: float = 30) -> str:
    result = subprocess.run(
        args, check=check, text=True, capture_output=True, timeout=timeout
    )
    return result.stdout.strip()


def instance_states() -> dict[str, str]:
    values = json.loads(run("lxc", "list", "--format=json"))
    wanted = set(MESH + CLIENTS)
    return {
        item["name"]: str(item.get("status", "UNKNOWN")).upper()
        for item in values
        if item.get("name") in wanted
    }


def container_probe() -> dict:
    text = run(
        "lxc", "exec", "bpibroadband", "--", "python3", "-c", CONTAINER_PROBE,
        timeout=45,
    )
    return json.loads(text)


def host_cgroup_snapshot() -> dict | None:
    root = Path("/sys/fs/cgroup/lxc.payload.bpibroadband")
    try:
        values = {
            "memory_current_bytes": int((root / "memory.current").read_text().strip()),
            "memory_peak_bytes": int((root / "memory.peak").read_text().strip()),
            "stat_bytes": {},
        }
        for line in (root / "memory.stat").read_text().splitlines():
            key, value = line.split()
            values["stat_bytes"][key] = int(value)
        return values
    except (FileNotFoundError, PermissionError, ValueError):
        return None


def model_counts() -> dict[str, int] | None:
    query = (
        "select (select count(*) from DeviceList),"
        "(select count(*) from RadioList),"
        "(select count(*) from BSSList),"
        "(select count(*) from STAList where Associated=1);"
    )
    try:
        text = run(
            "lxc", "exec", "bpibroadband", "--", "mysql", "-N", "-ubpi",
            "-proot", "OneWifiMesh", "-e", query,
        )
        values = [int(value) for value in text.split()]
        return dict(zip(("devices", "radios", "bss", "associated"), values))
    except (subprocess.SubprocessError, ValueError):
        return None


def topology_counts() -> dict[str, int] | None:
    try:
        document = json.loads(
            run(
                "curl", "-fsS", "--connect-timeout", "2", "--max-time", "5",
                "http://127.0.0.1:8888/api/v1/topology",
                timeout=8,
            )
        )
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return None
    clients = {
        str(sta.get("staMAC", "")).lower()
        for node in document.get("nodes", [])
        for sta in (node.get("STAList") or [])
        if sta.get("staMAC")
    }
    return {
        "nodes": len(document.get("nodes", [])),
        "clients": len(clients),
        "edges": len(document.get("edges", [])),
    }


def storage_snapshot() -> dict | None:
    script = r'''
set -eu
for path in /nvram /rdklogs /var/lib/mysql /tmp; do
    [ ! -e "$path" ] || printf 'PATH\t%s\t%s\n' "$path" "$(du -sb "$path" | awk '{print $1}')"
done
printf 'JOURNAL\t%s\n' "$(journalctl --disk-usage 2>/dev/null)"
mysql -N -ubpi -proot -e "select table_name,table_rows,data_length,index_length from information_schema.tables where table_schema='OneWifiMesh' order by table_name" 2>/dev/null | sed 's/^/TABLE\t/'
for unit in onewifi em_ctrl em_agent em_cli ieee1905_em_ctrl ieee1905_em_agent; do
    printf 'JOURNAL_UNIT\t%s\t' "$unit"
    journalctl -b -u "$unit" -o cat --no-pager 2>/dev/null | wc -c
done
'''
    try:
        text = run("lxc", "exec", "bpibroadband", "--", "sh", "-c", script, timeout=45)
    except subprocess.SubprocessError:
        return None
    result: dict[str, object] = {"paths_bytes": {}, "tables": {}, "journal_units_bytes": {}}
    for line in text.splitlines():
        fields = line.split("\t")
        if fields[0] == "PATH" and len(fields) == 3:
            result["paths_bytes"][fields[1]] = int(fields[2])
        elif fields[0] == "JOURNAL" and len(fields) == 2:
            result["journal_disk_usage"] = fields[1]
        elif fields[0] == "TABLE" and len(fields) == 5:
            result["tables"][fields[1]] = {
                "rows": int(fields[2]), "data_bytes": int(fields[3]),
                "index_bytes": int(fields[4]),
            }
        elif fields[0] == "JOURNAL_UNIT" and len(fields) == 3:
            result["journal_units_bytes"][fields[1]] = int(fields[2].strip())
    return result


def phase(states: dict[str, str]) -> str:
    if states.get("bpibroadband") != "RUNNING":
        return "controller-stopped"
    extenders = sum(states.get(name) == "RUNNING" for name in MESH[1:])
    clients = sum(states.get(name) == "RUNNING" for name in CLIENTS)
    if extenders == 0:
        return "controller-only"
    if extenders < 4:
        return f"extenders-{extenders}"
    if clients < 10:
        return f"clients-{clients}"
    return "steady-complete"


def identity(process: dict) -> str:
    return str(process.get("unit") or process.get("name") or "unknown")


def summarize(samples: list[dict], output: Path) -> dict:
    by_identity: dict[str, list[dict]] = defaultdict(list)
    by_phase: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        by_phase[sample["phase"]].append(sample)
        grouped: dict[str, list[dict]] = defaultdict(list)
        for process in sample.get("container", {}).get("processes", []):
            grouped[identity(process)].append(process)
        for name, processes in grouped.items():
            by_identity[name].append({
                "pss_kib": sum(item["pss_kib"] for item in processes),
                "rss_kib": sum(item["rss_kib"] for item in processes),
                "swap_kib": sum(item["swap_kib"] for item in processes),
                "threads": sum(item["threads"] for item in processes),
                "cmdline": next(
                    (item["cmdline"] for item in processes if item["cmdline"]), ""
                ),
            })

    process_summary = {}
    for name, values in sorted(by_identity.items()):
        process_summary[name] = {
            "samples": len(values),
            "pss_kib_min": min(item["pss_kib"] for item in values),
            "pss_kib_median": round(statistics.median(item["pss_kib"] for item in values)),
            "pss_kib_max": max(item["pss_kib"] for item in values),
            "rss_kib_max": max(item["rss_kib"] for item in values),
            "swap_kib_max": max(item["swap_kib"] for item in values),
            "threads_max": max(item["threads"] for item in values),
            "example_cmdline": next((item["cmdline"] for item in values if item["cmdline"]), ""),
        }

    phase_summary = {}
    for name, values in sorted(by_phase.items()):
        running = [item for item in values if item.get("container")]
        phase_summary[name] = {
            "samples": len(values),
            "process_pss_kib_min": min(
                (item["container"]["process_pss_kib"] for item in running), default=None
            ),
            "process_pss_kib_max": max(
                (item["container"]["process_pss_kib"] for item in running), default=None
            ),
            "cgroup_current_bytes_min": min(
                (item["host_cgroup"]["memory_current_bytes"] for item in running
                 if item.get("host_cgroup")),
                default=None,
            ),
            "cgroup_current_bytes_max": max(
                (item["host_cgroup"]["memory_current_bytes"] for item in running
                 if item.get("host_cgroup")),
                default=None,
            ),
        }

    result = {
        "completed_at": now_iso(),
        "sample_count": len(samples),
        "elapsed_seconds": samples[-1]["elapsed_seconds"] if samples else 0,
        "processes": process_summary,
        "phases": phase_summary,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile the bpibroadband memory footprint")
    parser.add_argument("--duration", type=float, default=900, help="seconds")
    parser.add_argument("--interval", type=float, default=5, help="seconds")
    parser.add_argument("--storage-interval", type=float, default=120, help="seconds")
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/bpibroadband-memory"))
    args = parser.parse_args()
    if args.duration <= 0 or args.interval <= 0 or args.storage_interval <= 0:
        parser.error("all intervals must be positive")

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_root / f"{stamp}-bpibroadband-memory"
    output.mkdir(parents=True)
    stream_path = output / "samples.jsonl"
    started = time.monotonic()
    next_storage = 0.0
    samples = []

    while True:
        elapsed = time.monotonic() - started
        states = instance_states()
        sample: dict[str, object] = {
            "at": now_iso(), "elapsed_seconds": round(elapsed, 3),
            "phase": phase(states), "instances": states,
        }
        if states.get("bpibroadband") == "RUNNING":
            try:
                sample["container"] = container_probe()
                # Read from the host after the short Python probe exits.  This
                # avoids charging the measurement process itself to the
                # container's working-set value.
                sample["host_cgroup"] = host_cgroup_snapshot()
            except subprocess.SubprocessError as error:
                sample["probe_error"] = str(error)
            sample["model"] = model_counts()
            sample["topology"] = topology_counts()
            if elapsed >= next_storage:
                sample["storage"] = storage_snapshot()
                next_storage = elapsed + args.storage_interval

        samples.append(sample)
        with stream_path.open("a") as stream:
            stream.write(json.dumps(sample, sort_keys=True) + "\n")

        container = sample.get("container", {})
        units = {
            identity(item): item for item in container.get("processes", [])
        } if isinstance(container, dict) else {}
        print(
            f"elapsed={elapsed:.1f}s phase={sample['phase']} "
            f"pss_kib={container.get('process_pss_kib', '-')} "
            f"cgroup_bytes={(sample.get('host_cgroup') or {}).get('memory_current_bytes', '-')} "
            f"em_ctrl_pss={units.get('em_ctrl.service', {}).get('pss_kib', '-')} "
            f"em_cli_pss={units.get('em_cli.service', {}).get('pss_kib', '-')} "
            f"model={sample.get('model')}",
            flush=True,
        )
        if elapsed >= args.duration:
            break
        time.sleep(max(0.0, min(args.interval, args.duration - elapsed)))

    summary = summarize(samples, output)
    print(f"PASSED samples={summary['sample_count']} artifacts={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
