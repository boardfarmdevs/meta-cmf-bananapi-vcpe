"""The health audit's failed traffic check keeps the medium's state (health-audit.sh medium_evidence):
its telemetry, configuration and logs, the previous start's included, the last five kept."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
AUDIT = (ROOT / "gen/tests/health-audit.sh").read_text()


def function(name):
    return re.search(rf"^{name}\(\) \{{.*?^\}}", AUDIT, re.MULTILINE | re.DOTALL).group() + "\n"


def run(tmp_path, telemetry_ok, calls):
    runtime = tmp_path / "run"
    runtime.mkdir(exist_ok=True)
    for name in ("wmediumd.cfg", "wmediumd.log", "wmediumd.log.prev"):
        (runtime / name).write_text(f"{name}\n")
    curl_body = """echo '{"packet_metrics": {}}'""" if telemetry_ok else "return 7"
    script = f'''
set -euo pipefail
medium_runtime={runtime}
medium_telemetry=http://fixture/api/v1/telemetry
medium_evidence_root={tmp_path / "evidence"}
n=0
date() {{ printf '20261009T0600%02dZ\\n' "$n"; }}
curl() {{ {curl_body}; }}
''' + function("medium_evidence") + f'''
for n in $(seq 1 {calls}); do medium_evidence; done
'''
    return subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True).stdout


def test_a_failed_traffic_check_keeps_the_mediums_state(tmp_path):
    out = run(tmp_path, True, 1)
    kept = tmp_path / "evidence" / "20261009T060001Z"
    assert sorted(p.name for p in kept.iterdir()) == [
        "telemetry.json", "wmediumd.cfg", "wmediumd.log", "wmediumd.log.prev"]
    assert out.strip() == f"MEDIUM_EVIDENCE {kept} (telemetry.json wmediumd.cfg wmediumd.log wmediumd.log.prev)"


def test_without_the_observer_the_logs_are_kept_and_the_last_five(tmp_path):
    run(tmp_path, False, 7)
    dirs = sorted(p.name for p in (tmp_path / "evidence").iterdir())
    assert dirs == [f"20261009T0600{n:02d}Z" for n in range(3, 8)]
    assert not (tmp_path / "evidence" / dirs[-1] / "telemetry.json").exists()


def test_it_runs_only_when_the_traffic_check_failed():
    assert '[ "$traffic_fail" = 0 ] || medium_evidence' in AUDIT
    # after the traffic section the traffic test executes (health-audit-traffic-test.py)
    assert AUDIT.index("|| medium_evidence") > AUDIT.index('if [ -s "$results" ]')
