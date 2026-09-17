#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


LXC = r'''#!/usr/bin/env python3
import json,os,stat,sys,time
from pathlib import Path
config=json.loads(Path(os.environ['STUB_CONFIG']).read_text())
if sys.argv[1:] == ['list','-c','n','--format','csv']:
    for name in config['inventory']: print(name)
    raise SystemExit(config.get('list_exit',0))
if len(sys.argv) < 5 or sys.argv[1] != 'exec' or sys.argv[3:5] != ['--','ping']:
    raise SystemExit('unexpected LXC invocation')
name=sys.argv[2]
fifo=stat.S_ISFIFO(os.fstat(0).st_mode)
stolen=os.read(0,65536) if config.get('consume_stdin') else b''
record={'name':name,'args':sys.argv[4:],'stdin_fifo':fifo,'stolen':stolen.decode(errors='replace')}
descriptor=os.open(os.environ['STUB_CALLS'],os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
os.write(descriptor,(json.dumps(record)+'\n').encode());os.close(descriptor)
if config.get('slow') == name:time.sleep(.15)
if config.get('failed') == name:raise SystemExit(1)
if config.get('malformed') == name:
    print('No usable statistics')
else:
    loss=10 if config.get('loss') == name else 0
    print('10 packets transmitted, %d received, %d%% packet loss'%(10-loss//10,loss))
'''

SORT = r'''#!/usr/bin/env python3
import os,subprocess,sys,time
result=subprocess.run(['/usr/bin/sort',*sys.argv[1:]],input=sys.stdin.buffer.read(),capture_output=True)
for line in result.stdout.splitlines(keepends=True):
    sys.stdout.buffer.write(line);sys.stdout.buffer.flush()
    if os.environ.get('STUB_PACE')=='1':time.sleep(.003)
raise SystemExit(result.returncode)
'''


def names(count):
    return (["wlan-client"] + [f"wlan-client-{index:03d}" for index in range(1, count)]) if count else []


def run_case(body, name, expected=100, inventory=None, reject_roster=False, pass_expected=True, **options):
    config = {"inventory": names(expected) if inventory is None else inventory, **options}
    with tempfile.TemporaryDirectory(prefix="audit-traffic-fixture-") as temporary:
        directory = Path(temporary)
        config_path = directory / "config.json"
        calls_path = directory / "calls.jsonl"
        config_path.write_text(json.dumps(config))
        for filename, content in (("lxc", LXC), ("sort", SORT)):
            path = directory / filename
            path.write_text(content)
            path.chmod(0o755)
        script = directory / "audit.sh"
        script.write_text('''set -euo pipefail
exec </dev/null
status_section() { :; }
status_wait() { :; }
ping_count=10 ping_interval=1 ping_max_loss=0 ping_exec_attempts=2 ping_exec_timeout=5
''' + f"expected_clients={expected}\n" + body + '\nexit "$traffic_fail"\n')
        environment = dict(os.environ, PATH=str(directory) + ":" + os.environ["PATH"],
                           STUB_CONFIG=str(config_path), STUB_CALLS=str(calls_path),
                           STUB_PACE="1" if config.get("consume_stdin") else "0")
        completed = subprocess.run(["bash", str(script)], env=environment, text=True,
                                   capture_output=True, timeout=30)
        calls = [json.loads(line) for line in calls_path.read_text().splitlines()] if calls_path.exists() else []
    rows = re.findall(r"^(wlan-client(?:-[0-9]{3})?) ([^\n]+)$", completed.stdout, re.M)
    checks = {"exit_matches": (completed.returncode == 0) == pass_expected}
    if reject_roster:
        checks["no_partial_traffic_launch"] = not calls and not rows
    else:
        checks["all_exact_clients_launched"] = {call["name"] for call in calls} == set(names(expected))
        checks["all_exact_clients_reported_once"] = len(rows) == expected and {row[0] for row in rows} == set(names(expected))
        checks["unchanged_ping_parameters"] = all(call["args"] == ["ping", "-q", "-c", "10", "-i", "1", "-W", "2", "10.0.0.1"] for call in calls)
        if config.get("consume_stdin"):
            checks["no_roster_pipe_inheritance"] = not any(call["stdin_fifo"] for call in calls)
            checks["no_roster_bytes_stolen"] = not any(call["stolen"] for call in calls)
        if config.get("failed"):
            checks["existing_bounded_retry_preserved"] = sum(call["name"] == config["failed"] for call in calls) == 2
    return {"name": name, "pass": all(checks.values()), "checks": checks,
            "exit_code": completed.returncode, "reported_clients": len(rows), "call_count": len(calls),
            "stolen_bytes": sum(len(call["stolen"]) for call in calls),
            "stdout": completed.stdout, "stderr": completed.stderr, "calls": calls}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.read_text()
    body = source[source.index('status_section "End-to-end traffic"'):source.index('if [ -s "$results" ]')]
    cases = [
        run_case(body, "full20", expected=20),
        run_case(body, "full100"),
        run_case(body, "stdin_consumer", consume_stdin=True),
        run_case(body, "short91", inventory=names(91), reject_roster=True, pass_expected=False),
        run_case(body, "empty", inventory=[], reject_roster=True, pass_expected=False),
        run_case(body, "failed_listing_with_full_output", list_exit=7, reject_roster=True, pass_expected=False),
        run_case(body, "failed_listing_empty", inventory=[], list_exit=7, reject_roster=True, pass_expected=False),
        run_case(body, "duplicate_same_count", inventory=names(99) + ["wlan-client-098"], reject_roster=True, pass_expected=False),
        run_case(body, "wrong_identity_same_count", inventory=names(99) + ["wlan-client-100"], reject_roster=True, pass_expected=False),
        run_case(body, "extra_client", inventory=names(101), reject_roster=True, pass_expected=False),
        run_case(body, "missing_middle", inventory=[name for name in names(100) if name != "wlan-client-050"], reject_roster=True, pass_expected=False),
        run_case(body, "native_ping_failure", failed="wlan-client-050", pass_expected=False),
        run_case(body, "missing_ping_statistics", malformed="wlan-client-010", pass_expected=False),
        run_case(body, "nonzero_loss", loss="wlan-client-010", pass_expected=False),
        run_case(body, "unrelated_containers", inventory=["bpibroadband", "bpiap", "unrelated-project"] + names(100)),
        run_case(body, "waits_for_each_child", slow="wlan-client-070"),
    ]
    result = {"source": str(args.source.resolve()), "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
              "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
              "scope": "Complete production traffic section executed in bash with local LXC/list/ping stubs; no lab commands", "cases": cases,
              "passed": sum(case["pass"] for case in cases), "total": len(cases)}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for case in cases:
        failed = [key for key, value in case["checks"].items() if not value]
        print(f"{'PASS' if case['pass'] else 'FAIL'} {case['name']} exit={case['exit_code']} rows={case['reported_clients']} stolen_bytes={case['stolen_bytes']} {failed}")
    print(f"RESULT {result['passed']}/{result['total']} PASS")
    return 0 if all(case["pass"] for case in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
