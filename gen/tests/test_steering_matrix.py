from pathlib import Path
import re
import subprocess

import pytest


SOURCE = Path(__file__).with_name("steering-matrix.sh").read_text()


def function(name):
    return re.search(rf"^{name}\(\) \{{.*?^\}}", SOURCE, re.MULTILINE | re.DOTALL).group() + "\n"


def test_candidate_discovery_is_scan_only():
    script = '''
ssid=private_ssid
lxc() {
    case "${*: -1}" in
        scan_results) printf '02:00:00:00:01:00\\t5180\\t-30\\t[WPA2]\\tprivate_ssid\\n' ;;
        *) [[ "$*" == *'scan TYPE=ONLY freq=5180'* ]] || return 2; echo OK ;;
    esac
}
sleep() { return 0; }
''' + function("prime_candidate_scan") + '\nprime_candidate_scan station 02:00:00:00:01:00 5180\n'
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("actual,expected_rc", [("source", 0), ("target", 1), ("", 1)])
def test_pre_request_rejects_autonomous_roaming(actual, expected_rc):
    script = '''
client_bssid() { printf '%s' "$ACTUAL"; }
curl() { echo model; }
jq() { echo source; }
''' + function("verify_steering_source") + '\nverify_steering_source station mac source\n'
    result = subprocess.run(["bash", "-c", script], env={"ACTUAL": actual},
                            capture_output=True, text=True)
    assert result.returncode == expected_rc
    if expected_rc:
        assert "no steering request sent" in result.stderr


def test_source_is_verified_after_scan_and_before_request():
    body = SOURCE[SOURCE.index('for ((round=1;'):]
    assert body.index('prime_candidate_scan "$client"') < body.index('verify_steering_source "$client"')
    assert body.index('verify_steering_source "$client"') < body.index('/usr/bin/steer.sh')
