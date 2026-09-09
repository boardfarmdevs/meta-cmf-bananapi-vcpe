import json
import os
from pathlib import Path
import subprocess

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh/steer.sh"
STA = "02:00:00:00:03:00"
TARGET = "02:00:00:aa:aa:02"
CURRENT = "02:00:00:aa:aa:01"
ROW = CURRENT + "\tOneWifiMesh@02:00:00:00:01:20@02:00:00:00:01:00@" + CURRENT + "@0\t1"


@pytest.mark.parametrize("rows, expected, successful", [(ROW, CURRENT, True), (ROW, TARGET, False),
    (ROW + "\n" + ROW, CURRENT, False), ("", CURRENT, False)])
def test_single_atomic_inventory_lookup_preserves_source_guard(tmp_path, rows, expected, successful):
    mysql = tmp_path / "mysql"
    mysql.write_text('#!/bin/sh\nprintf "call\\n" >> "$CALL_LOG"\nprintf "%s\\n" "$ROWS"\n')
    mysql.chmod(0o755)
    driver = tmp_path / "driver"
    driver.write_text('#!/bin/sh\ncat "$2" > "$PAYLOAD"\necho steer_drv_status=Success\n')
    driver.chmod(0o755)
    script = tmp_path / "steer.sh"
    script.write_text(SOURCE.read_text().replace('/usr/bin/steer_drv', str(driver))
                      .replace('/tmp/steer-${STA}.json', str(tmp_path / "request.json")))
    result = subprocess.run(["sh", str(script), STA, TARGET, "115", "36", "gentle", expected],
        capture_output=True, text=True, timeout=3,
        env={**os.environ, "PATH": str(tmp_path) + ":" + os.environ["PATH"], "ROWS": rows,
             "CALL_LOG": str(tmp_path / "calls"), "PAYLOAD": str(tmp_path / "payload")})
    assert (result.returncode == 0) == successful, result.stderr
    assert (tmp_path / "calls").read_text() == "call\n"
    if successful:
        network = json.loads((tmp_path / "payload").read_text())["wfa-dataelements:ClientSteer"]["Network"]
        assert network["DeviceList"][0]["ID"] == "02:00:00:00:01:20"
        station = network["DeviceList"][0]["RadioList"][0]["BSSList"][0]["STAList"][0]
        assert station["ClientSteer"]["BTMDisassociationImminent"] is False
    else:
        assert not (tmp_path / "payload").exists()
