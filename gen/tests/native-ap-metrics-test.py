"""Compile the production threshold evaluator and AP-query parser without platform services."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile


native = Path(sys.argv[1])
onewifi = Path(sys.argv[2])
header = (native / "inc/em_base.h").read_text()
params = re.search(r"typedef struct \{\n    int num_radios;.*?em_cmd_ap_metrics_rprt_params_t;", header, re.S).group()
macros = "\n".join(re.search(r"^#define\s+" + name + r"\s+.*$", header, re.M).group()
                   for name in ("EM_MAX_BANDS", "EM_MAX_RADIO_PER_AGENT", "EM_MAX_BSSS"))
program = r"""
#include <cassert>
#include <cstdio>
#include <vector>
#include <string>
using mac_address_t = unsigned char[6];
MACROS
PARAMS
#include "em_ap_metrics_query.h"
#include "wifi_em_util_threshold.h"
int main() {
    em_util_threshold_t state{};
    assert(!em_util_threshold_crossed(&state, 128, 6, 32, true));
    assert(!em_util_threshold_crossed(&state, 128, 6, 32, true));
    assert(em_util_threshold_crossed(&state, 128, 6, 224, true));
    assert(!em_util_threshold_crossed(&state, 128, 6, 224, true));
    assert(!em_util_threshold_crossed(&state, 128, 6, 0, false));
    assert(em_util_threshold_crossed(&state, 128, 6, 32, true));
    assert(em_util_threshold_crossed(&state, 128, 6, 128, true));
    assert(!em_util_threshold_crossed(&state, 128, 6, 128, true));
    assert(!em_util_threshold_crossed(&state, 128, 11, 32, true));
    assert(!em_util_threshold_crossed(&state, 64, 11, 224, true));
    assert(!em_util_threshold_crossed(&state, 0, 11, 32, true));
    assert(!state.valid);
    assert(!em_util_threshold_crossed(&state, 128, 11, 224, true));
    assert(em_util_threshold_crossed(&state, 128, 11, 0, true));
    assert(!em_util_threshold_crossed(&state, 128, 11, 256, true));
    assert(em_util_threshold_crossed(&state, 128, 11, 255, true));
    const std::string query = "020000000002020000000001893a0000800b1234008093000701aabbccddeeff000000";
    em_cmd_ap_metrics_rprt_params_t params{};
    assert(em_decode_ap_metrics_query_hex(query.data(), query.size(), params));
    assert(params.query && params.query_id == 0x1234 && params.query_bss_count == 1);
    assert(params.query_radio_count == 0 && params.query_source[5] == 1);
    const unsigned char bssid[] = {0xaa,0xbb,0xcc,0xdd,0xee,0xff};
    assert(em_ap_metrics_query_contains(params.query_bssids, params.query_bss_count, bssid));
    const unsigned char other[] = {0xaa,0xbb,0xcc,0xdd,0xee,0xfe};
    assert(!em_ap_metrics_query_contains(params.query_bssids, params.query_bss_count, other));
    for (size_t length = 0; length < query.size(); ++length) {
        assert(!em_decode_ap_metrics_query_hex(query.data(), length, params));
    }
    for (const std::string &malformed : {
        query.substr(0, 48) + "06" + query.substr(50),
        query.substr(0, 50) + "02" + query.substr(52),
        query.substr(0, 40) + "01" + query.substr(42),
        query.substr(0, 42) + "00" + query.substr(44),
        query.substr(0, 60) + "zz" + query.substr(62),
        query.substr(0, query.size() - 6) + "93000701aabbccddeeff000000"
    }) {
        assert(!em_decode_ap_metrics_query_hex(malformed.data(), malformed.size(), params));
    }
    const std::string radio_query = query.substr(0, query.size() - 6) + "820006010203040506000000";
    assert(em_decode_ap_metrics_query_hex(radio_query.data(), radio_query.size(), params));
    assert(params.query_radio_count == 1 && params.query_radios[0][5] == 6);
    const std::string zero_mid = query.substr(0, 36) + "0000" + query.substr(40);
    assert(em_decode_ap_metrics_query_hex(zero_mid.data(), zero_mid.size(), params));
    assert(params.query_id == 0);
    puts("PASS: native threshold edges, invalid samples, policy/channel resets, query bounds/MID/BSSID/radio selection");
}
""".replace("MACROS", macros).replace("PARAMS", params)
with tempfile.TemporaryDirectory(prefix="native-ap-metrics-") as temporary:
    executable = Path(temporary) / "test"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-x", "c++", "-",
                    "-I", str(native / "inc"), "-I", str(onewifi / "include"),
                    "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)

metrics_source = (native / "src/em/metrics/em_metrics.cpp").read_text()
handler = metrics_source.split("int em_metrics_t::handle_ap_metrics_query(", 1)[1].split(
    "\nint em_metrics_t::send_ap_metrics_response", 1)[0]
handoff_program = r"""
#include <cassert>
#include <cstdio>
#include <vector>
#include <string>
using mac_address_t = unsigned char[6];
MACROS
PARAMS
#include "em_ap_metrics_query.h"
enum { em_bus_event_type_ap_metrics_query };
struct Model {
    unsigned char controller[6] = {2,0,0,0,0,1};
    const unsigned char *get_ctl_mac() { return controller; }
};
struct Manager {
    std::string raw;
    void io_process(int, char *, unsigned int) { assert(false); }
    void io_process(int type, unsigned char *data, unsigned int length) {
        assert(type == em_bus_event_type_ap_metrics_query && data[length - 1] == 0);
        raw.assign(reinterpret_cast<char *>(data), length - 1);
    }
};
struct em_metrics_t {
    Model model;
    Manager manager;
    Model *get_data_model() { return &model; }
    Manager *get_mgr() { return &manager; }
    int handle_ap_metrics_query(unsigned char *, unsigned int);
};
HANDLER
int main() {
    const std::string query = "020000000002020000000001893a0000800b1234008093000701aabbccddeeff000000";
    std::vector<unsigned char> frame;
    for (size_t offset = 0; offset < query.size(); offset += 2)
        frame.push_back(static_cast<unsigned char>(std::stoul(query.substr(offset, 2), nullptr, 16)));
    em_metrics_t metrics;
    assert(metrics.handle_ap_metrics_query(frame.data(), frame.size()) == 0);
    assert(metrics.manager.raw == query);
    metrics.manager.raw.clear();
    frame[11] = 3;
    assert(metrics.handle_ap_metrics_query(frame.data(), frame.size()) == -1);
    assert(metrics.manager.raw.empty());
    puts("PASS: native raw-event handoff preserves query and rejects an unknown controller");
}
""".replace("MACROS", macros).replace("PARAMS", params).replace(
    "HANDLER", "int em_metrics_t::handle_ap_metrics_query(" + handler)
with tempfile.TemporaryDirectory(prefix="native-ap-metrics-handoff-") as temporary:
    executable = Path(temporary) / "test"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-x", "c++", "-",
                    "-I", str(native / "inc"), "-o", str(executable)],
                   input=handoff_program, text=True, check=True)
    subprocess.run([str(executable)], check=True)

timer = re.search(r"int em_ap_report_config_task\(.*?\n\}",
                  (onewifi / "source/apps/em/wifi_em.c").read_text(), re.S).group()
timer_program = r"""
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#define RETURN_OK 0
#define RETURN_ERR -1
#define FALSE 0
typedef int em_policy_req_type_t;
typedef int wifi_mon_stats_request_state_t;
enum {mon_stats_request_state_start, mon_stats_request_state_stop};
typedef struct { struct {int interval;} ap_metric_policy; } em_config_t;
typedef struct {void *sched;} controller_t;
typedef struct {controller_t *ctrl;} wifi_app_t;
typedef struct {
    wifi_app_t *app; int policy_type; em_config_t policy_config;
    const char *query; int sched_id; int current_interval;
} em_ap_report_callback_arg_t;
static struct {em_ap_report_callback_arg_t args;} em_ap_metrics_report_cache;
static int added, updated, cancelled, failure;
static int ap_report_push_cb(em_ap_report_callback_arg_t *args) { return 0; }
static int scheduler_add_timer_task(void *sched, int high, int *identifier, void *callback,
    void *args, int milliseconds, int repetitions, int immediate) {
    assert(milliseconds > 0); ++added; *identifier = 12; return failure;
}
static int scheduler_update_timer_task_interval(void *sched, int identifier, int milliseconds) {
    assert(identifier == 12 && milliseconds > 0); ++updated; return failure;
}
static int scheduler_cancel_timer_task(void *sched, int identifier) {
    assert(identifier == 12); ++cancelled; return failure;
}
TIMER
int main(void) {
    controller_t ctrl = {0}; wifi_app_t app = {&ctrl}; em_config_t config = {{0}};
    assert(em_ap_report_config_task(&app, &config, 0, 0, 0) == 0);
    assert(added == 0 && cancelled == 0);
    config.ap_metric_policy.interval = 5;
    assert(em_ap_report_config_task(&app, &config, 0, 0, 0) == 0);
    assert(added == 1 && em_ap_metrics_report_cache.args.current_interval == 5);
    assert(em_ap_report_config_task(&app, &config, 0, 0, 0) == 0);
    assert(added == 1 && updated == 0);
    config.ap_metric_policy.interval = 120;
    assert(em_ap_report_config_task(&app, &config, 0, 0, 0) == 0);
    assert(updated == 1);
    failure = -1;
    config.ap_metric_policy.interval = 10;
    assert(em_ap_report_config_task(&app, &config, 0, 0, 0) == -1);
    assert(em_ap_metrics_report_cache.args.current_interval == 120);
    failure = 0;
    config.ap_metric_policy.interval = 0;
    assert(em_ap_report_config_task(&app, &config, 0, 0, 0) == 0);
    assert(cancelled == 1 && em_ap_metrics_report_cache.args.sched_id == 0);
    assert(em_ap_metrics_report_cache.args.app == &app);
    assert(em_ap_report_config_task(&app, &config, 0, 0, 0) == 0);
    assert(cancelled == 1);
    puts("PASS: timer start/update, idempotent policy, zero interval and scheduler failure");
}
""".replace("TIMER", timer)
with tempfile.TemporaryDirectory(prefix="native-ap-metrics-timer-") as temporary:
    executable = Path(temporary) / "test"
    subprocess.run(["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                    "-x", "c", "-", "-o", str(executable)], input=timer_program, text=True, check=True)
    subprocess.run([str(executable)], check=True)

callback = re.search(r"static bus_error_t em_request_ap_metrics\(.*?\n\}",
                     (onewifi / "source/apps/em/wifi_em.c").read_text(), re.S).group()
bus_program = r"""
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef int bus_error_t;
enum { bus_data_type_string, bus_error_invalid_input, bus_error_general,
       bus_error_success, wifi_event_type_command, wifi_event_type_em_ap_metrics_query };
#define RETURN_OK 0
typedef struct { int data_type; struct { void *bytes; } raw_data; size_t raw_data_len; } raw_data_t;
static char delivered[4097];
static int queue_result;
int push_event_to_ctrl_queue(void *request, size_t length, int event, int subtype, void *route) {
    assert(event == wifi_event_type_command && subtype == wifi_event_type_em_ap_metrics_query);
    assert(length <= sizeof(delivered));
    memcpy(delivered, request, length);
    assert(delivered[length - 1] == 0);
    return queue_result;
}
CALLBACK
int main(void) {
    char query[] = "020000000002020000000001893a0000800b1234008093000701aabbccddeeff000000";
    raw_data_t request = {bus_data_type_string, {query}, sizeof(query)};
    assert(em_request_ap_metrics(NULL, &request, NULL) == bus_error_success);
    assert(strcmp(delivered, query) == 0);
    request.raw_data_len = strlen(query);
    assert(em_request_ap_metrics(NULL, &request, NULL) == bus_error_success);
    assert(strcmp(delivered, query) == 0);
    queue_result = -1;
    assert(em_request_ap_metrics(NULL, &request, NULL) == bus_error_general);
    queue_result = 0;
    request.raw_data_len--;
    assert(em_request_ap_metrics(NULL, &request, NULL) == bus_error_invalid_input);
    request.raw_data_len++;
    query[15] = 'z';
    assert(em_request_ap_metrics(NULL, &request, NULL) == bus_error_invalid_input);
    query[15] = 0;
    assert(em_request_ap_metrics(NULL, &request, NULL) == bus_error_invalid_input);
    request.raw_data_len = 4098;
    assert(em_request_ap_metrics(NULL, &request, NULL) == bus_error_invalid_input);
    puts("PASS: RBUS length conventions, bounded strings, invalid input and queue rejection");
}
""".replace("CALLBACK", callback)
with tempfile.TemporaryDirectory(prefix="native-ap-metrics-bus-") as temporary:
    executable = Path(temporary) / "test"
    subprocess.run(["gcc", "-std=c99", "-D_POSIX_C_SOURCE=200809L", "-Wall", "-Wextra",
                    "-Werror", "-Wno-unused-parameter", "-x", "c", "-", "-o", str(executable)],
                   input=bus_program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
