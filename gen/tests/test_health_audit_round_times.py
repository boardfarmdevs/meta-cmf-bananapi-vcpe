"""The health audit's traffic rounds carry their times, the medium's netlink refusals before and
during each (its timed log) and every client's link as the round starts (health-audit.sh
medium_counts, traffic_round, traffic_rounds): a lossy first round right after a bring-up is
told apart from a fault by them."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
AUDIT = (ROOT / "gen/tests/health-audit.sh").read_text()

LOG_1 = """\
2026-10-09T13:19:59.000001Z nl: cmd 2, seq 1: Invalid argument
2026-10-09T13:20:00.000001Z nl: cmd 2, seq 2: Invalid argument
"""
LOG = """\
2026-10-09T13:20:10.000000Z nl: cmd 2, seq 3: Invalid argument
2026-10-09T13:20:20.000000Z nl: cmd 3, seq 4: Invalid argument
2026-10-09T13:20:30.000000Z wmediumd: something else
2026-10-09T13:21:00.000000Z nl: cmd 3, seq 5: Invalid argument
"""


def function(name):
    return re.search(rf"^{name}\(\) \{{.*?^\}}", AUDIT, re.MULTILINE | re.DOTALL).group() + "\n"


def counts(tmp_path, start, end, with_rotation=True):
    (tmp_path / "wmediumd.log").write_text(LOG)
    if with_rotation:
        (tmp_path / "wmediumd.log.1").write_text(LOG_1)
    script = "set -euo pipefail\n" + f"medium_runtime={tmp_path}\n" + function("medium_counts") + \
        f'medium_counts "{start}" "{end}"\n'
    return subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True).stdout


def test_the_refusals_between_two_stamps_counted_by_command_across_the_rotation(tmp_path):
    assert counts(tmp_path, "2026-10-09T13:20:00.000000Z", "2026-10-09T13:20:59.999999Z") == "cmd2=2 cmd3=1"
    assert counts(tmp_path, "2026-10-09T13:19:00.000000Z", "2026-10-09T13:22:00.000000Z") == "cmd2=3 cmd3=2"


def test_no_log_or_no_rotation_counts_what_there_is(tmp_path):
    assert counts(tmp_path, "2026-10-09T13:19:00.000000Z", "2026-10-09T13:22:00.000000Z",
                  with_rotation=False) == "cmd2=1 cmd3=2"
    script = "set -euo pipefail\n" + f"medium_runtime={tmp_path / 'none'}\n" + function("medium_counts") + \
        'medium_counts 2026-10-09T13:19:00Z 2026-10-09T13:22:00Z\n'
    out = subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True).stdout
    assert out == "cmd2=0 cmd3=0"


def test_the_stamps_sort_as_the_medium_log_does():
    script = function("stamp") + "stamp\n"
    out = subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True).stdout.strip()
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", out)


def test_each_round_reports_its_times_and_the_medium_and_each_client_its_link():
    rounds = function("traffic_rounds")
    assert 'traffic_round "$round"' in rounds
    assert re.search(r'echo "ROUND_TIME round=\$round start=\$start end=\$end" \\\n\s+"medium_before '
                     r'\$\(medium_counts "\$mark" "\$start"\) medium_during \$\(medium_counts "\$start" "\$end"\)"',
                     rounds)
    assert "mark=${audit_start:-$(stamp)}" in rounds
    one = function("traffic_round")
    assert 'echo "LINK round=$1 $client $link"' in one
    # the link is read before the ping, and its failure never fails the client's round
    assert one.index("iw dev wlan0 station dump") < one.index("ping -q")
    assert re.search(r"connected=%s\", b \? b : \"none\", c != \"\" \? c \"s\" : \"-\"\}'\) \|\| true", one)
    # the medium's helpers sit in the traffic section, which the traffic test runs on its own
    section = AUDIT[AUDIT.index('status_section "End-to-end traffic"'):AUDIT.index('if [ -s "$results" ]')]
    assert "stamp() {" in section and "medium_counts() {" in section
