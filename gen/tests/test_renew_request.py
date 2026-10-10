"""A renew request (series 0258, 0259): the CLI's cfg_renew sends a wfa-dataelements:Renew subdoc
with a bus event type of its own, which the controller decodes into a renew of each radio it
names (agent AL MAC and current operating class), refusing a bad request as a whole; em_cli's
POST /api/v1/renew builds that subdoc and answers with the controller's status.

Before, the subdoc went out with the type of the controller's own raw renew (a radio MAC), and
the controller read the subdoc's name as that MAC ("Radio: 43:66:67:52:65:6e", "CfgRen"). The
raw renew is now taken only at its own size, and the orchestrator's renew of a cancelled radio
sets that size.

The MAC check is compiled from 0258's own lines; em_cli's route is run with go test against its
renew_request_test.go; the rest is read from the patches."""
from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess
import tarfile

import pytest

PATCHES = Path(__file__).resolve().parents[2] / "recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh"
P0258 = "0258-ctrl-a-renew-request-from-the-cli-renews-the-radios-it-names.patch"
P0259 = "0259-cli-a-renew-route.patch"


def added_lines(patch):
    return [line[1:] for line in (PATCHES / patch).read_text().splitlines()
            if line.startswith("+") and not line.startswith("+++")]


def added_function(patch, signature):
    text = "\n".join(added_lines(patch))
    start = text.index(signature)
    return text[start:text.index("\n}\n", start) + 3]


def hunk_of(patch, path):
    """The diff text of one file in a patch."""
    text = (PATCHES / patch).read_text()
    start = text.index(f"+++ b/{path}")
    following = re.search(r"^diff --git", text[start:], re.M)
    return text[start:] if following is None else text[start:start + following.start()]


def test_the_patches_are_in_the_series_after_0257():
    recipe = (PATCHES.parent / "unified-wifi-mesh.bbappend").read_text()
    assert recipe.index("0257-cli-candidate-not-ready-submitted-again") < recipe.index(P0258[:-6]) \
        < recipe.index(P0259[:-6])
    for name in ("renew_request.go", "renew_request_test.go"):
        assert f"file://{name}" in recipe and f'"{name}"' in recipe    # fetched and copied in
    for name in (P0258, P0259):
        subprocess.run(["git", "apply", "--numstat", str(PATCHES / name)], check=True, capture_output=True)


def test_the_request_has_its_own_bus_event_type_added_last():
    # appended just before em_bus_event_type_max: no existing value moves
    assert re.search(r"\n \s*em_bus_event_type_ap_metrics_query,\n(\+.*\n)*\+\s*em_bus_event_type_cfg_renew_subdoc,\n"
                     r"(\+.*\n)* \n \s*em_bus_event_type_max", hunk_of(P0258, "inc/em_base.h"))
    for cli in ("src/rdkb-cli/em_cmd_cli.cpp", "src/cli/em_cmd_cli.cpp"):
        hunk = hunk_of(P0258, cli)
        assert "+            bevt->type = em_bus_event_type_cfg_renew_subdoc;" in hunk
        assert "-            bevt->type = em_bus_event_type_cfg_renew;" in hunk
        assert 'get_edited_node(node, "Renew", info->buff)' in hunk     # the caller's tree first


def test_the_raw_renew_is_taken_only_at_its_own_size():
    controller = hunk_of(P0258, "src/ctrl/dm_easy_mesh_ctrl.cpp")
    assert "+    if (evt->data_len != sizeof(em_bus_event_type_cfg_renew_params_t)) {" in controller
    cancel = hunk_of(P0258, "src/orch/em_orch_ctrl.cpp")
    assert "+            bev->data_len = sizeof(em_bus_event_type_cfg_renew_params_t);" in cancel
    # the cancelled radio's renew is only completed: its type and radio stay as they were
    assert not [line for line in cancel.splitlines() if line.startswith("-") and not line.startswith("---")]
    # the start's null-MAC renew of every radio (em_ctrl.cpp, ac_config_raw) is not touched
    changed = [line for line in (PATCHES / P0258).read_text().splitlines()
               if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    assert not [line for line in changed if "ac_config_raw" in line]


def test_the_request_is_checked_as_a_whole_before_any_renew():
    analyze = added_function(P0258, "int dm_easy_mesh_ctrl_t::analyze_config_renew_subdoc(")
    refused = analyze.index("    if (refused == true) {\n        return -1;\n    }")
    assert analyze.index("pcmd[num++] = new em_cmd_cfg_renew_t") > refused
    for reason in ("not JSON", "no wfa-dataelements:Renew with a DeviceList", "without an AL MAC ID",
                   "not known", "without a RadioList", "without one current Class", "radio on current class",
                   "more than %d radios"):
        assert reason in analyze
    handler = added_function(P0258, "void em_ctrl_t::handle_config_renew_subdoc(")
    # is_cmd_type_in_progress() reads a renew event as a raw radio
    assert "m_orch->is_cmd_type_in_progress(" not in handler
    assert handler.count("m_ctrl_cmd->send_result(") == 3


@pytest.mark.skipif(shutil.which("g++") is None, reason="C++ compiler required")
def test_the_mac_check_takes_only_a_mac(tmp_path):
    check = added_function(P0258, "static bool renew_request_mac(")
    (tmp_path / "check.cpp").write_text('''#include <ctype.h>
#include <stdio.h>
#include <string.h>
typedef unsigned char mac_address_t[6];
struct cJSON { const char *valuestring; int is_string; };
static bool cJSON_IsString(const cJSON *item) { return item != NULL && item->is_string; }
''' + check + '''
int main(int argc, char **argv)
{
    for (int i = 1; i < argc; i++) {
        cJSON item = {argv[i], 1};
        mac_address_t mac;
        printf("%s %d\\n", argv[i], renew_request_mac(&item, mac) ? 1 : 0);
    }
    cJSON number = {NULL, 0};
    mac_address_t mac;
    printf("number %d\\n", renew_request_mac(&number, mac) ? 1 : 0);
    return 0;
}
''')
    subprocess.run(["g++", "-Wall", "-Werror", "-o", str(tmp_path / "check"), str(tmp_path / "check.cpp")], check=True)
    cases = {"00:60:2f:da:68:e4": 1, "00:60:2F:DA:68:E4": 1, "00:00:00:00:00:00": 0, "CfgRenew.json": 0,
             "00:60:2f:da:68": 0, "00:60:2f:da:68:e4:00": 0, "00-60-2f-da-68-e4": 0, "0g:60:2f:da:68:e4": 0}
    out = subprocess.run([str(tmp_path / "check"), *cases], check=True, capture_output=True, text=True).stdout
    got = dict(line.rsplit(" ", 1) for line in out.splitlines())
    assert {k: int(v) for k, v in got.items()} == {**cases, "number": 0}


@pytest.mark.skipif(shutil.which("go") is None, reason="Go toolchain required")
def test_the_route_answers_with_the_controllers_status(tmp_path):
    for name in ("renew_request.go", "renew_request_test.go"):
        (tmp_path / name).write_text((PATCHES / name).read_text())
    (tmp_path / "stubs.go").write_text('package main\n\nfunc submitRenewSubdoc(subdoc []byte) (string, error) '
                                       '{ return "", nil }\n\nfunc main() {}\n')
    environment = dict(os.environ, GO111MODULE="off", GOWORK="off", GOCACHE=str(tmp_path / "cache"))
    result = subprocess.run(["go", "test", "-count=1", "."], cwd=tmp_path, env=environment,
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_route_submits_through_libemcli():
    main = "\n".join(added_lines(P0259))
    assert 'api.HandleFunc("/renew", renewHandler).Methods("POST")' in main
    submit = added_function(P0259, "func submitRenewSubdoc(")
    assert 'C.CString("cfg_renew OneWifiMesh")' in submit and 'getTreeValue(result, "Status")' in submit


def test_the_helper_is_rebuilt_with_the_route():
    with tarfile.open(PATCHES / "em-cli.tar.gz") as archive:
        sources = archive.extractfile("./em-cli-sources.sha256").read().decode()
        helper = archive.extractfile("./onewifi_em_cli").read()
    digest = hashlib.sha256((PATCHES / "renew_request.go").read_bytes()).hexdigest()
    assert f"{digest}  ./renew_request.go" in sources
    assert b"/renew" in helper and b"cfg_renew OneWifiMesh" in helper
