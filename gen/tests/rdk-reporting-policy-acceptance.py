#!/usr/bin/env python3
"""Bounded RDK AP-metrics query/threshold qualification with native wire evidence."""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from optimizer.load_capture import NativeLoadDecoder
from wmdcfg.survey_bridge import parse_contexts


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def command(*arguments, timeout=30):
    return subprocess.run(arguments, check=True, text=True, capture_output=True, timeout=timeout).stdout.strip()


def fetch(endpoint, payload=None):
    request = Request("http://127.0.0.1:8888/api/v1/" + endpoint,
                      data=None if payload is None else json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=40) as response:
        return json.load(response)


def mac(raw):
    return ":".join(f"{octet:02x}" for octet in raw)


def frame_for(source, destination, kind, identifier, payload):
    return (bytes.fromhex(destination.replace(":", "")) + bytes.fromhex(source.replace(":", ""))
            + bytes.fromhex("893a") + struct.pack("!BBHHBB", 0, 0, kind, identifier, 0, 0x80)
            + payload + bytes(3))


def decode_frame(frame):
    if len(frame) < 25 or frame[12:14] != bytes.fromhex("893a") or frame[14] != 0:
        return None
    kind, identifier = struct.unpack_from("!HH", frame, 16)
    if kind not in (2, 3, 0x8000, 0x8003, 0x800B, 0x800C):
        return None
    record = {"type": kind, "message_id": identifier, "source": mac(frame[6:12]),
              "destination": mac(frame[:6]), "fragment": frame[20], "last": bool(frame[21] & 0x80)}
    if frame[20] == 0 and frame[21] & 0x80:
        position = 22
        while position + 3 <= len(frame):
            tag, length = struct.unpack_from("!BH", frame, position)
            position += 3
            value = frame[position:position + length]
            if len(value) != length:
                return None
            position += length
            if tag == 0:
                break
            if tag == 0x8A and length >= 2:
                count = value[1]
                if length != 2 + count * 10:
                    return None
                record["policy"] = {"interval": value[0], "radios": [
                    {"ruid": mac(value[offset:offset + 6]), "rcpi": value[offset + 6],
                     "hysteresis": value[offset + 7], "utilization": value[offset + 8],
                     "inclusion": value[offset + 9]}
                    for offset in range(2, length, 10)]}
    return record


def capture():
    decoder = NativeLoadDecoder()
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x893A)) as receiver:
        receiver.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)
        print(json.dumps({"ready": True}), flush=True)
        checked = time.monotonic()
        while True:
            ready, _, _ = select.select([receiver, sys.stdin], [], [], .5)
            if sys.stdin in ready and not os.read(sys.stdin.fileno(), 1):
                break
            if receiver in ready:
                frame = receiver.recv(65536)
                record = decode_frame(frame)
                if record is not None:
                    record.update(monotonic_ns=time.monotonic_ns(), at=time.time(), frame=frame.hex())
                    decoded = decoder.feed(frame, time.monotonic())
                    if decoded is not None:
                        record["report"] = decoded
                    print(json.dumps(record), flush=True)
            if time.monotonic() - checked >= 1:
                packets, drops = struct.unpack("II", receiver.getsockopt(263, 6, 8))
                require(drops == 0, "capture socket dropped packets")
                checked = time.monotonic()
        packets, drops = struct.unpack("II", receiver.getsockopt(263, 6, 8))
        require(drops == 0, "capture socket dropped packets on shutdown")


def query_matches(row, identifier, bssid, value):
    loads = row.get("report", {}).get("loads", [])
    return (row["message_id"] == identifier and len(loads) == 1
            and loads[0]["bssid"] == bssid and loads[0]["utilization"] == value)


class Wire:
    def __init__(self, container, output):
        self.container = container
        self.pid = json.loads(command("lxc", "query", f"/1.0/instances/{container}/state"))["pid"]
        self.rows = []
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.error = None
        self.output = output
        self.process = subprocess.Popen([
            "nsenter", "-t", str(self.pid), "-n", sys.executable, str(Path(__file__).resolve()),
            "--capture"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        if not self.ready.wait(8):
            self.close()
            raise RuntimeError("native wire capture did not become ready")

    def read(self):
        try:
            with self.output.open("w") as stream:
                for line in self.process.stdout:
                    value = json.loads(line)
                    if value.get("ready"):
                        self.ready.set()
                        continue
                    stream.write(line)
                    stream.flush()
                    with self.lock:
                        require(len(self.rows) < 50000, "native capture record limit exceeded")
                        self.rows.append(value)
        except Exception as error:
            self.error = str(error)

    def since(self, mark=0):
        require(self.error is None and self.process.poll() is None, "native capture failed: " + str(self.error))
        with self.lock:
            return [row for row in self.rows if row["monotonic_ns"] >= mark]

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.reader.join(timeout=5)
        require(self.process.returncode == 0 and self.error is None and not self.reader.is_alive(),
                "native capture failed: " + str(self.error) + " " + self.process.stderr.read())

    def send(self, frame):
        command("nsenter", "-t", str(self.pid), "-n", sys.executable, str(Path(__file__).resolve()),
                "--send", frame.hex())


def configure(policy):
    result = fetch("wifipolicy", [policy])
    require(result.get("success") is True, "native policy update rejected")
    observed = next(row for row in fetch("wifipolicy")["policyConfig"] if row["id"] == policy["id"])
    for field in ("apMetricReportingPolicy", "radioSpecificMetricsPolicy"):
        require(observed[field] == policy[field], "native policy readback mismatch: " + field)


def wait_for(predicate, seconds, description):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.1)
    raise RuntimeError(description)


def identities():
    result = {}
    for node in ("bpibroadband", "bpiap", "bpiap-001", "bpiap-002", "bpiap-003"):
        result[node] = command("lxc", "exec", node, "--", "systemctl", "show", "em_agent", "onewifi",
                               *( ["em_ctrl"] if node == "bpibroadband" else []),
                               "-p", "Id", "-p", "MainPID", "-p", "NRestarts", "-p", "ActiveState")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--extended", action="store_true")
    parser.add_argument("--socket", default="/run/meta-cmf-wmediumd/metrics/control.sock")
    parser.add_argument("--capture", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--send", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.capture:
        capture()
        return 0
    if args.send:
        with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x893A)) as sender:
            sender.bind(("brlan0", 0))
            sender.send(bytes.fromhex(args.send))
        return 0
    if not args.live:
        print(json.dumps({"state": "prepared", "scope": "RDK native query and threshold qualification",
                          "mutations": ["one agent reporting policy", "bounded survey field fixtures"]}))
        return 0
    require(os.geteuid() == 0 and args.root and args.output, "requires root in RDK VM, --root and --output")
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"state": "failed", "stack": "rdk", "scope": "native field/reporting contract",
              "physical_congestion_claim": False, "restoration_errors": []}
    fixture = None
    fixture_log = None
    saved = None
    bridge_stopped = False
    before = identities()
    report["identity_before"] = before
    report["controller_sha256"] = command("lxc", "exec", "bpibroadband", "--", "sha256sum", "/usr/bin/onewifi_em_ctrl")
    node = "bpiap-001"
    wires = []
    token = None
    lease_stop = threading.Event()
    lease_thread = None
    lease_errors = []

    def lease_request(payload, method="POST"):
        request = Request("http://127.0.0.1:8891/api/demo/interactions/lease",
            data=json.dumps({"command_id": str(uuid.uuid4()), **payload}).encode(), method=method,
            headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:8891"})
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    def renew_lease():
        while not lease_stop.wait(5):
            try:
                lease_request({"token": token})
            except Exception as error:
                lease_errors.append(str(error))
                return

    def fixed(value):
        nonlocal fixture, fixture_log
        if fixture is not None:
            fixture.terminate()
            fixture.wait(timeout=5)
            fixture_log.close()
        fixture_log = (args.output / f"fixture-{value}-{time.monotonic_ns()}.log").open("w")
        fixture = subprocess.Popen([sys.executable, "-m", "wmdcfg.survey_bridge", "--enable",
            "--socket", args.socket, "--fixed-utilization", str(value)],
            stdout=fixture_log, stderr=subprocess.STDOUT)

    try:
        with urlopen("http://127.0.0.1:8891/api/demo/interactions", timeout=10) as response:
            room = json.load(response)
        require(not room["lease"]["held"] and room["playback"]["status"] == "paused"
                and room["playback"]["time_ms"] == 0 and room["expected_online_clients"] == 20
                and not room.get("recording", {}).get("active", False)
                and room["selected_world"] == "home-five-agent--private-client-room-walk",
                "requires idle default twenty-client room")
        token = lease_request({"owner": "rdk-rf14-qualification"})["token"]
        lease_thread = threading.Thread(target=renew_lease, daemon=True)
        lease_thread.start()
        bssids = [command("lxc", "exec", node, "--", "cat", f"/sys/class/net/wifi{number}/address")
                  for number in range(3)]
        bssid = bssids[0]
        policies = fetch("wifipolicy")["policyConfig"]
        saved = next(row for row in policies if any(radio["id"] == bssid for radio in row["radioSpecificMetricsPolicy"]))
        (args.output / "saved-policy.json").write_text(json.dumps(saved, indent=2) + "\n")
        source = saved["id"].lower()
        report.update(agent=node, agent_al=source, bssids=bssids)
        controller_wire = Wire("bpibroadband", args.output / "controller-wire.jsonl")
        wires.append(controller_wire)
        agent_wire = Wire(node, args.output / "agent-wire.jsonl")
        wires.append(agent_wire)

        def reports_since(mark):
            return [row for row in controller_wire.since(mark) if row.get("report") and row["source"] == source]

        def loads_since(mark, value):
            return [row for row in reports_since(mark) if any(
                load["bssid"] == bssid and load["utilization"] == value for load in row["report"]["loads"])]

        info = command("lxc", "exec", node, "--", "iw", "dev", "wifi0", "info")
        phy = next(line.split()[1] for line in info.splitlines() if line.strip().startswith("wiphy "))
        context_path = Path(f"/sys/kernel/debug/ieee80211/phy{phy}/hwsim/rf_survey")

        def context(value):
            require(fixture.poll() is None and not lease_errors, "fixture or maintenance lease failed")
            available, rows = parse_contexts(context_path.read_text())
            current = next(row for row in rows if row["frequency_mhz"] == 2437)
            if not available or not current["valid"] or current["active_us"] <= 0:
                return None
            current["utilization"] = round(255 * current["busy_us"] / current["active_us"])
            return current if current["utilization"] == value else None

        command("systemctl", "is-active", "--quiet", "wmdcfg-survey-bridge")
        command("systemctl", "stop", "wmdcfg-survey-bridge")
        bridge_stopped = True
        mark = time.monotonic_ns()
        fixed(32)
        baseline = wait_for(lambda: loads_since(mark, 32), 20, "low fixture did not reach native AP Metrics")
        report["periodic_low_control"] = {"passed": True, "reports": len(baseline), "value": 32}
        modified = deepcopy(saved)
        modified["apMetricReportingPolicy"]["interval"] = 120
        for radio in modified["radioSpecificMetricsPolicy"]:
            radio.update(apUtilizationThreshold=128, starCPIThreshold=0)
        policy_mark = time.monotonic_ns()
        configure(modified)
        requests = wait_for(lambda: [row for row in agent_wire.since(policy_mark) if row.get("policy", {}).get("interval") == 120
                                    and row["destination"] == source], 10, "policy did not reach selected agent")
        policy_request = requests[-1]
        controller_al = policy_request["source"]
        report["controller_al"] = controller_al
        require(all(row["utilization"] == 128 for row in policy_request["policy"]["radios"]), "wire threshold differs")
        wait_for(lambda: [row for row in controller_wire.since(policy_mark) if row["type"] == 0x8000
                          and row["source"] == source and row["message_id"] == policy_request["message_id"]],
                 10, "native policy ACK missing")
        report["policy_delivery"] = {"passed": True, "request": policy_request, "acknowledged": True}
        time.sleep(6)
        silence_mark = time.monotonic_ns()
        time.sleep(6)
        require(not reports_since(silence_mark), "periodic traffic still present in isolation window")
        report["periodic_isolation"] = {"passed": True, "interval_seconds": 120, "quiet_seconds": 6}
        report["threshold"] = {}
        for direction, value in (("upward", 224), ("downward", 32)):
            mark = time.monotonic_ns()
            fixed(value)
            observed = wait_for(lambda: context(value),
                                5, "driver did not apply threshold fixture")
            time.sleep(15)
            final_driver = context(value)
            require(final_driver is not None, "driver fixture changed during threshold observation")
            rows = reports_since(mark)
            matching = [row for row in rows if any(load["bssid"] == bssid and load["utilization"] == value
                                                 for load in row["report"]["loads"])]
            report["threshold"][direction] = {"state": "observed" if matching else "not_observed",
                "driver": observed, "driver_after": final_driver,
                "threshold": 128, "seconds": (time.monotonic_ns() - mark) / 1e9,
                "native_reports": len(rows), "matching_reports": len(matching),
                "stimulus_to_report_seconds": (matching[0]["monotonic_ns"] - mark) / 1e9 if matching else None}
        report["query"] = []
        base_id = 0xD800 + os.getpid() % 256
        for offset, current_bssid in enumerate(bssids):
            identifier = base_id + offset
            payload = bytes.fromhex("93000701") + bytes.fromhex(current_bssid.replace(":", ""))
            mark = time.monotonic_ns()
            controller_wire.send(frame_for(controller_al, source, 0x800B, identifier, payload))
            received = wait_for(lambda: [row for row in agent_wire.since(mark) if row["type"] == 0x800B
                              and row["message_id"] == identifier and row["destination"] == source],
                     3, "AP Metrics Query did not reach agent")
            time.sleep(3)
            responses = [row for row in reports_since(mark) if query_matches(row, identifier, current_bssid, 32)]
            latency = (responses[0]["monotonic_ns"] - received[0]["monotonic_ns"]) / 1e9 if responses else None
            report["query"].append({"bssid": current_bssid, "message_id": identifier,
                "request_received": True, "matched_responses": len(responses), "budget_seconds": 3,
                "response_seconds": latency,
                "state": "observed" if latency is not None and 0 <= latency <= 1 else "not_observed"})
        mark = time.monotonic_ns()
        identifier = base_id + 3
        controller_wire.send(frame_for(controller_al, source, 2, identifier, b""))
        wait_for(lambda: [row for row in controller_wire.since(mark) if row["type"] == 3
                          and row["source"] == source and row["message_id"] == identifier],
                 5, "positive topology-query transport control failed")
        report["query_transport_control"] = {"passed": True, "message_id": identifier}
        require((time.monotonic_ns() - policy_mark) / 1e9 < 110, "isolation exceeded periodic guard")
        if args.extended:
            modified["apMetricReportingPolicy"]["interval"] = 0
            configure(modified)
            time.sleep(6)
            report["zero_interval"] = {}
            for direction, value in (("upward", 224), ("downward", 32)):
                mark = time.monotonic_ns()
                fixed(value)
                wait_for(lambda: context(value), 5, "zero-interval driver fixture missing")
                rows = wait_for(lambda: loads_since(mark, value), 8, "threshold failed with periodic reporting disabled")
                time.sleep(3)
                require(len(loads_since(mark, value)) == 1, "threshold repeatedly reported an unchanged side")
                report["zero_interval"][direction] = {"passed": True,
                    "stimulus_to_report_seconds": (rows[0]["monotonic_ns"] - mark) / 1e9}
            for radio in modified["radioSpecificMetricsPolicy"]:
                radio["apUtilizationThreshold"] = 0
            configure(modified)
            time.sleep(3)
            mark = time.monotonic_ns()
            fixed(224)
            wait_for(lambda: context(224), 5, "disabled-threshold fixture missing")
            time.sleep(5)
            require(not reports_since(mark), "disabled thresholds or periodic timer emitted reports")
            report["threshold_disabled"] = {"passed": True}
            pending = {}
            for offset, current_bssid in enumerate(bssids):
                identifier = base_id + 10 + offset
                payload = bytes.fromhex("93000701") + bytes.fromhex(current_bssid.replace(":", ""))
                pending[identifier] = current_bssid
                controller_wire.send(frame_for(controller_al, source, 0x800B, identifier, payload))
            rows = wait_for(lambda: [row for row in reports_since(mark)
                if row["message_id"] in pending and query_matches(row, row["message_id"], pending[row["message_id"]], 224)],
                3, "queries did not refresh utilization with all reporting disabled")
            time.sleep(1)
            matched = {row["message_id"] for row in reports_since(mark) if row["message_id"] in pending
                and query_matches(row, row["message_id"], pending[row["message_id"]], 224)}
            require(matched == set(pending), "overlapping query MIDs or BSSIDs were lost")
            report["overlapping_fresh_queries"] = {"passed": True, "message_ids": sorted(matched), "utilization": 224}
            mark = time.monotonic_ns()
            accepted = fetch("ap_metrics_query", {"AlMac": source, "BSSIDs": [bssid]})
            require(accepted.get("state") == "submitted", "native controller did not submit AP query")
            received = wait_for(lambda: [row for row in agent_wire.since(mark) if row["type"] == 0x800B
                and row["source"] == controller_al and row["destination"] == source],
                3, "controller-submitted query was not received")
            identifier = received[0]["message_id"]
            rows = wait_for(lambda: [row for row in reports_since(mark)
                if query_matches(row, identifier, bssid, 224)], 3, "controller-submitted query did not complete")
            latency = (rows[0]["monotonic_ns"] - received[0]["monotonic_ns"]) / 1e9
            require(0 <= latency <= 1, "controller-submitted query exceeded one-second response budget")
            report["controller_query"] = {"passed": True, "message_id": identifier, "response_seconds": latency}
            mark = time.monotonic_ns()
            require(fetch("ap_metrics_query", {"AlMac": source, "BSSIDs": bssids}).get("state") == "submitted",
                    "multi-BSSID query was not submitted")
            received = wait_for(lambda: [row for row in agent_wire.since(mark) if row["type"] == 0x800B
                and row["source"] == controller_al and row["destination"] == source],
                3, "multi-BSSID query did not reach agent")
            identifier = received[0]["message_id"]
            rows = wait_for(lambda: [row for row in reports_since(mark) if row["message_id"] == identifier
                and len(row["report"]["loads"]) == len(bssids)
                and {load["bssid"] for load in row["report"]["loads"]} == set(bssids)
                and all(load["utilization"] == 224 for load in row["report"]["loads"])],
                3, "multi-BSSID query lost selection or utilization")
            latency = (rows[0]["monotonic_ns"] - received[0]["monotonic_ns"]) / 1e9
            require(0 <= latency <= 1, "multi-BSSID query exceeded one-second response budget")
            report["multi_bssid_query"] = {"passed": True, "message_id": identifier, "response_seconds": latency}
            mark = time.monotonic_ns()
            for payload, status in (({}, 400),
                ({"AlMac": source, "BSSIDs": ["not-a-mac"]}, 400),
                ({"AlMac": source, "BSSIDs": [bssid] * 25}, 400),
                ({"AlMac": source, "BSSIDs": ["02:ff:ff:ff:ff:ff"]}, 503)):
                try:
                    fetch("ap_metrics_query", payload)
                except HTTPError as error:
                    require(error.code == status, "unexpected invalid-query response")
                else:
                    raise RuntimeError("invalid or foreign-BSSID query was accepted")
            require(not [row for row in agent_wire.since(mark) if row["type"] == 0x800B],
                    "rejected API query emitted a native request")
            report["invalid_queries"] = {"passed": True, "cases": 4}
            fixed(32)
            wait_for(lambda: context(32), 5, "restoration fixture missing")
        configure(saved)
        mark = time.monotonic_ns()
        wait_for(lambda: loads_since(mark, 32), 20, "restored periodic native reports did not resume")
        report["periodic_restoration"] = {"passed": True, "value": 32}
        report["audit_completed"] = True
        report["state"] = "passed" if (all(row["state"] == "observed" for row in report["query"])
            and all(row["state"] == "observed" for row in report["threshold"].values())) else "incomplete-native-support"
    except Exception as error:
        report["error"] = str(error)
    finally:
        if saved is not None:
            try:
                configure(saved)
                report["policy_restored"] = True
            except Exception as error:
                report["restoration_errors"].append("policy: " + str(error))
        if fixture is not None:
            fixture.terminate()
            try:
                fixture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                fixture.kill()
                fixture.wait(timeout=5)
            fixture_log.close()
        if bridge_stopped:
            try:
                command("systemctl", "start", "wmdcfg-survey-bridge")
                report["survey_bridge_restored"] = True
            except Exception as error:
                report["restoration_errors"].append("bridge: " + str(error))
        for wire in reversed(wires):
            try:
                wire.close()
            except Exception as error:
                report["restoration_errors"].append("capture: " + str(error))
        lease_stop.set()
        if lease_thread is not None:
            lease_thread.join(timeout=12)
        if token is not None:
            try:
                lease_request({"token": token}, "DELETE")
            except Exception as error:
                report["restoration_errors"].append("lease release: " + str(error))
        report["restoration_errors"].extend(lease_errors)
        try:
            report["identity_after"] = identities()
            report["identities_unchanged"] = report["identity_after"] == before
        except Exception as error:
            report["restoration_errors"].append("service identities: " + str(error))
            report["identities_unchanged"] = False
        if report["restoration_errors"] or not report["identities_unchanged"]:
            report["state"] = "failed"
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if not key.startswith("identity_")}), flush=True)
    return 0 if report["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
