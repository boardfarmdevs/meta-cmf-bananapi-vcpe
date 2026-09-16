"""Compile production OneWifi client-collector configuration without HAL or runtime access."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import tempfile


FUNCTIONS = (
    "em_common_config_to_monitor_queue", "em_route", "generate_vap_mask_for_radio_index",
    "client_diag_config_to_monitor_queue", "ap_metrics_collector_config",
    "ap_metrics_config_to_monitor_queue", "push_em_config_event_to_monitor_queue",
    "handle_em_webconfig_event",
)

CASES = (
    "common-order", "common-zero", "common-negative", "common-too-many",
    "common-null-config", "common-null-data", "unknown-radio", "unavailable-radio",
    "zero-ruid", "multicast-ruid", "duplicate-radio", "alias-radio", "atomic-validation",
    "ap-explicit-policy", "link-explicit-policy", "all-start-flags", "stop-state",
    "ap-interval-zero", "ap-interval-one", "ap-interval-five", "ap-interval-large",
    "ap-zero-radios", "link-zero-radios", "allocation-failure", "null-app",
    "null-config", "null-manager", "invalid-policy", "negative-count", "excess-count",
    "queue-survey-failure", "queue-vap-failure", "queue-client-failure",
    "queue-link-failure", "report-config-failure", "mask-failure",
    "vap-count-overflow", "mask-count-overflow", "mask-bit-overflow", "mask-high-bit",
    "event-ap-failure", "event-link-failure", "event-stop-failure", "event-null-app",
    "event-unknown-radio",
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
#define MAX_NUM_RADIOS 3
#define EM_MAX_RADIO_POLICY 4
#define MAX_NUM_VAP_PER_RADIO 4
#define wifi_util_error_print(...) ((void)0)
#define wifi_util_dbg_print(...) ((void)0)
#define wifi_util_info_print(...) ((void)0)
#define wifi_app_inst_easymesh 64
#define wifi_sub_component_mon 2
#define wifi_event_monitor_data_collection_config 3
#define WIFI_RADIO_SCAN_MODE_NONE 0
#define webconfig_subdoc_type_em_config 9
#define mon_stats_type_associated_device_stats 5
#define mon_stats_type_radio_channel_stats 1
#define mon_stats_type_vap_stats 7
typedef unsigned char mac_addr_t[6];
typedef enum { mon_stats_request_state_stop, mon_stats_request_state_start } wifi_mon_stats_request_state_t;
typedef enum {
    em_app_event_type_assoc_stats_rcpi_monitor = 10,
    em_app_event_type_assoc_dev_stats_periodic,
    em_app_event_type_ap_metrics_rad_chan_stats,
    em_app_event_type_vap_stats_periodic
} em_app_event_type_t;
typedef enum {
    em_ap_metrics_none, em_ap_metrics_only, em_ap_metrics_link,
    em_ap_metrics_traffic, em_ap_metrics_link_and_traffic,
    em_policy_req_type_link_metrics, em_policy_req_type_ap_metrics
} em_policy_req_type_t;
typedef struct {
    mac_addr_t ruid;
    int sta_rcpi_threshold, sta_rcpi_hysteresis, ap_util_threshold;
    bool traffic_stats, link_metrics, sta_status;
} radio_metrics_policy_t;
typedef struct {
    int radio_count;
    radio_metrics_policy_t radio_metrics_policy[EM_MAX_RADIO_POLICY];
} radio_metrics_policies_t;
typedef struct {
    struct { unsigned char interval; } ap_metric_policy;
    radio_metrics_policies_t radio_metrics_policies;
} em_config_t;
typedef struct {
    struct { union { struct { em_config_t em_config; } em_data; } u; } data;
} wifi_app_t;
typedef struct {
    unsigned int radio_index, vap_index, app_info, scan_mode;
} wifi_mon_stats_args_t;
typedef struct {
    unsigned int inst, data_type, interval_ms;
    wifi_mon_stats_args_t args;
    wifi_mon_stats_request_state_t req_state;
    bool start_immediately;
} wifi_mon_stats_config_t;
typedef struct { union { wifi_mon_stats_config_t mon_stats_config; } u; } wifi_monitor_data_t;
typedef struct { unsigned int vap_index; } rdk_wifi_vap_info_t;
typedef struct {
    unsigned int num_vaps;
    rdk_wifi_vap_info_t rdk_vap_array[MAX_NUM_VAP_PER_RADIO];
} rdk_wifi_vap_map_t;
typedef struct { struct { rdk_wifi_vap_map_t vaps; } radio_config[MAX_NUM_RADIOS]; } wifi_mgr_t;
typedef struct { int dst; union { int inst_bit_map; } u; } wifi_event_route_t;
typedef struct { int type; union { struct { em_config_t em_config; } decoded; } u; } webconfig_subdoc_data_t;
typedef struct { union { webconfig_subdoc_data_t *webconfig_data; } u; } wifi_event_t;
static struct { unsigned int req_stats_vap_mask; } client_assoc_stats[MAX_NUM_RADIOS];
static unsigned int em_util_thresholds[MAX_NUM_RADIOS];
static wifi_mgr_t manager;
static wifi_app_t application;
static em_config_t configuration;
static wifi_monitor_data_t queued[64];
static unsigned int queue_count, queue_calls, report_calls, allocation_calls, frees;
static int fail_queue_type, fail_report, missing_mask_radio = -1;
static bool missing_manager, fail_allocation;
static unsigned int available_radios = MAX_NUM_RADIOS;
static unsigned int reported_vap_count[MAX_NUM_RADIOS];
static int policy_radio(unsigned int index) { return index == 0 ? 2 : index == 1 ? 0 : 1; }
static wifi_mgr_t *get_wifimgr_obj(void) { return missing_manager ? NULL : &manager; }
static unsigned int getNumberRadios(void) { return available_radios; }
static unsigned int getNumberVAPsPerRadio(unsigned int index)
{
    assert(index < MAX_NUM_RADIOS);
    return reported_vap_count[index];
}
static int em_get_radio_index_from_mac(unsigned char *mac)
{
    if (mac[0] != 2 || mac[5] < 1 || mac[5] > MAX_NUM_RADIOS) return RETURN_ERR;
    return mac[5] - 1;
}
static rdk_wifi_vap_map_t *getRdkWifiVap(unsigned int radio)
{
    assert(radio < MAX_NUM_RADIOS);
    return (int)radio == missing_mask_radio ? NULL : &manager.radio_config[radio].vaps;
}
static bool isVapSTAMesh(unsigned int vap) { return vap == 2 || vap == 10 || vap == 18; }
static int push_event_to_monitor_queue(wifi_monitor_data_t *data, int subtype, wifi_event_route_t *route)
{
    assert(data && route && subtype == wifi_event_monitor_data_collection_config);
    assert(route->dst == wifi_sub_component_mon && route->u.inst_bit_map == wifi_app_inst_easymesh);
    queue_calls++;
    if ((int)data->u.mon_stats_config.data_type == fail_queue_type) return RETURN_ERR;
    assert(queue_count < 64);
    queued[queue_count++] = *data;
    return RETURN_OK;
}
static int em_ap_report_config_task(wifi_app_t *app, em_config_t *config,
    wifi_mon_stats_request_state_t state, int interval, em_policy_req_type_t policy)
{
    (void)state; (void)interval; (void)policy;
    assert(app && config);
    report_calls++;
    return fail_report ? 7 : RETURN_OK;
}
static void *fixture_malloc(size_t size)
{
    allocation_calls++;
    return fail_allocation ? NULL : malloc(size);
}
static void fixture_free(void *allocation)
{
    if (allocation) frees++;
    free(allocation);
}
#define malloc fixture_malloc
#define free fixture_free
"""

CHECKS = r"""
static void initialize(void)
{
    configuration.radio_metrics_policies.radio_count = 3;
    configuration.ap_metric_policy.interval = 2;
    application.data.u.em_data.em_config.radio_metrics_policies.radio_count = 0;
    application.data.u.em_data.em_config.ap_metric_policy.interval = 4;
    for (unsigned int index = 0; index < MAX_NUM_RADIOS; ++index) {
        unsigned int radio = policy_radio(index);
        radio_metrics_policy_t *policy = &configuration.radio_metrics_policies.radio_metrics_policy[index];
        policy->ruid[0] = 2;
        policy->ruid[5] = radio + 1;
        policy->link_metrics = true;
        reported_vap_count[index] = 3;
        manager.radio_config[index].vaps.num_vaps = 3;
        for (unsigned int vap_offset = 0; vap_offset < 3; ++vap_offset)
            manager.radio_config[index].vaps.rdk_vap_array[vap_offset].vap_index = index * 8 + vap_offset;
    }
}
static int run_policy(bool ap, wifi_mon_stats_request_state_t state)
{
    wifi_app_t original = application;
    em_config_t original_config = configuration;
    int result = push_em_config_event_to_monitor_queue(&application, state,
        ap ? em_policy_req_type_ap_metrics : em_policy_req_type_link_metrics, &configuration);
    assert(memcmp(&application, &original, sizeof(application)) == 0);
    assert(memcmp(&configuration, &original_config, sizeof(configuration)) == 0);
    assert(fail_allocation || allocation_calls == frees);
    return result;
}
static void check_clients(unsigned int interval, wifi_mon_stats_request_state_t state)
{
    unsigned int clients = 0;
    unsigned int counts[MAX_NUM_RADIOS] = {0};
    for (unsigned int index = 0; index < queue_count; ++index) {
        wifi_mon_stats_config_t *request = &queued[index].u.mon_stats_config;
        assert(request->inst == wifi_app_inst_easymesh);
        assert(request->start_immediately);
        assert(request->req_state == state);
        if (request->data_type != mon_stats_type_associated_device_stats) continue;
        assert(request->args.radio_index < MAX_NUM_RADIOS);
        assert(request->args.vap_index / 8 == request->args.radio_index);
        assert(!isVapSTAMesh(request->args.vap_index));
        assert(request->interval_ms == interval);
        counts[request->args.radio_index]++;
        clients++;
    }
    assert(clients == 6);
    for (unsigned int index = 0; index < MAX_NUM_RADIOS; ++index) assert(counts[index] == 2);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];
    initialize();
    wifi_monitor_data_t data[MAX_NUM_RADIOS];
    memset(data, 0xa5, sizeof(data));
    if (!strcmp(scenario, "common-order")) {
        assert(em_common_config_to_monitor_queue(data, &configuration) == RETURN_OK);
        for (unsigned int index = 0; index < MAX_NUM_RADIOS; ++index) {
            assert(data[index].u.mon_stats_config.args.radio_index == (unsigned int)policy_radio(index));
            assert(data[index].u.mon_stats_config.inst == wifi_app_inst_easymesh);
        }
    } else if (!strcmp(scenario, "common-zero")) {
        configuration.radio_metrics_policies.radio_count = 0;
        assert(em_common_config_to_monitor_queue(data, &configuration) == RETURN_OK);
    } else if (!strcmp(scenario, "common-null-config")) {
        assert(em_common_config_to_monitor_queue(data, NULL) == RETURN_ERR);
    } else if (!strcmp(scenario, "common-null-data")) {
        assert(em_common_config_to_monitor_queue(NULL, &configuration) == RETURN_ERR);
    } else if (!strcmp(scenario, "common-negative") || !strcmp(scenario, "common-too-many") ||
        !strcmp(scenario, "unknown-radio") || !strcmp(scenario, "unavailable-radio") ||
        !strcmp(scenario, "zero-ruid") || !strcmp(scenario, "multicast-ruid") ||
        !strcmp(scenario, "duplicate-radio") || !strcmp(scenario, "alias-radio") ||
        !strcmp(scenario, "atomic-validation")) {
        if (!strcmp(scenario, "common-negative")) configuration.radio_metrics_policies.radio_count = -1;
        else if (!strcmp(scenario, "common-too-many")) configuration.radio_metrics_policies.radio_count = 5;
        else if (!strcmp(scenario, "unknown-radio")) configuration.radio_metrics_policies.radio_metrics_policy[0].ruid[5] = 9;
        else if (!strcmp(scenario, "unavailable-radio")) available_radios = 2;
        else if (!strcmp(scenario, "zero-ruid")) memset(configuration.radio_metrics_policies.radio_metrics_policy[0].ruid, 0, 6);
        else if (!strcmp(scenario, "multicast-ruid")) configuration.radio_metrics_policies.radio_metrics_policy[0].ruid[0] = 3;
        else if (!strcmp(scenario, "atomic-validation")) configuration.radio_metrics_policies.radio_metrics_policy[2].ruid[5] = 9;
        else {
            configuration.radio_metrics_policies.radio_metrics_policy[1] = configuration.radio_metrics_policies.radio_metrics_policy[0];
            if (!strcmp(scenario, "alias-radio")) configuration.radio_metrics_policies.radio_metrics_policy[1].ruid[3] = 1;
        }
        wifi_monitor_data_t original[MAX_NUM_RADIOS];
        memcpy(original, data, sizeof(data));
        assert(em_common_config_to_monitor_queue(data, &configuration) == RETURN_ERR);
        assert(memcmp(original, data, sizeof(data)) == 0);
        assert(queue_calls == 0);
    } else if (!strcmp(scenario, "ap-explicit-policy") || !strcmp(scenario, "link-explicit-policy") ||
        !strcmp(scenario, "all-start-flags") || !strcmp(scenario, "stop-state") ||
        !strncmp(scenario, "ap-interval-", 12)) {
        bool ap = strcmp(scenario, "link-explicit-policy") != 0 && strcmp(scenario, "all-start-flags") != 0;
        wifi_mon_stats_request_state_t state = !strcmp(scenario, "stop-state") ? mon_stats_request_state_stop : mon_stats_request_state_start;
        if (!strcmp(scenario, "ap-interval-zero")) configuration.ap_metric_policy.interval = 0;
        if (!strcmp(scenario, "ap-interval-one")) configuration.ap_metric_policy.interval = 1;
        if (!strcmp(scenario, "ap-interval-five")) configuration.ap_metric_policy.interval = 5;
        if (!strcmp(scenario, "ap-interval-large")) configuration.ap_metric_policy.interval = 120;
        assert(run_policy(ap, state) == RETURN_OK);
        unsigned int interval = configuration.ap_metric_policy.interval;
        check_clients(ap ? (interval > 0 && interval < 5 ? interval : 5) * 1000 : EM_DEF_LINK_METRICS_COLLECT_INTERVAL_MSEC, state);
        assert(report_calls == (ap ? 1U : 0U));
    } else if (!strcmp(scenario, "ap-zero-radios") || !strcmp(scenario, "link-zero-radios")) {
        bool ap = !strcmp(scenario, "ap-zero-radios");
        configuration.radio_metrics_policies.radio_count = 0;
        assert(run_policy(ap, mon_stats_request_state_stop) == RETURN_OK);
        assert(queue_count == 0 && report_calls == (ap ? 1U : 0U));
    } else if (!strcmp(scenario, "null-app") || !strcmp(scenario, "null-config") || !strcmp(scenario, "invalid-policy")) {
        assert(push_em_config_event_to_monitor_queue(!strcmp(scenario, "null-app") ? NULL : &application,
            mon_stats_request_state_start, !strcmp(scenario, "invalid-policy") ? 99 : em_policy_req_type_ap_metrics,
            !strcmp(scenario, "null-config") ? NULL : &configuration) == RETURN_ERR);
        assert(queue_calls == 0 && allocation_calls == 0);
    } else if (!strcmp(scenario, "mask-count-overflow") || !strcmp(scenario, "mask-bit-overflow") || !strcmp(scenario, "mask-high-bit")) {
        manager.radio_config[0].vaps.num_vaps = !strcmp(scenario, "mask-count-overflow") ? MAX_NUM_VAP_PER_RADIO + 1 : 1;
        manager.radio_config[0].vaps.rdk_vap_array[0].vap_index = !strcmp(scenario, "mask-high-bit") ? 31 : 32;
        int result = generate_vap_mask_for_radio_index(0);
        assert(result == (!strcmp(scenario, "mask-high-bit") ? RETURN_OK : RETURN_ERR));
        assert(client_assoc_stats[0].req_stats_vap_mask == (!strcmp(scenario, "mask-high-bit") ? 0x80000000U : 0));
    } else if (!strncmp(scenario, "event-", 6)) {
        webconfig_subdoc_data_t document = {.type = webconfig_subdoc_type_em_config};
        document.u.decoded.em_config = configuration;
        document.u.decoded.em_config.radio_metrics_policies.radio_count = 1;
        radio_metrics_policy_t *policy = &document.u.decoded.em_config.radio_metrics_policies.radio_metrics_policy[0];
        policy->link_metrics = false;
        policy->sta_rcpi_threshold = !strcmp(scenario, "event-stop-failure") ? 0 : 80;
        fail_queue_type = !strcmp(scenario, "event-ap-failure") ? mon_stats_type_radio_channel_stats : mon_stats_type_associated_device_stats;
        if (!strcmp(scenario, "event-unknown-radio")) policy->ruid[5] = 99;
        wifi_event_t event = {.u.webconfig_data = &document};
        assert(handle_em_webconfig_event(!strcmp(scenario, "event-null-app") ? NULL : &application, &event) == RETURN_ERR);
    } else {
        bool ap = strcmp(scenario, "queue-link-failure") != 0;
        if (!strcmp(scenario, "allocation-failure")) fail_allocation = true;
        else if (!strcmp(scenario, "null-manager")) missing_manager = true;
        else if (!strcmp(scenario, "negative-count")) configuration.radio_metrics_policies.radio_count = -1;
        else if (!strcmp(scenario, "excess-count")) configuration.radio_metrics_policies.radio_count = 99;
        else if (!strcmp(scenario, "queue-survey-failure")) fail_queue_type = mon_stats_type_radio_channel_stats;
        else if (!strcmp(scenario, "queue-vap-failure")) fail_queue_type = mon_stats_type_vap_stats;
        else if (!strcmp(scenario, "queue-client-failure") || !strcmp(scenario, "queue-link-failure")) fail_queue_type = mon_stats_type_associated_device_stats;
        else if (!strcmp(scenario, "report-config-failure")) fail_report = 1;
        else if (!strcmp(scenario, "mask-failure")) missing_mask_radio = 2;
        else if (!strcmp(scenario, "vap-count-overflow")) reported_vap_count[2] = MAX_NUM_VAP_PER_RADIO + 1;
        else { fprintf(stderr, "Unknown scenario %s\n", scenario); return 2; }
        assert(run_policy(ap, mon_stats_request_state_start) == RETURN_ERR);
    }
    printf("PASS %s\n", scenario);
    return 0;
}
"""


def extract_function(source, name):
    match = re.search(r"^(?:static\s+)?int\s+" + re.escape(name) +
                      r"\s*\([^;]*?\)\s*\{.*?^\}", source, re.M | re.S)
    if not match:
        raise ValueError("Production function missing: " + name)
    return match.group()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path, nargs="?")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--output", type=Path, help="New JSON report; never overwritten")
    arguments = parser.parse_args()
    if bool(arguments.source_root) == bool(arguments.source_dir):
        parser.error("Supply one source root, positional or --source-dir")
    if arguments.output and arguments.output.exists():
        parser.error("Output already exists")
    root = (arguments.source_dir or arguments.source_root).resolve()
    source_path = root / "source/apps/em/wifi_em.c"
    source = source_path.read_text()
    constant = re.search(r"^#define\s+EM_DEF_LINK_METRICS_COLLECT_INTERVAL_MSEC\s+\d+[^\n]*", source, re.M)
    if not constant:
        parser.error("Production interval constant missing")
    definitions = [extract_function(source, name) for name in FUNCTIONS]
    declarations = "\n".join(definition.split("{", 1)[0].strip() + ";" for definition in definitions)
    program = "\n".join((constant.group(), STUBS, declarations, "\n".join(definitions), CHECKS))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    report = {"source": str(source_path), "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
              "functions": list(FUNCTIONS), "asan": False, "cases": []}
    with tempfile.TemporaryDirectory(prefix="onewifi-client-collector-") as temporary:
        directory = Path(temporary)
        translation = directory / "test.c"
        binary = directory / "test"
        translation.write_text(program)
        command = [arguments.cc, "-std=gnu11", "-O0", "-g", "-fno-strict-aliasing",
                   "-Werror=incompatible-pointer-types", "-Werror=implicit-function-declaration",
                   str(translation), "-o", str(binary)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
        report["compile"] = {"returncode": compiled.returncode, "stderr": compiled.stderr}
        if compiled.returncode == 0:
            for case in CASES:
                try:
                    result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=3)
                    record = {"case": case, "passed": result.returncode == 0, "returncode": result.returncode,
                              "stdout": result.stdout, "stderr": result.stderr}
                except subprocess.TimeoutExpired:
                    record = {"case": case, "passed": False, "error": "3-second timeout"}
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
