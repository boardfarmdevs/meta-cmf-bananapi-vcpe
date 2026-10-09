"""The health audit's traffic rounds carry their times, the medium's netlink refusals before and
during each (its timed log) and every client's link as the round starts (health-audit.sh
medium_counts, traffic_round, traffic_rounds): a lossy first round right after a bring-up is
told apart from a fault by them."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
AUDIT = (ROOT / "gen/tests/health-audit.sh").read_text()
# the medium's telemetry is read with jq, a host tool of the suite (install-host.sh)
needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed on this host")

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


def medium(script_body, tmp_path, curl_body):
    script = "set -euo pipefail\n" + f"medium_runtime={tmp_path}\n" + \
        "medium_telemetry=http://fixture/api/v1/telemetry\n" + \
        f"curl() {{ {curl_body}; }}\n" + function("medium_snapshot") + function("medium_round") + script_body
    return subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True).stdout.strip()


SUMMARY = ('{"packet_metrics": {"summary": {"frames_seen": %d, "management_frames": 80, "data_frames": 20,'
           ' "multicast_frames": 70, "netlink_clone_einval": 5, "netlink_other_errors": %d,'
           ' "queue_delay_usec_max": %d, "queue_depth_max": 40%s}}}')


@needs_jq
def test_a_round_shows_the_mediums_traffic_refusals_backlog_and_cpu(tmp_path):
    # the shell itself stands in for wmediumd: its CPU ticks are real
    body = '''echo $$ > "$medium_runtime/wmediumd.pid"
before=$(medium_snapshot)
n=1
after=$(medium_snapshot)
echo "$before"
medium_round "$before" "$after"
'''
    bound = ', "drops_queue_bound": %d'
    curl = (f"if [ \"${{n:-0}}\" = 1 ]; then echo '{SUMMARY % (1500, 9, 2500000, bound % 37)}';"
            f" else echo '{SUMMARY % (100, 4, 900000, bound % 12)}'; fi")
    snapshot, line = medium(body, tmp_path, curl).splitlines()
    assert re.fullmatch(r"100 80 20 70 5 4 900000 40 12 \d+", snapshot)
    # the queue maxima are the medium's lifetime ones, marked when the round raised them; the
    # queue-bound drops are the round's own
    assert re.fullmatch(r"frames=1400 management=0 data=0 multicast=0 clone_einval=0 other_errors=5 "
                        r"queue_bound_drops=25 lifetime_queue_delay_max_usec=2500000\(new\) "
                        r"lifetime_queue_depth_max=40 wmediumd_cpu_s=\d+\.\d", line)


@needs_jq
def test_a_medium_without_the_queue_bound_has_no_drops_to_give(tmp_path):
    body = 'medium_round "$(medium_snapshot)" "$(medium_snapshot)"\n'
    line = medium(body, tmp_path, f"echo '{SUMMARY % (100, 4, 900000, '')}'")
    assert re.fullmatch(r"frames=0 management=0 data=0 multicast=0 clone_einval=0 other_errors=0 "
                        r"queue_bound_drops=- lifetime_queue_delay_max_usec=900000 "
                        r"lifetime_queue_depth_max=40 wmediumd_cpu_s=-", line)


def radio_drops(before, after):
    script = "set -euo pipefail\n" + function("radio_drops_round") + \
        f"radio_drops_round '{before}' '{after}'\n"
    return subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True).stdout.strip()


def test_the_radios_whose_hwsim_drops_rose_most_first():
    before = "bpibroadband/phy0 14443\nbpiap-001/phy2 10\npod-1/phy108 0\nwlan-client/phy4 3"
    after = "bpibroadband/phy0 14500\nbpiap-001/phy2 2010\npod-1/phy108 0\nwlan-client/phy4 3\npod-2/phy110 9"
    # a radio new in the second snapshot has no before: left out, not counted from 0
    assert radio_drops(before, after) == "bpiap-001/phy2=2000 bpibroadband/phy0=57"
    assert radio_drops(before, before) == "none"
    assert radio_drops("", after) == "unavailable"


def test_the_radios_drops_read_in_every_devices_network_namespace():
    snapshot = function("radio_drops_snapshot")
    assert "lxc list -c np --format csv" in snapshot
    assert 'nsenter -t "$pid" -n iw dev' in snapshot and 'nsenter -t "$pid" -n ethtool -S "$interface"' in snapshot
    assert '$1 == "d_tx_dropped:"' in snapshot
    # one interface per radio: hwsim counts per radio, every interface of it repeats it
    assert "!seen[phy]++" in snapshot
    assert snapshot.rstrip().splitlines()[-2].strip().startswith("return 0")


@needs_jq
def test_without_the_mediums_telemetry_the_round_says_so(tmp_path):
    assert medium('medium_round "$(medium_snapshot)" "$(medium_snapshot)"', tmp_path, "return 7") == \
        "medium unavailable"
    nulls = '{"packet_metrics": {"available": false, "summary": {}}}'
    assert medium('medium_round "$(medium_snapshot)" "$(medium_snapshot)"', tmp_path, f"echo '{nulls}'") == \
        "medium unavailable"


def test_each_round_reports_the_medium_beside_its_times():
    rounds = function("traffic_rounds")
    assert rounds.index("before=$(medium_snapshot)") < rounds.index('traffic_round "$round"') \
        < rounds.index("after=$(medium_snapshot)")
    assert 'echo "MEDIUM_ROUND round=$round $(medium_round "$before" "$after")"' in rounds
    assert rounds.index("drops_before=$(radio_drops_snapshot)") < rounds.index('traffic_round "$round"') \
        < rounds.index("drops_after=$(radio_drops_snapshot)")
    assert 'echo "RADIO_DROPS round=$round $(radio_drops_round "$drops_before" "$drops_after")"' in rounds
    section = AUDIT[AUDIT.index('status_section "End-to-end traffic"'):AUDIT.index('if [ -s "$results" ]')]
    assert "medium_snapshot() {" in section and "medium_round() {" in section
    assert "radio_drops_snapshot() {" in section and "radio_drops_round() {" in section
