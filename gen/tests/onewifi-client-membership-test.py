"""Compile actual OneWifi membership collection/cache/getter against deterministic HAL and clocks."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import tempfile


FUNCTIONS = {
    "wifi_stats_assoc_client.c": (
        "process_assoc_dev_stats", "execute_assoc_client_stats_api", "copy_assoc_client_stats_from_cache",
    ),
    "wifi_monitor.c": ("get_sta_stats_info",),
}
CASES = (
    "event-seeded-empty", "event-seeded-no-frame", "event-seeded-repeated-empty",
    "polled-empty", "vap-isolation", "raw-active-false", "new-hal-row",
    "partial-membership", "hal-error", "hal-error-buffer", "positive-null",
    "newer-connect", "newer-connect-polled", "newer-connect-next-round",
    "frame-only-expired", "frame-only-recent", "frame-only-boundary",
    "frame-only-future", "wall-clock-error", "queue-allocation-error",
    "station-allocation-error", "partial-allocation-error", "pre-hal-clock-error",
    "post-hal-clock-error", "null-collector", "null-monitor", "null-args", "inactive-cache",
    "partial-allocation-recovery", "queue-allocation-recovery",
)

STUBS = r"""
#include <assert.h>
#include <ctype.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#define RETURN_OK 0
#define RETURN_ERR -1
#define STA_KEY_LEN 18
#define MAX_NUM_RADIOS 2
#define MAX_NUM_VAP_PER_RADIO 2
#define wifi_util_error_print(...) ((void)0)
#define wifi_util_info_print(...) ((void)0)
#define wifi_util_dbg_print(...) ((void)0)
#define mon_stats_type_associated_device_stats 3
#define rdk_dev_mode_type_em_node 2
#define rdk_dev_mode_type_em_colocated_node 3
#define wifi_event_type_exec 1
#define wifi_event_type_hal_ind 2
#define wifi_event_type_monitor 3
#define wifi_event_exec_timeout 4
#define wifi_event_exec_stop 5
#define wifi_event_type_collect_stats 6
#define timespecisset(value) ((value)->tv_sec != 0 || (value)->tv_nsec != 0)
#define timespeccmp(left, right, operation) (((left)->tv_sec == (right)->tv_sec) ? ((left)->tv_nsec operation (right)->tv_nsec) : ((left)->tv_sec operation (right)->tv_sec))
#define timespecsub(left, right, result) do { (result)->tv_sec = (left)->tv_sec - (right)->tv_sec; (result)->tv_nsec = (left)->tv_nsec - (right)->tv_nsec; if ((result)->tv_nsec < 0) { (result)->tv_nsec += 1000000000L; --(result)->tv_sec; } } while (0)
#define timespecadd(left, right, result) do { (result)->tv_sec = (left)->tv_sec + (right)->tv_sec; (result)->tv_nsec = (left)->tv_nsec + (right)->tv_nsec; if ((result)->tv_nsec >= 1000000000L) { (result)->tv_nsec -= 1000000000L; ++(result)->tv_sec; } } while (0)
typedef unsigned int UINT;
typedef unsigned char mac_address_t[6];
typedef unsigned char mac_addr_t[6];
typedef char sta_key_t[STA_KEY_LEN];
typedef struct {
    mac_address_t cli_MACAddress, cli_MLDAddr;
    bool cli_Active, cli_AuthenticationState, cli_MLDEnable;
    char cli_OperatingStandard[64], cli_OperatingChannelBandwidth[64], cli_InterferenceSources[64];
    int cli_SignalStrength, cli_RSSI, cli_MinRSSI, cli_MaxRSSI, cli_SNR;
    unsigned long cli_LastDataDownlinkRate, cli_LastDataUplinkRate, cli_Retransmissions;
    unsigned long cli_DataFramesSentAck, cli_DataFramesSentNoAck, cli_BytesSent, cli_BytesReceived;
    unsigned long cli_Disassociations, cli_AuthenticationFailures, cli_Associations;
    unsigned long cli_activeNumSpatialStreams, cli_capableNumSpatialStreams;
    unsigned long cli_PacketsSent, cli_PacketsReceived, cli_ErrorsSent, cli_RetransCount;
    unsigned long cli_FailedRetransCount, cli_RetryCount, cli_MultipleRetryCount;
    unsigned long cli_MaxDownlinkRate, cli_MaxUplinkRate, cli_TxFrames, cli_RxRetries, cli_RxErrors;
} wifi_associated_dev3_t;
typedef struct { time_t frame_timestamp; } assoc_req_elem_t;
typedef struct {
    mac_address_t sta_mac, link_mac;
    wifi_associated_dev3_t dev_stats;
    bool updated, connection_authorized, rapid_disconnect_flag;
    struct timespec timestamp, last_connected_time, last_disconnected_time;
    struct timespec total_connected_time, total_disconnected_time;
    unsigned int good_rssi_time, bad_rssi_time;
    assoc_req_elem_t assoc_frame_data;
} sta_data_t;
typedef struct { int ap_index; wifi_associated_dev3_t dev_stats; mac_address_t link_address; unsigned int last_connect_time; assoc_req_elem_t sta_data; } assoc_dev_data_t;
typedef struct { char *keys[16]; void *values[16]; } hash_map_t;
typedef struct { void *values[16]; unsigned int count; } queue_t;
typedef struct { unsigned int vap_index; } wifi_mon_stats_args_t;
typedef struct { wifi_mon_stats_args_t *args; struct { bool is_event_subscribed; unsigned int stats_type_subscribed; } stats_clctr; } wifi_mon_collector_element_t;
typedef struct { wifi_mon_stats_args_t args; } wifi_mon_stats_config_t;
typedef struct { wifi_mon_stats_config_t *mon_stats_config; } wifi_mon_provider_element_t;
typedef struct { int data_type; wifi_mon_stats_args_t args; void *stat_pointer; unsigned int stat_array_size; } wifi_provider_response_t;
typedef struct { bool enabled; } wifi_front_haul_bss_t;
typedef struct { int unused; } wifi_platform_property_t;
typedef struct { bool link_quality_rfc; } wifi_rfc_dml_parameters_t;
typedef struct { int good_rssi_threshold; } wifi_global_param_t;
typedef struct { int network_mode; bool rf_status_down; int apps_mgr; } wifi_ctrl_t;
typedef struct { unsigned int size; struct { char mac_str[18]; wifi_associated_dev3_t dev; unsigned int vap_index; } stats; } linkquality_data_t;
typedef struct {
    int data_lock;
    bool radio_presence[2];
    int sta_health_rssi_threshold;
    struct { hash_map_t *sta_map; struct timespec last_sta_update_time; struct { unsigned int rapid_reconnect_threshold; } ap_params; } bssid_data[2];
} wifi_monitor_t;
static wifi_monitor_t g_monitor_module;
static wifi_platform_property_t properties;
static wifi_ctrl_t controller;
static wifi_rfc_dml_parameters_t rfc;
static wifi_global_param_t global_parameters;
static wifi_front_haul_bss_t bsses[2];
static wifi_mon_stats_args_t arguments;
static wifi_mon_collector_element_t collector;
static wifi_associated_dev3_t hal_rows[2];
static unsigned int hal_count, hal_calls, disconnects, publications, allocated_stations;
static int hal_return, clock_failure;
static bool positive_null, error_buffer, newer_connect, queue_failure;
static unsigned int fail_station_allocation;
static time_t monotonic_seconds = 6000, wall_seconds = 1789605000;
static bool after_hal;
static const unsigned int subject = 0x49;

static void *fixture_calloc(size_t count, size_t size)
{
    if (count == 1 && size == sizeof(sta_data_t)) {
        allocated_stations++;
        if (fail_station_allocation == allocated_stations) return NULL;
    }
    return calloc(count, size);
}
static hash_map_t *hash_map_create(void) { return calloc(1, sizeof(hash_map_t)); }
static void *hash_map_get(hash_map_t *map, const char *key)
{
    if (!map) return NULL;
    for (unsigned int index = 0; index < 16; ++index)
        if (map->keys[index] && !strcmp(map->keys[index], key)) return map->values[index];
    return NULL;
}
static int hash_map_put(hash_map_t *map, char *key, void *value)
{
    for (unsigned int index = 0; index < 16; ++index) {
        if (!map->keys[index]) { map->keys[index] = key; map->values[index] = value; return 0; }
    }
    assert(false); return -1;
}
static void *hash_map_get_first(hash_map_t *map)
{
    if (!map) return NULL;
    for (unsigned int index = 0; index < 16; ++index) if (map->keys[index]) return map->values[index];
    return NULL;
}
static void *hash_map_get_next(hash_map_t *map, void *value)
{
    bool seen = false;
    for (unsigned int index = 0; index < 16; ++index) {
        if (seen && map->keys[index]) return map->values[index];
        if (map->keys[index] && map->values[index] == value) seen = true;
    }
    return NULL;
}
static unsigned int hash_map_count(hash_map_t *map)
{
    unsigned int count = 0;
    if (map) for (unsigned int index = 0; index < 16; ++index) count += map->keys[index] != NULL;
    return count;
}
static void *hash_map_remove(hash_map_t *map, const char *key)
{
    for (unsigned int index = 0; index < 16; ++index) {
        if (map->keys[index] && !strcmp(map->keys[index], key)) {
            void *value = map->values[index];
            free(map->keys[index]); map->keys[index] = NULL; map->values[index] = NULL; return value;
        }
    }
    return NULL;
}
static char *to_sta_key(unsigned char *mac, char *key)
{
    snprintf(key, STA_KEY_LEN, "%02x:%02x:%02x:%02x:%02x:%02x", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]); return key;
}
static void str_tolower(char *text) { for (; *text; ++text) *text = tolower((unsigned char)*text); }
static int pthread_mutex_lock(int *lock) { assert(*lock == 0); *lock = 1; return 0; }
static int pthread_mutex_unlock(int *lock) { assert(*lock == 1); *lock = 0; return 0; }
static queue_t *queue_create(void) { return queue_failure ? NULL : calloc(1, sizeof(queue_t)); }
static int queue_push(queue_t *queue, void *value) { assert(queue->count < 16); queue->values[queue->count++] = value; return 0; }
static unsigned int queue_count(queue_t *queue) { return queue->count; }
static void *queue_pop(queue_t *queue) { return queue->values[--queue->count]; }
static void queue_destroy(queue_t *queue) { assert(queue->count == 0); free(queue); }
static wifi_platform_property_t *get_wifi_hal_cap_prop(void) { return &properties; }
static wifi_ctrl_t *get_wifictrl_obj(void) { return &controller; }
static wifi_rfc_dml_parameters_t *get_ctrl_rfc_parameters(void) { return &rfc; }
static wifi_global_param_t *get_wifidb_wifi_global_param(void) { return &global_parameters; }
static UINT get_radio_index_for_vap_index(wifi_platform_property_t *prop, unsigned int vap) { (void)prop; return vap < 2 ? vap : (UINT)-1; }
static int getVAPArrayIndexFromVAPIndex(unsigned int vap, unsigned int *index) { assert(vap < 2); *index = vap; return 0; }
static wifi_front_haul_bss_t *Get_wifi_object_bss_parameter(unsigned int vap) { return vap < 2 ? &bsses[vap] : NULL; }
static bool isVapSTAMesh(unsigned int vap) { (void)vap; return false; }
static bool is_zero_mac(unsigned char *mac) { const unsigned char zero[6] = {0}; return memcmp(mac, zero, 6) == 0; }
static void apps_mgr_link_quality_event(void *apps, int type, int event, void *data, unsigned int count)
{ (void)apps; (void)type; (void)event; (void)count; free(data); }
static void events_update_clientdiagdata(unsigned int count, unsigned int vap, wifi_associated_dev3_t *rows)
{ (void)vap; assert(count == 0 || rows != NULL); }
static void send_wifi_disconnect_event_to_ctrl(unsigned char *mac, unsigned int vap)
{ (void)mac; assert(vap == arguments.vap_index && g_monitor_module.data_lock == 0); disconnects++; }
static void push_monitor_response_event_to_ctrl_queue(wifi_provider_response_t *response, size_t size, int type, int subtype, void *route)
{ (void)response; (void)size; (void)type; (void)subtype; (void)route; assert(g_monitor_module.data_lock == 0); publications++; }
static int fixture_clock_gettime(clockid_t clock, struct timespec *value)
{
    assert(clock == CLOCK_MONOTONIC);
    if ((clock_failure == 1 && !after_hal) || (clock_failure == 2 && after_hal)) return -1;
    value->tv_sec = monotonic_seconds; value->tv_nsec = after_hal ? 500000000L : 0; return 0;
}
static time_t fixture_time(time_t *destination)
{ if (destination) *destination = wall_seconds; return wall_seconds; }
static sta_data_t *find_sta(unsigned int vap, unsigned int identity)
{
    mac_address_t mac = {2, 0, 0, 0, identity, 0}; sta_key_t key;
    return hash_map_get(g_monitor_module.bssid_data[vap].sta_map, to_sta_key(mac, key));
}
static sta_data_t *seed(unsigned int vap, unsigned int identity)
{
    sta_data_t *station = calloc(1, sizeof(sta_data_t));
    station->sta_mac[0] = 2; station->sta_mac[4] = identity;
    memcpy(station->dev_stats.cli_MACAddress, station->sta_mac, 6);
    station->dev_stats.cli_Active = true;
    station->connection_authorized = true;
    station->last_connected_time.tv_sec = monotonic_seconds - 100;
    station->assoc_frame_data.frame_timestamp = wall_seconds - 100;
    sta_key_t key;
    hash_map_put(g_monitor_module.bssid_data[vap].sta_map, strdup(to_sta_key(station->sta_mac, key)), station);
    return station;
}
static int wifi_getApAssociatedDeviceDiagnosticResult3(unsigned int vap, wifi_associated_dev3_t **rows, unsigned int *count)
{
    assert(g_monitor_module.data_lock == 0 && vap == arguments.vap_index);
    hal_calls++; after_hal = true;
    if (newer_connect) {
        sta_data_t *station = find_sta(vap, subject);
        station->last_connected_time = (struct timespec){monotonic_seconds, 250000000L};
        station->dev_stats.cli_Active = true;
    }
    *count = hal_count;
    *rows = NULL;
    if ((hal_count && !positive_null) || error_buffer) {
        *rows = calloc(hal_count ? hal_count : 1, sizeof(wifi_associated_dev3_t));
        if (hal_count) memcpy(*rows, hal_rows, hal_count * sizeof(wifi_associated_dev3_t));
    }
    return hal_return;
}
#define calloc fixture_calloc
#define clock_gettime fixture_clock_gettime
#define time fixture_time
"""

CHECKS = r"""
static int collect(void)
{
    after_hal = false;
    int result = execute_assoc_client_stats_api(&collector, &g_monitor_module, 5000);
    assert(g_monitor_module.data_lock == 0);
    return result;
}
static unsigned int cached(unsigned int vap)
{
    wifi_mon_stats_config_t config = {.args.vap_index = vap};
    wifi_mon_provider_element_t provider = {.mon_stats_config = &config};
    void *rows = NULL;
    unsigned int count = 0;
    fail_station_allocation = 0;
    assert(copy_assoc_client_stats_from_cache(&provider, &rows, &count, &g_monitor_module) == RETURN_OK);
    free(rows);
    return count;
}
static void inactive(unsigned int identity)
{
    sta_data_t *station = find_sta(0, identity);
    assert(station == NULL || station->dev_stats.cli_Active == false);
    assoc_dev_data_t entry = {.ap_index = 0};
    entry.dev_stats.cli_MACAddress[0] = 2;
    entry.dev_stats.cli_MACAddress[4] = identity;
    entry.dev_stats.cli_Active = true;
    get_sta_stats_info(&entry);
    assert(entry.dev_stats.cli_Active == false);
}
static void row(unsigned int offset, unsigned int identity)
{
    hal_rows[offset].cli_MACAddress[0] = 2;
    hal_rows[offset].cli_MACAddress[4] = identity;
    hal_rows[offset].cli_AuthenticationState = true;
    hal_rows[offset].cli_Active = false;
    hal_rows[offset].cli_RSSI = -53;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];
    for (unsigned int vap = 0; vap < 2; ++vap) {
        bsses[vap].enabled = true;
        g_monitor_module.radio_presence[vap] = true;
        g_monitor_module.bssid_data[vap].sta_map = hash_map_create();
        g_monitor_module.bssid_data[vap].last_sta_update_time.tv_sec = monotonic_seconds - 10;
        g_monitor_module.bssid_data[vap].ap_params.rapid_reconnect_threshold = 5;
    }
    collector.args = &arguments;
    sta_data_t *station = seed(0, subject);
    if (!strcmp(scenario, "event-seeded-empty") || !strcmp(scenario, "event-seeded-no-frame") ||
        !strcmp(scenario, "event-seeded-repeated-empty") || !strcmp(scenario, "polled-empty") || !strcmp(scenario, "vap-isolation")) {
        if (!strcmp(scenario, "event-seeded-no-frame")) station->assoc_frame_data.frame_timestamp = 0;
        if (!strcmp(scenario, "polled-empty")) { station->total_connected_time.tv_sec = 20; station->last_connected_time.tv_sec = 0; }
        if (!strcmp(scenario, "vap-isolation")) seed(1, subject);
        assert(collect() == RETURN_OK);
        inactive(subject);
        assert(cached(0) == 0);
        if (!strcmp(scenario, "vap-isolation")) assert(cached(1) == 1 && find_sta(1, subject)->dev_stats.cli_Active);
        if (!strcmp(scenario, "event-seeded-repeated-empty")) {
            monotonic_seconds += 10;
            assert(collect() == RETURN_OK);
            assert(find_sta(0, subject) == NULL && disconnects == 1);
            assert(collect() == RETURN_OK && disconnects == 1 && cached(0) == 0);
        }
    } else if (!strcmp(scenario, "raw-active-false") || !strcmp(scenario, "new-hal-row") || !strcmp(scenario, "partial-membership")) {
        unsigned int identity = !strcmp(scenario, "raw-active-false") ? subject : subject + 1;
        hal_count = 1; row(0, identity);
        assert(collect() == RETURN_OK);
        sta_data_t *observed = find_sta(0, identity);
        assert(observed && observed->dev_stats.cli_Active && observed->dev_stats.cli_AuthenticationState);
        assert(observed->dev_stats.cli_RSSI == -53 && observed->timestamp.tv_sec == monotonic_seconds);
        assert(cached(0) == 1);
        if (identity != subject) inactive(subject);
    } else if (!strcmp(scenario, "hal-error") || !strcmp(scenario, "hal-error-buffer") ||
        !strcmp(scenario, "positive-null") || !strcmp(scenario, "queue-allocation-error") ||
        !strcmp(scenario, "station-allocation-error") || !strcmp(scenario, "partial-allocation-error") ||
        !strcmp(scenario, "pre-hal-clock-error") || !strcmp(scenario, "post-hal-clock-error")) {
        station->total_connected_time.tv_sec = 20;
        if (!strncmp(scenario, "hal-error", 9)) { hal_return = RETURN_ERR; error_buffer = !strcmp(scenario, "hal-error-buffer"); }
        if (!strcmp(scenario, "positive-null")) { positive_null = true; hal_count = 1; }
        if (!strcmp(scenario, "queue-allocation-error")) queue_failure = true;
        if (!strcmp(scenario, "station-allocation-error")) { hal_count = 1; row(0, subject + 1); fail_station_allocation = 1; }
        if (!strcmp(scenario, "partial-allocation-error")) { hal_count = 2; row(0, subject + 1); row(1, subject + 2); fail_station_allocation = 2; }
        if (!strcmp(scenario, "pre-hal-clock-error")) clock_failure = 1;
        if (!strcmp(scenario, "post-hal-clock-error")) clock_failure = 2;
        assert(collect() == RETURN_ERR);
        assert(station->dev_stats.cli_Active && disconnects == 0 && publications == 0);
        if (clock_failure == 1) assert(hal_calls == 0);
    } else if (!strcmp(scenario, "partial-allocation-recovery") || !strcmp(scenario, "queue-allocation-recovery")) {
        hal_count = 2; row(0, subject); row(1, subject + 1);
        if (!strcmp(scenario, "partial-allocation-recovery")) fail_station_allocation = 1;
        else queue_failure = true;
        assert(collect() == RETURN_ERR && station->dev_stats.cli_Active);
        fail_station_allocation = 0;
        queue_failure = false;
        hal_count = 0;
        monotonic_seconds += 10;
        assert(collect() == RETURN_OK);
        inactive(subject);
        assert(cached(0) == 0);
    } else if (!strcmp(scenario, "newer-connect") || !strcmp(scenario, "newer-connect-polled") ||
        !strcmp(scenario, "newer-connect-next-round")) {
        if (strcmp(scenario, "newer-connect")) station->total_connected_time.tv_sec = 20;
        newer_connect = true;
        assert(collect() == RETURN_OK && station->dev_stats.cli_Active && cached(0) == 1);
        assert(disconnects == 0);
        if (!strcmp(scenario, "newer-connect-next-round")) {
            newer_connect = false;
            monotonic_seconds += 10;
            assert(collect() == RETURN_OK);
            inactive(subject);
            assert(cached(0) == 0);
        }
    } else if (!strncmp(scenario, "frame-only-", 11) || !strcmp(scenario, "wall-clock-error")) {
        station->last_connected_time = (struct timespec){0};
        station->connection_authorized = false;
        station->dev_stats.cli_Active = false;
        if (!strcmp(scenario, "frame-only-expired")) station->assoc_frame_data.frame_timestamp = wall_seconds - 6;
        if (!strcmp(scenario, "frame-only-recent")) station->assoc_frame_data.frame_timestamp = wall_seconds - 1;
        if (!strcmp(scenario, "frame-only-boundary")) station->assoc_frame_data.frame_timestamp = wall_seconds - 5;
        if (!strcmp(scenario, "frame-only-future")) station->assoc_frame_data.frame_timestamp = wall_seconds + 60;
        if (!strcmp(scenario, "wall-clock-error")) wall_seconds = (time_t)-1;
        assert(collect() == RETURN_OK);
        assert((find_sta(0, subject) == NULL) == !strcmp(scenario, "frame-only-expired"));
        assert(disconnects == 0 && cached(0) == 0);
    } else if (!strcmp(scenario, "null-collector")) {
        assert(execute_assoc_client_stats_api(NULL, &g_monitor_module, 5000) == RETURN_ERR && hal_calls == 0);
    } else if (!strcmp(scenario, "null-monitor")) {
        assert(execute_assoc_client_stats_api(&collector, NULL, 5000) == RETURN_ERR && hal_calls == 0);
    } else if (!strcmp(scenario, "null-args")) {
        collector.args = NULL;
        assert(collect() == RETURN_ERR && hal_calls == 0);
    } else if (!strcmp(scenario, "inactive-cache")) {
        station->dev_stats.cli_Active = false;
        assert(cached(0) == 0);
        inactive(subject);
    } else { fprintf(stderr, "Unknown case %s\n", scenario); return 2; }
    assert(g_monitor_module.data_lock == 0);
    printf("PASS %s\n", scenario);
    return 0;
}
"""


def extract_function(source, name):
    match = re.search(r"^int\s+" + re.escape(name) + r"\s*\([^;]*?\)\s*\{.*?^\}", source, re.M | re.S)
    if not match:
        raise ValueError("Production function missing: " + name)
    return match.group()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path, nargs="?")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--output", type=Path, help="Exclusive-create JSON report")
    arguments = parser.parse_args()
    if bool(arguments.source_root) == bool(arguments.source_dir):
        parser.error("Supply exactly one source root")
    if arguments.output and arguments.output.exists():
        parser.error("Output already exists")
    root = (arguments.source_dir or arguments.source_root).resolve() / "source/stats"
    definitions = []
    sources = []
    for filename, functions in FUNCTIONS.items():
        path = root / filename
        content = path.read_text()
        definitions.extend(extract_function(content, name) for name in functions)
        sources.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "functions": list(functions)})
    declarations = "\n".join(definition.split("{", 1)[0].strip() + ";" for definition in definitions)
    program = "\n".join((STUBS, declarations, "\n".join(definitions), CHECKS))
    cases = [arguments.case] if arguments.case else CASES
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    report = {"source": str(root.parent.parent), "sources": sources, "asan": False, "cases": []}
    with tempfile.TemporaryDirectory(prefix="onewifi-client-membership-") as temporary:
        directory = Path(temporary)
        translation = directory / "test.c"
        executable = directory / "test"
        translation.write_text(program)
        compiled = subprocess.run([arguments.cc, "-std=gnu11", "-O0", "-g", "-fno-strict-aliasing",
                                   "-Werror=implicit-function-declaration", "-Werror=incompatible-pointer-types",
                                   str(translation), "-o", str(executable)], capture_output=True, text=True, timeout=30)
        report["compile"] = {"returncode": compiled.returncode, "stderr": compiled.stderr}
        if compiled.returncode == 0:
            for case in cases:
                try:
                    result = subprocess.run([str(executable), case], capture_output=True, text=True, timeout=3)
                    record = {"case": case, "passed": result.returncode == 0, "returncode": result.returncode,
                              "stdout": result.stdout, "stderr": result.stderr}
                except subprocess.TimeoutExpired:
                    record = {"case": case, "passed": False, "error": "3-second timeout"}
                report["cases"].append(record)
                print(("PASS " if record["passed"] else "FAIL ") + case)
        else:
            print(compiled.stderr)
    report["passed"] = compiled.returncode == 0 and len(report["cases"]) == len(cases) and all(case["passed"] for case in report["cases"])
    if arguments.output:
        with arguments.output.open("x") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    print(json.dumps({"passed": report["passed"], "cases": len(report["cases"]),
                      "failures": sum(not case["passed"] for case in report["cases"])}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
