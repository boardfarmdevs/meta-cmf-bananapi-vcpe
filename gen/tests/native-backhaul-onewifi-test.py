"""Compile actual OneWifi backhaul scan/FSM functions against isolated fake HAL/timers."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import tempfile


CASES = (
    "null-inputs", "wrong-radio", "wrong-state-connected", "wrong-state-connecting",
    "wrong-state-disconnecting", "zero-rows", "null-rows", "missing-target",
    "target-wrong-channel", "invalid-band", "allocation-failure", "mixed-channels", "target-only-snapshot",
    "all-wrong-channel", "requested-target", "untargeted-csa", "snapshot-owned",
    "scan-wrong-state", "scan-invalid-radio", "scan-submission-failure", "scan-success",
    "connect-sync-failure", "connect-sync-nonzero", "connect-sync-existing-timer",
    "connect-sync-failure-bounded", "connect-success",
)

FUNCTIONS = (
    "ext_set_conn_state", "schedule_connect_sm", "process_ext_connect_event_timeout",
    "process_connected_scan_result_timeout", "ext_connected_scan",
    "process_ext_connected_scan_results", "ext_try_connecting",
)

STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define RETURN_OK 0
#define RETURN_ERR -1
#define TRUE 1
#define FALSE 0
#define WIFI_RADIO_SCAN_MODE_OFFCHAN 1
#define wifi_util_info_print(...) ((void)0)
#define wifi_util_error_print(...) ((void)0)
#define wifi_util_dbg_print(...) ((void)0)
#define wifi_event_type_command 1
#define wifi_event_type_sta_connect_in_progress 2
#define WIFI_CTRL 0
typedef unsigned char mac_addr_t[6];
typedef unsigned char bssid_t[6];
typedef char mac_addr_str_t[18];
typedef unsigned int wifi_freq_bands_t;
typedef unsigned int wifi_vap_index_t;
typedef struct { int unused; } wifi_platform_property_t;
typedef struct {
    unsigned char bssid[6];
    char ssid[64];
    unsigned int freq;
    int rssi;
} wifi_bss_info_t;
typedef enum {
    connection_attempt_wait, connection_attempt_in_progress, connection_attempt_failed
} connection_attempt_t;
typedef enum {
    connection_state_disconnected_scan_list_none,
    connection_state_disconnected_scan_list_in_progress,
    connection_state_disconnected_scan_list_all,
    connection_state_disconnected_steady,
    connection_state_connection_in_progress,
    connection_state_connection_to_lcb_in_progress,
    connection_state_connection_to_nb_in_progress,
    connection_state_connected,
    connection_state_connected_wait_for_csa,
    connection_state_connected_scan_list,
    connection_state_disconnection_in_progress
} connection_state_t;
typedef struct {
    wifi_bss_info_t external_ap;
    wifi_freq_bands_t radio_freq_band;
    connection_attempt_t conn_attempt;
    unsigned int conn_retry_attempt;
    wifi_vap_index_t vap_index;
} bss_candidate_t;
typedef struct { bss_candidate_t *scan_list; unsigned int scan_count; } bss_candidate_list_t;
typedef struct {
    bss_candidate_list_t candidates_list;
    bss_candidate_t new_bss;
    bss_candidate_t last_connected_bss;
    connection_state_t conn_state;
    unsigned int connected_vap_index;
    unsigned int go_to_channel;
    unsigned int conn_retry;
    unsigned int new_bss_scan_retry;
    int ext_connect_algo_processor_id;
    int ext_conn_status_ind_timeout_handler_id;
    int ext_connected_scan_result_timeout_handler_id;
    int ext_scan_result_timeout_handler_id;
    int ext_scan_result_wait_timeout_handler_id;
} vap_svc_ext_t;
typedef struct {
    void *sched;
    int apps_mgr;
    bool rf_status_down;
    bool multiap_sta_enabled;
} wifi_ctrl_t;
typedef struct vap_svc {
    wifi_ctrl_t *ctrl;
    wifi_platform_property_t *prop;
    union { vap_svc_ext_t ext; } u;
} vap_svc_t;
typedef struct { unsigned int radio_index; unsigned int num; wifi_bss_info_t *bss; } scan_results_t;
typedef struct { int identity; int interval; int (*callback)(vap_svc_t *); bool active; } timer_tester_t;
static timer_tester_t timers[32];
static unsigned int timer_count, canceled_count, scan_calls, connect_calls, analytics_calls;
static int scan_return, connect_return, invalid_band, invalid_radio;
static unsigned int scanned_radio, scanned_channel, connected_vap;
static bool allocation_failure;
static wifi_bss_info_t connected_bss;
static wifi_ctrl_t controller;
static wifi_platform_property_t properties;
static vap_svc_t service;
static wifi_bss_info_t rows[4];
static scan_results_t results;

static void *test_malloc(size_t length)
{
    if (allocation_failure) return NULL;
    void *memory = malloc(length);
    if (memory) memset(memory, 0xa5, length);
    return memory;
}
static void *test_calloc(size_t count, size_t length)
{
    if (allocation_failure) return NULL;
    return calloc(count, length);
}
static int scheduler_cancel_timer_task(void *scheduler, int identity)
{
    (void)scheduler;
    canceled_count++;
    for (unsigned int index = 0; index < timer_count; index++)
        if (timers[index].identity == identity) timers[index].active = false;
    return 0;
}
static int scheduler_add_timer_task(void *scheduler, bool high_priority, int *identity,
    int (*callback)(vap_svc_t *), vap_svc_t *argument, int interval, int repetitions, bool start)
{
    (void)scheduler; (void)high_priority; (void)argument; (void)repetitions; (void)start;
    assert(timer_count < 32);
    *identity = 100 + (int)timer_count;
    timers[timer_count++] = (timer_tester_t){*identity, interval, callback, true};
    return 0;
}
static void cancel_scan_result_timer(wifi_ctrl_t *ctrl, vap_svc_ext_t *ext)
{
    int *identities[] = {&ext->ext_scan_result_timeout_handler_id,
        &ext->ext_scan_result_wait_timeout_handler_id, &ext->ext_connected_scan_result_timeout_handler_id};
    for (unsigned int index = 0; index < 3; index++) {
        if (*identities[index]) scheduler_cancel_timer_task(ctrl->sched, *identities[index]);
        *identities[index] = 0;
    }
}
static int get_radio_index_for_vap_index(wifi_platform_property_t *prop, unsigned int vap)
{
    (void)prop;
    return invalid_radio || vap != 15 ? RETURN_ERR : 1;
}
static int get_sta_vap_index_for_radio(wifi_platform_property_t *prop, unsigned int radio)
{
    (void)prop;
    return radio == 1 ? 15 : RETURN_ERR;
}
static int convert_radio_index_to_freq_band(wifi_platform_property_t *prop, unsigned int radio, int *band)
{
    (void)prop;
    if (invalid_band || radio > 2) return RETURN_ERR;
    *band = radio == 1 ? 2 : 1;
    return RETURN_OK;
}
static int convert_freq_band_to_radio_index(unsigned int band, int *radio)
{
    if (band != 2) return RETURN_ERR;
    *radio = 1;
    return RETURN_OK;
}
static int convert_freq_to_channel(unsigned int frequency, unsigned char *channel)
{
    if (frequency < 5000 || frequency > 5900) return RETURN_ERR;
    *channel = (frequency - 5000) / 5;
    return RETURN_OK;
}
static int get_dwell_time(void) { return 50; }
static bool is_bssid_valid(const bssid_t address)
{
    static const bssid_t empty = {0};
    return memcmp(address, empty, sizeof(empty)) != 0;
}
static int wifi_hal_startScan(unsigned int radio, int mode, int dwell, int count, unsigned int *channels)
{
    assert(mode == WIFI_RADIO_SCAN_MODE_OFFCHAN && dwell == 50 && count == 1);
    scan_calls++;
    scanned_radio = radio;
    scanned_channel = *channels;
    return scan_return;
}
static int wifi_hal_connect(unsigned int vap, wifi_bss_info_t *candidate)
{
    connect_calls++;
    connected_vap = vap;
    connected_bss = *candidate;
    return connect_return;
}
static void reset_sta_state(vap_svc_t *svc, unsigned int vap) { (void)svc; assert(vap == 15); }
static void hotspot_timing_target_detected(void) {}
static char *to_mac_str(const unsigned char *address, char *output)
{
    snprintf(output, 18, "%02x:%02x:%02x:%02x:%02x:%02x", address[0], address[1],
        address[2], address[3], address[4], address[5]);
    return output;
}
static void apps_mgr_analytics_event(int *manager, int type, int subtype, void *candidate)
{
    (void)manager; (void)type; (void)subtype; (void)candidate;
    analytics_calls++;
}
int process_ext_connect_algorithm(vap_svc_t *svc);
#define malloc test_malloc
#define calloc test_calloc
"""

CHECKS = r"""
#undef malloc
#undef calloc
int process_ext_connect_algorithm(vap_svc_t *svc)
{
    svc->u.ext.ext_connect_algo_processor_id = 0;
    if (svc->u.ext.conn_state == connection_state_connection_in_progress ||
        svc->u.ext.conn_state == connection_state_connection_to_nb_in_progress ||
        svc->u.ext.conn_state == connection_state_connection_to_lcb_in_progress)
        ext_try_connecting(svc);
    return 0;
}
static void initialize(void)
{
    memset(&service, 0, sizeof(service));
    memset(&controller, 0, sizeof(controller));
    memset(rows, 0, sizeof(rows));
    service.ctrl = &controller;
    service.prop = &properties;
    controller.multiap_sta_enabled = true;
    service.u.ext.conn_state = connection_state_connected_scan_list;
    service.u.ext.connected_vap_index = 15;
    service.u.ext.go_to_channel = 36;
    service.u.ext.ext_connected_scan_result_timeout_handler_id = 42;
    for (unsigned int index = 0; index < 4; index++) {
        rows[index].bssid[0] = 2;
        rows[index].bssid[5] = 10 + index;
        strcpy(rows[index].ssid, "mesh_backhaul");
        rows[index].freq = 5180;
        rows[index].rssi = -65 - (int)index;
    }
    service.u.ext.new_bss.external_ap = rows[0];
    service.u.ext.new_bss.radio_freq_band = 2;
    results = (scan_results_t){1, 1, rows};
}
static unsigned int active_timer(int (*callback)(vap_svc_t *), int interval)
{
    unsigned int count = 0;
    for (unsigned int index = 0; index < timer_count; index++)
        if (timers[index].active && timers[index].callback == callback &&
            timers[index].interval == interval) count++;
    return count;
}
static void preserved_pending(connection_state_t original)
{
    assert(service.u.ext.conn_state == original);
    assert(service.u.ext.ext_connected_scan_result_timeout_handler_id == 42);
    assert(canceled_count == 0 && timer_count == 0);
    assert(service.u.ext.candidates_list.scan_list == NULL);
}
static void remains_connected(void)
{
    assert(service.u.ext.conn_state == connection_state_connected);
    assert(service.u.ext.ext_connected_scan_result_timeout_handler_id == 0);
    assert(connect_calls == 0);
}
static void assert_snapshot(unsigned int count)
{
    assert(service.u.ext.conn_state == connection_state_disconnection_in_progress);
    assert(service.u.ext.ext_connected_scan_result_timeout_handler_id == 0);
    assert(service.u.ext.candidates_list.scan_count == count);
    assert(service.u.ext.candidates_list.scan_list != NULL);
    for (unsigned int index = 0; index < count; index++) {
        bss_candidate_t *candidate = &service.u.ext.candidates_list.scan_list[index];
        assert(candidate->external_ap.freq == 5180);
        assert(candidate->radio_freq_band == 2);
        assert(candidate->conn_attempt == connection_attempt_wait);
        assert(candidate->conn_retry_attempt == 0);
        assert(candidate->vap_index == 0 || candidate->vap_index == 15);
    }
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];
    initialize();
    if (!strcmp(scenario, "null-inputs")) {
        ext_connected_scan(NULL);
        process_ext_connected_scan_results(NULL, &results);
        process_ext_connected_scan_results(&service, NULL);
        preserved_pending(connection_state_connected_scan_list);
    } else if (!strcmp(scenario, "wrong-radio")) {
        results.radio_index = 0;
        process_ext_connected_scan_results(&service, &results);
        preserved_pending(connection_state_connected_scan_list);
    } else if (!strncmp(scenario, "wrong-state-", 12)) {
        connection_state_t original = !strcmp(scenario, "wrong-state-connected") ? connection_state_connected :
            !strcmp(scenario, "wrong-state-connecting") ? connection_state_connection_in_progress :
            connection_state_disconnection_in_progress;
        service.u.ext.conn_state = original;
        process_ext_connected_scan_results(&service, &results);
        preserved_pending(original);
    } else if (!strcmp(scenario, "zero-rows") || !strcmp(scenario, "null-rows")) {
        if (!strcmp(scenario, "zero-rows")) results.num = 0;
        else results.bss = NULL;
        process_ext_connected_scan_results(&service, &results);
        remains_connected();
    } else if (!strcmp(scenario, "missing-target") || !strcmp(scenario, "target-wrong-channel")) {
        results.num = 2;
        if (!strcmp(scenario, "missing-target")) service.u.ext.new_bss.external_ap.bssid[5] = 99;
        else rows[0].freq = 5200;
        process_ext_connected_scan_results(&service, &results);
        remains_connected();
    } else if (!strcmp(scenario, "invalid-band") || !strcmp(scenario, "allocation-failure")) {
        invalid_band = !strcmp(scenario, "invalid-band");
        allocation_failure = !strcmp(scenario, "allocation-failure");
        process_ext_connected_scan_results(&service, &results);
        remains_connected();
    } else if (!strcmp(scenario, "all-wrong-channel")) {
        rows[0].freq = 5200;
        process_ext_connected_scan_results(&service, &results);
        remains_connected();
    } else if (!strcmp(scenario, "mixed-channels")) {
        memset(&service.u.ext.new_bss, 0, sizeof(bss_candidate_t));
        results.num = 4;
        rows[1].freq = 5200;
        rows[3].freq = 5220;
        process_ext_connected_scan_results(&service, &results);
        assert_snapshot(2);
        assert(!memcmp(service.u.ext.candidates_list.scan_list[0].external_ap.bssid, rows[0].bssid, 6));
        assert(!memcmp(service.u.ext.candidates_list.scan_list[1].external_ap.bssid, rows[2].bssid, 6));
    } else if (!strcmp(scenario, "target-only-snapshot")) {
        results.num = 4;
        service.u.ext.new_bss.external_ap = rows[2];
        rows[1].freq = 5200;
        process_ext_connected_scan_results(&service, &results);
        assert_snapshot(1);
        assert(!memcmp(service.u.ext.candidates_list.scan_list[0].external_ap.bssid, rows[2].bssid, 6));
    } else if (!strcmp(scenario, "requested-target") || !strcmp(scenario, "untargeted-csa") ||
        !strcmp(scenario, "snapshot-owned")) {
        if (!strcmp(scenario, "untargeted-csa")) memset(&service.u.ext.new_bss, 0, sizeof(bss_candidate_t));
        wifi_bss_info_t expected = rows[0];
        process_ext_connected_scan_results(&service, &results);
        assert_snapshot(1);
        assert(!memcmp(&rows[0], &expected, sizeof(expected)));
        memset(rows, 0xcc, sizeof(rows));
        assert(!memcmp(&service.u.ext.candidates_list.scan_list[0].external_ap, &expected, sizeof(expected)));
    } else if (!strcmp(scenario, "scan-wrong-state")) {
        service.u.ext.conn_state = connection_state_connected;
        ext_connected_scan(&service);
        assert(scan_calls == 0);
        preserved_pending(connection_state_connected);
    } else if (!strcmp(scenario, "scan-submission-failure") || !strcmp(scenario, "scan-invalid-radio")) {
        scan_return = RETURN_ERR;
        invalid_radio = !strcmp(scenario, "scan-invalid-radio");
        ext_connected_scan(&service);
        assert(scan_calls == (invalid_radio ? 0U : 1U));
        remains_connected();
        assert(!active_timer(process_connected_scan_result_timeout, EXT_SCAN_RESULT_TIMEOUT));
    } else if (!strcmp(scenario, "scan-success")) {
        ext_connected_scan(&service);
        assert(scan_calls == 1 && scanned_radio == 1 && scanned_channel == 36);
        assert(service.u.ext.conn_state == connection_state_connected_scan_list);
        assert(active_timer(process_connected_scan_result_timeout, EXT_SCAN_RESULT_TIMEOUT) == 1);
    } else if (!strncmp(scenario, "connect-", 8)) {
        service.u.ext.conn_state = connection_state_connection_to_nb_in_progress;
        service.u.ext.ext_connected_scan_result_timeout_handler_id = 0;
        connect_return = !strcmp(scenario, "connect-success") ? RETURN_OK : RETURN_ERR;
        if (!strcmp(scenario, "connect-sync-nonzero")) connect_return = 1;
        if (!strcmp(scenario, "connect-sync-existing-timer"))
            scheduler_add_timer_task(controller.sched, false,
                &service.u.ext.ext_conn_status_ind_timeout_handler_id,
                process_ext_connect_event_timeout, &service, EXT_IGNITE_CONN_STATUS_IND_TIMEOUT, 1, false);
        ext_try_connecting(&service);
        assert(connect_calls == 1 && connected_vap == 15);
        assert(!memcmp(connected_bss.bssid, rows[0].bssid, 6));
        if (connect_return == RETURN_OK) {
            assert(active_timer(process_ext_connect_event_timeout, EXT_IGNITE_CONN_STATUS_IND_TIMEOUT) == 1);
            assert(!active_timer(process_ext_connect_algorithm, EXT_CONNECT_ALGO_PROCESSOR_INTERVAL));
            assert(analytics_calls == 1);
        } else {
            assert(!active_timer(process_ext_connect_event_timeout, EXT_IGNITE_CONN_STATUS_IND_TIMEOUT));
            assert(!active_timer(process_ext_connect_event_timeout, EXT_CONN_STATUS_IND_TIMEOUT));
            assert(active_timer(process_ext_connect_algorithm, EXT_CONNECT_ALGO_PROCESSOR_INTERVAL) == 1);
            if (!strcmp(scenario, "connect-sync-existing-timer")) {
                assert(canceled_count == 1);
                assert(service.u.ext.ext_conn_status_ind_timeout_handler_id == 0);
            }
            if (!strcmp(scenario, "connect-sync-failure-bounded")) {
                for (unsigned int round = 0; round < 8; round++) {
                    int selected = -1;
                    for (unsigned int index = 0; index < timer_count; index++)
                        if (timers[index].active) { selected = (int)index; break; }
                    if (selected < 0) break;
                    assert(timers[selected].interval <= EXT_CONNECT_ALGO_PROCESSOR_INTERVAL);
                    timers[selected].active = false;
                    timers[selected].callback(&service);
                }
                assert(connect_calls <= STA_MAX_CONNECT_ATTEMPT);
                assert(service.u.ext.conn_state == connection_state_disconnected_scan_list_none);
            }
        }
    } else {
        fprintf(stderr, "Unknown scenario: %s\n", scenario);
        return 2;
    }
    free(service.u.ext.candidates_list.scan_list);
    printf("PASS %s\n", scenario);
    return 0;
}
"""


def extract_function(source, name):
    match = re.search(r"^(?:static\s+)?(?:void|int)\s+" + re.escape(name) +
                      r"\s*\([^;]*?\)\s*\{.*?^\}", source, re.M | re.S)
    if not match:
        raise ValueError("Production function missing: " + name)
    return match.group()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path, nargs="?", help="OneWifi source root (build-helper compatibility)")
    parser.add_argument("--source-dir", type=Path,
                        help="OneWifi source root, or directory holding vap_svc_mesh_ext.c/vap_svc.h")
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--header-file", type=Path, help="Explicit vap_svc.h for a sparse source copy")
    parser.add_argument("--output", type=Path, help="New JSON report path; never overwritten")
    arguments = parser.parse_args()
    if arguments.output and arguments.output.exists():
        parser.error("--output must not already exist")
    if bool(arguments.source_root) == bool(arguments.source_dir):
        parser.error("Supply exactly one source root, positional or --source-dir")
    root = (arguments.source_dir or arguments.source_root).resolve()
    candidates = [root / "source/core/services", root / "source/vap_svc", root]
    matching = [candidate for candidate in candidates if (candidate / "vap_svc_mesh_ext.c").is_file()]
    if len(matching) != 1:
        parser.error("--source-dir must resolve to exactly one vap_svc_mesh_ext.c")
    root = matching[0]
    source_path = root / "vap_svc_mesh_ext.c"
    header_path = arguments.header_file.resolve() if arguments.header_file else root / "vap_svc.h"
    source = source_path.read_text()
    header = header_path.read_text()
    constants = []
    for name in ("STA_MAX_CONNECT_ATTEMPT", "EXT_CONNECT_ALGO_PROCESSOR_INTERVAL",
                 "EXT_SCAN_RESULT_TIMEOUT", "EXT_CONN_STATUS_IND_TIMEOUT", "EXT_IGNITE_CONN_STATUS_IND_TIMEOUT"):
        match = re.search(r"^#define\s+" + name + r"\s+\d+\s*$", header, re.M)
        if not match:
            raise ValueError("Production constant missing: " + name)
        constants.append(match.group())
    definitions = [extract_function(source, name) for name in FUNCTIONS]
    declarations = "\n".join(definition.split("{", 1)[0].strip() + ";" for definition in definitions)
    program = "\n".join(("\n".join(constants), STUBS, declarations, "\n".join(definitions), CHECKS))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    report = {
        "source": str(source_path), "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "header": str(header_path), "header_sha256": hashlib.sha256(header_path.read_bytes()).hexdigest(),
        "functions": list(FUNCTIONS), "asan": False, "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="native-backhaul-onewifi-") as temporary:
        directory = Path(temporary)
        translation = directory / "test.c"
        binary = directory / "test"
        translation.write_text(program)
        command = [arguments.cc, "-std=gnu11", "-O0", "-g", "-fno-strict-aliasing",
                   "-Werror=implicit-function-declaration", str(translation), "-o", str(binary)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
        report["compile"] = {"returncode": compiled.returncode, "stderr": compiled.stderr}
        if compiled.returncode == 0:
            for case in CASES:
                try:
                    result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=3)
                    record = {"case": case, "returncode": result.returncode,
                              "passed": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}
                except subprocess.TimeoutExpired:
                    record = {"case": case, "passed": False, "error": "3-second subprocess timeout"}
                report["cases"].append(record)
                print(("PASS " if record["passed"] else "FAIL ") + case)
        else:
            print(compiled.stderr)
    report["passed"] = compiled.returncode == 0 and len(report["cases"]) == len(CASES) and all(
        case["passed"] for case in report["cases"])
    if arguments.output:
        with arguments.output.open("x") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    print(json.dumps({"passed": report["passed"], "cases": len(report["cases"]),
                      "failures": sum(not case["passed"] for case in report["cases"])}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
