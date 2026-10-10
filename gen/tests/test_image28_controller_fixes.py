"""Image 28's controller and CLI fixes, read from the patches (the lab proofs are on rdk-1010):

- 0260: the agent writes the AP Radio Basic Capabilities TLV's entries back to back: it advances
  past an entry only when it wrote one, no 3-byte hole for an op class of another type;
- 0261: the controller's walk of that TLV is bounded three ways, each refusal logged: the TLV's
  length (its fixed part, and every entry with its channels), EM_MAX_CHANNELS_IN_LIST channels
  per entry (the 64-entry list it copies into), EM_MAX_OPCLASS op classes in the data model;
- 0262: a Topology Response goes to the agent's radio in topology sync, else to its first radio;
- 0263: em_cli's SSID change answers with the controller's status (set_ssid_status.go, go test);
- 0264: an SSID change is refused while a set_ssid, an em_config or a cfg_renew is active."""
from pathlib import Path
import os
import re
import shutil
import subprocess

import pytest

PATCHES = Path(__file__).resolve().parents[2] / "recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh"
SERIES = ["0259-cli-a-renew-route", "0260-agent-ap-radio-basic-capabilities-tlv-without-holes",
          "0261-ctrl-bound-the-ap-radio-basic-capabilities-tlv-walk",
          "0262-ctrl-a-topology-response-to-the-radio-waiting-for-it",
          "0263-cli-set-ssid-answers-with-the-controllers-status",
          "0264-ctrl-set-ssid-refused-while-a-configuration-is-in-flight"]


def in_series(number):
    """0262 and 0264 wait for the owner's word: their checks run only when the series has them."""
    recipe = (PATCHES.parent / "unified-wifi-mesh.bbappend").read_text()
    if not re.search(rf"file://{number}-\S+\.patch", recipe):
        pytest.skip(f"{number} is not in the series")


def patch(number):
    return next(PATCHES.glob(f"{number}-*.patch")).read_text()


def changed(number, sign):
    return [line[1:] for line in patch(number).splitlines()
            if line.startswith(sign) and not line.startswith(sign * 3)]


def test_the_patches_are_in_the_series_in_order():
    recipe = (PATCHES.parent / "unified-wifi-mesh.bbappend").read_text()
    listed = [name for name in SERIES if f"file://{name}.patch" in recipe]
    assert listed[:3] == SERIES[:3]
    assert [recipe.index(name) for name in listed] == sorted(recipe.index(name) for name in listed)
    for name in listed:
        subprocess.run(["git", "apply", "--numstat", str(PATCHES / f"{name}.patch")], check=True, capture_output=True)


def test_0260_advances_only_past_an_entry_it_wrote():
    advance = "op_class = reinterpret_cast<em_op_class_t *>(reinterpret_cast<unsigned char *>(op_class) + sizeof(em_op_class_t) + all_channel_len);"
    # removed at the op class loop's level (12 spaces), added inside the capability branch (16)
    assert "            " + advance in changed("0260", "-")
    assert "                " + advance in changed("0260", "+")
    assert not any(line.startswith("            " + advance) for line in changed("0260", "+"))
    assert any("TLV op class entry %d" in line for line in changed("0260", "+"))


def test_0261_bounds_the_walk_three_ways():
    added = "\n".join(changed("0261", "+"))
    assert "if (len < sizeof(em_ap_radio_basic_cap_t))" in added                     # the fixed part
    assert "(entry + sizeof(em_op_class_t) > buff + len)" in added                    # the entry
    assert "(entry + sizeof(em_op_class_t) + basic_cap_op_class->num > buff + len)" in added   # its channels
    assert "(basic_cap_op_class->num > EM_MAX_CHANNELS_IN_LIST)" in added             # the 64-entry list
    assert "if (dm->get_num_op_class() >= EM_MAX_OPCLASS)" in added                   # the data model's list
    assert added.count("em_printfout(") == 3 and added.count("break;") == 2


def test_0262_routes_the_response_to_the_waiting_radio():
    in_series("0262")
    added = "\n".join(changed("0262", "+"))
    assert "} else if (msg_type == em_msg_type_topo_resp) {" in added
    assert "waiting->get_state() == em_state_ctrl_topo_sync_pending" in added
    assert not changed("0262", "-")          # the first radio stays the fallback


def test_0264_refuses_while_a_configuration_is_in_flight():
    in_series("0264")
    added = "\n".join(changed("0264", "+"))
    for check in ("m_orch->is_cmd_type_in_progress(evt) == true", "m_orch->is_cmd_type_active(em_cmd_type_em_config)",
                  "m_orch->is_cmd_type_active(em_cmd_type_cfg_renew)"):
        assert check in added
    assert "bool em_orch_t::is_cmd_type_active(em_cmd_type_t type)" in added
    assert "return hash_map_get(m_cmd_map, key) != NULL;" in added


def test_0263_main_answers_with_the_status():
    added = "\n".join(changed("0263", "+"))
    assert "status, err := applyNetworkNameConfig(ssidTree)" in added
    assert "code, reply := setSSIDReply(status, err)" in added
    assert 'return getTreeValue(result, "Status"), nil' in added
    assert any("Profile updated successfully" in line for line in changed("0263", "-"))


@pytest.mark.skipif(shutil.which("go") is None, reason="Go toolchain required")
def test_0263_reply_maps_each_status(tmp_path):
    for name in ("set_ssid_status.go", "set_ssid_status_test.go"):
        (tmp_path / name).write_text((PATCHES / name).read_text())
    (tmp_path / "stubs.go").write_text("package main\n\nfunc main() {}\n")
    environment = dict(os.environ, GO111MODULE="off", GOWORK="off", GOCACHE=str(tmp_path / "cache"))
    result = subprocess.run(["go", "test", "-count=1", "."], cwd=tmp_path, env=environment,
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_helper_carries_0263():
    import hashlib
    import tarfile
    with tarfile.open(PATCHES / "em-cli.tar.gz") as archive:
        sources = archive.extractfile("./em-cli-sources.sha256").read().decode()
    digest = hashlib.sha256((PATCHES / "set_ssid_status.go").read_bytes()).hexdigest()
    assert f"{digest}  ./set_ssid_status.go" in sources
    assert re.search(r"\./main\.go", sources)
