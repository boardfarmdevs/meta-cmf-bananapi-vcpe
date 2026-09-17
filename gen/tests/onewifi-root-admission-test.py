import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
inputs = {
    "source/core/wifi_ctrl_rbus_handlers.c": ("get_backhaul_root", "set_backhaul_root"),
    "source/core/wifi_ctrl_queue_handlers.c": ("process_backhaul_root_admission",),
}
methods = []
hashes = {}
for relative, names in inputs.items():
    path = args.source / relative
    content = path.read_text()
    hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in names:
        method = re.search(r"static (?:bus_error_t|void) " + name + r"\(.*?\n\}", content, re.S)
        assert method, name
        methods.append(method.group())
program = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int bus_error_t;
typedef int bus_user_data_t;
typedef struct { int data_type; unsigned int raw_data_len; struct { void *bytes; } raw_data; } raw_data_t;
typedef struct { struct { int wifi_prop; } hal_cap; } wifi_mgr_t;
enum { bus_error_success, bus_error_invalid_input, bus_error_invalid_operation,
    bus_error_out_of_resources, bus_data_type_bytes, wifi_event_type_command,
    wifi_event_type_backhaul_root_admit };
#define RETURN_OK 0
#define MAX_NUM_VAP_PER_RADIO 16
#define wifi_util_info_print(...) ((void)0)
#define wifi_util_error_print(...) ((void)0)
static wifi_mgr_t manager;
static int get_error, queue_error, admitted, queued;
static unsigned char request[26], supplied[22];
wifi_mgr_t *get_wifimgr_obj(void) { return &manager; }
unsigned int getNumberRadios(void) { return 2; }
unsigned int get_sta_vap_index_for_radio(int *prop, unsigned int radio) {
    assert(prop == &manager.hal_cap.wifi_prop); return radio * 16 + 3;
}
int wifi_hal_backhaul_root_state(int vap_index, unsigned char *state) {
    assert(vap_index == 19); memcpy(state, supplied, 22); return get_error;
}
int wifi_hal_backhaul_root_admit(int vap_index, const unsigned char *state) {
    assert(vap_index == 19 && memcmp(state, supplied, 22) == 0); ++admitted; return 0;
}
int push_event_to_ctrl_queue(void *data, unsigned int length, int type, int subtype, void *extra) {
    assert(length == 26 && type == wifi_event_type_command &&
        subtype == wifi_event_type_backhaul_root_admit && extra == NULL);
    memcpy(request, data, length); ++queued; return queue_error;
}
METHODS
int main(void) {
    char valid[] = "Device.WiFi.STA.2.X_RDK_BackhaulRoot";
    supplied[7] = 1; supplied[8] = 2; supplied[14] = 2; supplied[20] = 1;
    raw_data_t value = {0};
    assert(get_backhaul_root(valid, &value, NULL) == bus_error_success);
    assert(value.data_type == bus_data_type_bytes && value.raw_data_len == 22 &&
        value.raw_data.bytes != supplied && memcmp(value.raw_data.bytes, supplied, 22) == 0);
    free(value.raw_data.bytes);
    get_error = -1;
    value = (raw_data_t){0};
    assert(get_backhaul_root(valid, &value, NULL) == bus_error_invalid_operation);
    get_error = 0;
    value = (raw_data_t){.data_type = bus_data_type_bytes, .raw_data_len = 22, .raw_data.bytes = supplied};
    assert(set_backhaul_root(valid, &value, NULL) == bus_error_success && queued == 1 && admitted == 0);
    process_backhaul_root_admission(request, sizeof(request));
    assert(admitted == 1);
    const char *invalid[] = {NULL, "", "Device.WiFi.STA.0.X_RDK_BackhaulRoot",
        "Device.WiFi.STA.3.X_RDK_BackhaulRoot", "Device.WiFi.STA.2.Bssid",
        "Device.WiFi.STA.2.X_RDK_BackhaulRoot.extra", "Device.WiFi.STA.-1.X_RDK_BackhaulRoot"};
    for (unsigned int index = 0; index < sizeof(invalid) / sizeof(invalid[0]); ++index) {
        assert(get_backhaul_root((char *)invalid[index], &value, NULL) == bus_error_invalid_input);
        assert(set_backhaul_root((char *)invalid[index], &value, NULL) == bus_error_invalid_input);
    }
    assert(get_backhaul_root(valid, NULL, NULL) == bus_error_invalid_input);
    assert(set_backhaul_root(valid, NULL, NULL) == bus_error_invalid_input);
    for (unsigned int length = 0; length <= 23; ++length) {
        if (length == 22) continue;
        value.raw_data_len = length;
        assert(set_backhaul_root(valid, &value, NULL) == bus_error_invalid_input);
    }
    value.raw_data_len = 22; value.data_type = -1;
    assert(set_backhaul_root(valid, &value, NULL) == bus_error_invalid_input);
    value.data_type = bus_data_type_bytes; value.raw_data.bytes = NULL;
    assert(set_backhaul_root(valid, &value, NULL) == bus_error_invalid_input);
    value.raw_data.bytes = supplied; queue_error = -1;
    assert(set_backhaul_root(valid, &value, NULL) == bus_error_out_of_resources);
    process_backhaul_root_admission(NULL, 26);
    process_backhaul_root_admission(request, 25);
    request[0] = 255;
    process_backhaul_root_admission(request, 26);
    assert(admitted == 1);
    puts("PASS: production root bus getters, owned bytes, strict requests, control-queue serialization and failure propagation");
}
'''.replace("METHODS", "\n\n".join(methods))
with tempfile.TemporaryDirectory(prefix="onewifi-root-admission-") as directory:
    binary = Path(directory) / "test"
    compile_result = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-x", "c", "-",
                                     "-o", str(binary)], input=program, text=True, capture_output=True)
    run = subprocess.run([str(binary)], text=True, capture_output=True) if compile_result.returncode == 0 else None
    result = {"source_sha256": hashes, "compile_exit": compile_result.returncode,
              "compile_stderr": compile_result.stderr, "run_exit": run.returncode if run else None,
              "stdout": run.stdout if run else "", "stderr": run.stderr if run else "",
              "passed": run is not None and run.returncode == 0}
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(result["stdout"] or result["compile_stderr"] or result["stderr"], end="")
    raise SystemExit(0 if result["passed"] else 1)
