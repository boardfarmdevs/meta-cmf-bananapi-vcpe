"""The lab VM keeps its cores, its containers' included, across its restarts
(gen/vm/scripts/guest/easymesh-save-core and easymesh-core-watch.service, installed by
50-runtime-service.sh): a hand-set core pattern was disarmed by a VM restart, which gives
apport's back (rdk-1004, 9 October)."""
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
GUEST = ROOT / "gen/vm/scripts/guest"
HELPER = GUEST / "easymesh-save-core"
UNIT = (GUEST / "easymesh-core-watch.service").read_text()


def save(tmp_path, name, pid, stamp, data):
    subprocess.run(["sh", str(HELPER), name, pid, stamp], input=data, check=True,
                   env=dict(os.environ, EASYMESH_CORE_DIR=str(tmp_path)))


def test_a_core_lands_in_the_vms_crash_directory_by_name_pid_and_time(tmp_path):
    save(tmp_path, "OneWifi", "4242", "1791540000", b"core bytes")
    assert (tmp_path / "core.OneWifi.4242.1791540000").read_bytes() == b"core bytes"


def test_the_cores_are_bounded_in_size_and_number(tmp_path):
    assert "head -c 1073741824 >" in HELPER.read_text()
    now = time.time()
    for n in range(12):
        old = tmp_path / f"core.old.{n}.0"
        old.write_bytes(b"x")
        os.utime(old, (now - 1000 + n, now - 1000 + n))
    save(tmp_path, "OneWifi", "1", "2", b"new")
    left = sorted(p.name for p in tmp_path.iterdir())
    assert len(left) == 10 and "core.OneWifi.1.2" in left
    assert "core.old.0.0" not in left and "core.old.2.0" not in left and "core.old.11.0" in left


def test_the_pattern_pipes_to_the_helper_after_apport_at_every_boot():
    assert re.search(r"^After=.*\bapport\.service\b", UNIT, re.MULTILINE)
    assert re.search(r"^After=.*\bsystemd-sysctl\.service\b", UNIT, re.MULTILINE)
    # %% in a unit is a literal %: the kernel gets |helper %e %P %t (the global PID)
    assert ('echo "|/usr/local/sbin/easymesh-save-core %%e %%P %%t" > /proc/sys/kernel/core_pattern'
            in UNIT)
    assert re.search(r"^WantedBy=multi-user\.target$", UNIT, re.MULTILINE)


def test_the_vm_installs_and_enables_it_and_a_build_pushes_it():
    runtime = (ROOT / "gen/vm/scripts/50-runtime-service.sh").read_text()
    assert "/home/easymesh/easymesh-assets/easymesh-save-core \\\n    /usr/local/sbin/easymesh-save-core" in runtime
    assert ("/home/easymesh/easymesh-assets/easymesh-core-watch.service \\\n"
            "    /etc/systemd/system/easymesh-core-watch.service") in runtime
    assert runtime.index("systemctl enable easymesh-core-watch.service") < \
        runtime.index("systemctl restart easymesh-core-watch.service")
    build = (ROOT / "gen/vm/lxd/build.sh").read_text()
    for name in ("easymesh-save-core", "easymesh-core-watch.service"):
        assert f"[{name}]=gen/vm/scripts/guest/{name}" in build
    assert os.access(HELPER, os.X_OK)
