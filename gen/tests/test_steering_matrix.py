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


def test_the_end_counts_the_labs_own_clients_not_backhaul_station_rows():
    # rdk-1009, 9 October: 50 moves passed, then a bare count of every station row (the
    # extenders' and pods' backhaul stations among them) differed and the matrix exited mute
    script = (
        "lab_client_macs=$'02:00:00:00:03:00\\n02:00:00:00:04:00'\n"
        + function("lab_clients_in_topology")
        + 'lab_clients_in_topology "$1"\n'
    )
    topology = ('{"nodes": [{"STAList": [{"staMAC": "02:00:00:00:03:00"}, {"staMAC": "02:00:00:4D:06:73"}]},'
                ' {"STAList": [{"staMAC": "02:00:00:00:04:00"}, {"staMAC": "02:00:00:00:04:00"}]}, {}]}')
    out = subprocess.run(["bash", "-c", script, "-", topology], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "2"
    out = subprocess.run(["bash", "-c", script, "-", '{"nodes": []}'], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "0"
    end = SOURCE[SOURCE.index("restore_medium\n\ntopology="):]
    assert 'final_total_clients=$(lab_clients_in_topology "$topology")' in end
    assert re.search(r'if \[ "\$final_total_clients" -ne "\$expected_total_clients" \]; then\n'
                     r'\s+echo "FAIL: the topology holds .*" >&2\n\s+failures=\$\(\(failures \+ 1\)\)', end)
    assert 'expected_total_clients=$(lab_clients_in_topology "$topology")' in SOURCE


def test_a_client_not_associated_at_its_turn_is_a_named_failed_move():
    loop = SOURCE[SOURCE.index('for ((round=1;'):]
    head = loop[:loop.index('target_index=')]
    assert 'if ! sta=$(client_mac "$client") || ! source=$(client_bssid "$client" 50); then' in head
    assert 'echo "FAIL: $client has no station MAC or is not associated before its move' in head
    assert "failures=$((failures + 1))" in head and "continue" in head
    # its row has the CSV's 15 columns
    row = re.search(r"printf '((?:%s,){14}%s)\\n' \\\n(.*?)\| tee -a \"\$results\"", head, re.DOTALL)
    assert row and len(re.findall(r'"[^"]*"|\S+', row.group(2).replace("\\\n", " "))) == 15
