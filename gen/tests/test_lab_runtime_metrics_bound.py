"""The lab runtime's metrics policy POST is bounded by em_cli's own worst case for the lab's
controller devices (gen/vm/scripts/guest/easymesh-lab-runtime, enable_metrics_reporting): em_cli
applies it device by device, each with up to 8 s to be admitted, 8 s for its commit and 2 s
after it. A fixed 45 s made a slow but successful apply fail every try (rdk-1004, 9 October)."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = (ROOT / "gen/vm/scripts/guest/easymesh-lab-runtime").read_text()


def function(name):
    return re.search(rf"^{name}\(\) \{{.*?^\}}", RUNTIME, re.MULTILINE | re.DOTALL).group() + "\n"


def bound(tmp_path, model_devices, pods):
    instances = ",".join(['{"config": {"user.emosa.role": "pod"}}'] * pods + ['{"config": {}}'] * 3)
    script = f'''
set -euo pipefail
model_devices={model_devices}
lxc() {{ echo '[{instances}]'; }}
curl() {{
    while [ "$#" -gt 0 ]; do [ "$1" = --max-time ] && echo "$2" > {tmp_path}/bound; shift; done
    echo '{{"success": true, "devices": {model_devices + pods}, "radios": {3 * model_devices + pods}}}'
}}
sleep() {{ :; }}
''' + function("enable_metrics_reporting") + "enable_metrics_reporting final 1\n"
    out = subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True).stdout
    assert out.startswith(f"metrics policy active on {model_devices + pods} devices")
    return int((tmp_path / "bound").read_text())


def test_the_bound_covers_em_clis_worst_case_for_every_controller_device(tmp_path):
    # 6 native devices (a wired extender among them) and 2 pods: 8 devices, 18 s each, and margin
    assert bound(tmp_path, 6, 2) == 18 * 8 + 15
    assert bound(tmp_path, 5, 0) == 18 * 5 + 15
    assert bound(tmp_path, 6, 2) > 45


def test_no_fixed_45_second_bound_is_left():
    body = function("enable_metrics_reporting")
    assert "--max-time 45" not in body
    assert 'curl -fsS --max-time "$bound" -X POST' in body
