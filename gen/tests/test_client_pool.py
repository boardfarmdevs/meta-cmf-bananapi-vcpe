from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest


POOL = Path(__file__).resolve().parents[1] / "wlan-client-pool.sh"
CLIENT_HELPER = Path(__file__).resolve().parents[1] / "wlan-client.sh"
CLIENT_START = Path(__file__).resolve().parents[1] / "wlan-client" / "wlan.start"
LAB_RUNTIME = (
    Path(__file__).resolve().parents[1]
    / "vm"
    / "scripts"
    / "guest"
    / "easymesh-lab-runtime"
)


def plan(profile: str) -> str:
    return subprocess.run(
        (str(POOL), "plan", "--profile", profile),
        check=True,
        text=True,
        capture_output=True,
    ).stdout


@pytest.mark.parametrize(
    ("profile", "cohorts", "hwsim"),
    (
        ("small", "private=10\tiot=10\ttotal=20", "required=25\tpool=32"),
        ("medium", "private=25\tiot=25\ttotal=50", "required=55\tpool=64"),
        ("stress", "private=50\tiot=50\ttotal=100", "required=105\tpool=128"),
    ),
)
def test_named_client_profiles_have_stable_counts(profile, cohorts, hwsim):
    output = plan(profile)

    assert f"CLIENTS\t{cohorts}" in output
    assert f"HWSIM\t{hwsim}" in output


def test_small_profile_assigns_distinct_ssid_cohorts_and_security():
    rows = plan("small").splitlines()[4:]

    assert len(rows) == 20
    assert all("\tprivate\t" in row for row in rows[:10])
    assert all("\tiot\t" in row and row.endswith("\tiot_ssid\twpa2\tauto") for row in rows[10:])
    assert rows[8].endswith("\tprivate_ssid\twpa2\t2.4")
    assert rows[9].endswith("\tprivate_ssid\tsae\t6")
    assert rows[9].startswith("9\twlan-client-009\t")
    assert rows[10].startswith("10\twlan-client-010\t")


def test_client_startup_replaces_old_dhcp_lease_before_udhcpc():
    hook = CLIENT_START.read_text()
    helper = CLIENT_HELPER.read_text()
    runtime = LAB_RUNTIME.read_text()

    flush = "ip -4 address flush dev wlan0 scope global"
    assert hook.index(flush) < hook.index("udhcpc -i wlan0")
    assert 'WLANSTART="$HERE/wlan-client/wlan.start"' in helper
    assert 'lxc file push -p "$WLANSTART"' in helper
    assert "verify_client_ipv4_ownership" in runtime
    assert 'addresses=$(lxc exec "$client" -- ip -4 -o address show' in runtime
    assert (
        'if [ "$medium_backend" = userspace ]; then\n'
        "        if [ -f /run/meta-cmf-wmediumd/wmediumd.log ]; then"
    ) in runtime


@pytest.mark.parametrize(
    ("band", "expected"),
    (("2.4", "2412 2484"), ("5", "5180 5825"), ("6", "5935 5955 6135 6195 7115")),
)
def test_band_scope_includes_future_ap_channels_without_crossing_bands(band, expected):
    helper = CLIENT_HELPER.read_text()
    function = re.search(r"((?:active|supported)_band_frequencies\(\) \{.*?\n\})", helper, re.S)
    assert function is not None
    function_name = function[1].split("(", 1)[0]
    environment = os.environ.copy()
    environment["IW_PHY"] = """
Wiphy phy0
    Frequencies:
        * 6135 MHz [37] (33.0 dBm)
        * 2412 MHz [1] (20.0 dBm)
        * 2467 MHz [12] (disabled)
        * 2484 MHz [14] (20.0 dBm)
        * 5180 MHz [36] (30.0 dBm)
        * 5260 MHz [52] (disabled)
        * 5825 MHz [165] (30.0 dBm)
        * 5935 MHz [2] (33.0 dBm)
        * 5955 MHz [1] (33.0 dBm)
        * 5975 MHz [5] (disabled)
        * 6195 MHz [49] (33.0 dBm) (no IR)
        * 7115 MHz [233] (33.0 dBm)
        * 902 MHz [-301] (disabled)
        * 58320 MHz [1] (20.0 dBm)
"""
    environment["IW_DEV"] = "channel 1 (5955 MHz), width: 20 MHz, center1: 5955 MHz"
    script = """
lxc() {
    if [ "$1" = exec ]; then
        if [ "$5" = phy ]; then
            printf '%s\n' "$IW_PHY"
        else
            printf '%s\n' "$IW_DEV"
        fi
    fi
}
""" + function[1] + f'\n{function_name} "$1"\n'
    output = subprocess.run(
        ("bash", "-c", script, "band-scope-test", band),
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    ).stdout.strip()
    assert output == expected


@pytest.mark.parametrize(
    ("band", "scope", "expected"),
    (("6", "", 1), ("6", "supported-phy-v1", 0), ("auto", "", 0)),
)
def test_pool_recreates_legacy_band_pinned_clients(band, scope, expected):
    function = re.search(r"(client_ready\(\) \{.*?\n\})", POOL.read_text(), re.S)
    assert function is not None
    environment = os.environ.copy()
    environment.update(CLIENT_BAND=band, CLIENT_SCOPE=scope)
    script = """
lxc() {
    case "$*" in
        'info '*) printf 'Status: RUNNING\n' ;;
        *user.easymesh.cohort) printf 'private\n' ;;
        *user.easymesh.ordinal) printf '10\n' ;;
        *user.easymesh.ssid) printf 'private_ssid\n' ;;
        *user.easymesh.security) printf 'sae\n' ;;
        *user.easymesh.band) printf '%s\n' "$CLIENT_BAND" ;;
        *user.easymesh.band-scope) printf '%s\n' "$CLIENT_SCOPE" ;;
        *'iw dev wlan0 link') printf 'Connected to 02:00:00:00:00:01\nSSID: private_ssid\nfreq: 5955.0\n' ;;
        *'ip -4 -o addr show wlan0') printf 'inet 10.0.0.9/24\n' ;;
        *) return 1 ;;
    esac
}
""" + function[1] + '\nclient_ready wlan-client-009 private 10 private_ssid sae "$CLIENT_BAND"\n'
    result = subprocess.run(("bash", "-c", script), env=environment, capture_output=True)
    assert result.returncode == expected
    assert 'user.easymesh.band-scope supported-phy-v1' in CLIENT_HELPER.read_text()
