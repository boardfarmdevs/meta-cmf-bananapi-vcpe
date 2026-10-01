"""The lab's side of the LXD monitoring bundle (easymesh-medium's lxd-monitoring/): its
wrapper with this lab's ports, the import's opt-in flag and the exports' copy."""

from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
LXD = ROOT / "gen/vm/lxd"


def test_import_monitoring_is_explicit_and_exports_carry_the_medium_bundle():
    importer = (LXD / "import.sh").read_text()
    assert "monitoring=false" in importer.lower() and "--monitoring)" in importer
    assert "observability/enable.sh" in importer and '"$monitoring" = true' in importer.lower()
    source = (LXD / "build.sh").read_text()
    assert "test ! -d /opt/easymesh-observability" in source
    assert "find observability -type f" in source
    assert source.count('cp -a "$root/gen/medium/lxd-monitoring" "$bundle/observability"') == 2
    assert source.count('rm -rf "$bundle/observability/tests"') == 2


def test_the_wrapper_runs_the_medium_bundle_with_this_vms_ports(tmp_path):
    lab = tmp_path / "gen/vm/lxd"
    lab.mkdir(parents=True)
    shutil.copy(LXD / "monitoring.sh", lab)
    shutil.copy(LXD / "instance-config.sh", lab)
    bundle = tmp_path / "gen/medium/lxd-monitoring"
    bundle.mkdir(parents=True)
    (bundle / "enable.sh").write_text('echo "$* base=$LAB_PORT_BASE"\n')
    expected = subprocess.run(
        ["bash", "-c", '. "$1" && easymesh_instance_port_base rdk-1001', "-", str(LXD / "instance-config.sh")],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    result = subprocess.run(["bash", str(lab / "monitoring.sh"), "enable", "rdk-1001", "192.0.2.1"],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == f"rdk-1001 192.0.2.1 base={expected}"
    refused = subprocess.run(["bash", str(lab / "monitoring.sh"), "setup", "rdk-1001"],
                             capture_output=True, text=True)
    assert refused.returncode == 2
