"""Exercise production NASTA decode/encode/HAL-loop functions with real cJSON."""

import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


native = Path(sys.argv[1])
dependencies = Path(sys.argv[2]) if len(sys.argv) > 2 else (
    Path(__file__).resolve().parent / "onewifi-query-test-deps"
)
header = (native / "include/wifi_base.h").read_text()
structures = re.search(r"#define MAX_NASTA_OPCLASS_ENTRIES.*?\} nasta_query_t;", header, re.S).group()
codec = (native / "source/webconfig/wifi_webconfig_nasta.c").read_text()
control = (native / "source/core/wifi_ctrl_webconfig.c").read_text()


def function(source, signature):
    return re.search(re.escape(signature) + r"\(.*?\n\}", source, re.S).group()


production = "\n\n".join([
    function(codec, "webconfig_error_t encode_nasta_query_subdoc"),
    function(codec, "webconfig_error_t decode_nasta_query_subdoc"),
    function(control, "int webconfig_nasta_apply"),
])
program = r"""
#define _POSIX_C_SOURCE 200809L
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <assert.h>
#include "cJSON.h"
#if CJSON_VERSION_MAJOR == 1 && CJSON_VERSION_MINOR == 7 && CJSON_VERSION_PATCH < 13
#define cJSON_GetNumberValue(object) ((object)->valuedouble)
#endif
typedef unsigned char mac_address_t[6];
typedef unsigned char wifi_hal_capability_t[16];
typedef struct {
    mac_address_t sta_mac;
    unsigned int channel;
    unsigned int op_class;
    unsigned int rcpi;
} wifi_na_sta_info_t;
typedef wifi_na_sta_info_t wifi_na_sta_req_params_t;
STRUCTURES
typedef int webconfig_error_t;
enum { webconfig_error_none, webconfig_error_encode, webconfig_error_decode,
       webconfig_error_invalid_subdoc };
enum { webconfig_subdoc_type_nasta_query, webconfig_data_descriptor_decoded,
       bus_data_type_string };
#define WIFI_HAL_SUCCESS 0
#define RETURN_OK 0
#define RETURN_ERR -1
#define bus_error_success 0
#define WIFI_NASTA_RESPONSE_EVENT "Device.WiFi.EM.NaStaResponse"
#define wifi_util_error_print(...) ((void)0)
#define wifi_util_info_print(...) ((void)0)
#define wifi_util_dbg_print(...) ((void)0)
typedef char *webconfig_subdoc_encoded_raw_t;
typedef struct {
    nasta_query_t nasta_query;
    nasta_response_t *nasta_response;
    wifi_hal_capability_t hal_cap;
} webconfig_subdoc_decoded_data_t;
typedef struct {
    int type;
    int descriptor;
    union {
        struct { char *raw; cJSON *json; } encoded;
        webconfig_subdoc_decoded_data_t decoded;
    } u;
} webconfig_subdoc_data_t;
typedef struct webconfig webconfig_t;
typedef struct {
    unsigned int num_objects;
    struct { const char *name; } objects[3];
    int (*encode_subdoc)(webconfig_t *, webconfig_subdoc_data_t *);
} webconfig_subdoc_t;
struct webconfig { webconfig_subdoc_t subdocs[1]; };
typedef struct { webconfig_t webconfig; int handle; } wifi_ctrl_t;
typedef struct {
    int data_type;
    struct { void *bytes; } raw_data;
    unsigned int raw_data_len;
} raw_data_t;
typedef struct { int (*bus_event_publish_fn)(int *, const char *, raw_data_t *); } bus_descriptor_t;
char *published;
uint64_t test_now_ms;
uint64_t hal_delay_ms;
uint64_t publish_delay_ms;
int clock_failure;
int clock_calls;
int hal_calls;
int failing_station;
int decoded_has_query_id;
int decoded_query_id;
static int test_clock_gettime(clockid_t clock_id, struct timespec *value)
{
    assert(clock_id == CLOCK_MONOTONIC);
    ++clock_calls;
    if (clock_failure == 1) return -1;
    value->tv_sec = (time_t)(test_now_ms / 1000);
    value->tv_nsec = (long)(test_now_ms % 1000) * 1000000;
    if (clock_failure == 2) value->tv_nsec = 1000000000L;
    if (clock_failure == 3) value->tv_sec = -1;
    return 0;
}
static int wifi_getNASta(unsigned int vap_index, wifi_na_sta_req_params_t *request,
                         wifi_na_sta_info_t *response)
{
    assert(vap_index == 7);
    ++hal_calls;
    test_now_ms += hal_delay_ms;
    if (failing_station == 256 || failing_station == request->sta_mac[5]) return -1;
    *response = *request;
    response->rcpi = 96;
    return WIFI_HAL_SUCCESS;
}
static int publish(int *handle, const char *event, raw_data_t *data)
{
    assert(handle != NULL && strcmp(event, WIFI_NASTA_RESPONSE_EVENT) == 0);
    assert(data->raw_data_len == strlen(data->raw_data.bytes) + 1);
    test_now_ms += publish_delay_ms;
    free(published);
    published = strdup(data->raw_data.bytes);
    return bus_error_success;
}
static bus_descriptor_t *get_bus_descriptor(void)
{
    static bus_descriptor_t descriptor = {publish};
    return &descriptor;
}
#define clock_gettime test_clock_gettime
PRODUCTION
int run_query(const char *request)
{
    wifi_ctrl_t ctrl = {0};
    webconfig_subdoc_data_t data = {0};
    ctrl.webconfig.subdocs[0].num_objects = 3;
    ctrl.webconfig.subdocs[0].objects[0].name = "Version";
    ctrl.webconfig.subdocs[0].objects[1].name = "SubDocName";
    ctrl.webconfig.subdocs[0].objects[2].name = "UnassocStaQueryList";
    ctrl.webconfig.subdocs[0].encode_subdoc = encode_nasta_query_subdoc;
    free(published);
    published = NULL;
    clock_calls = hal_calls = 0;
    decoded_has_query_id = decoded_query_id = -1;
    data.u.encoded.json = cJSON_Parse(request);
    int result = decode_nasta_query_subdoc(&ctrl.webconfig, &data);
    if (result != webconfig_error_none) return result;
    decoded_has_query_id = data.u.decoded.nasta_query.has_query_id;
    decoded_query_id = data.u.decoded.nasta_query.query_id;
    return webconfig_nasta_apply(&ctrl, &data.u.decoded);
}
int encode_timestamp(uint64_t timestamp)
{
    nasta_response_t response = {0};
    webconfig_subdoc_data_t data = {0};
    response.has_query_id = true;
    response.collected_monotonic_ms = timestamp;
    data.u.decoded.nasta_response = &response;
    int result = encode_nasta_query_subdoc(NULL, &data);
    if (result == webconfig_error_none) free(data.u.encoded.raw);
    return result;
}
""".replace("STRUCTURES", structures).replace("PRODUCTION", production)

with tempfile.TemporaryDirectory(prefix="onewifi-nasta-query-") as temporary:
    directory = Path(temporary)
    library = directory / "test.so"
    (directory / "libcjson.so.1").symlink_to((dependencies / "libcjson.so").resolve())
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
        "-shared", "-fPIC", "-x", "c", "-", "-x", "none",
        "-I", str(dependencies), str(dependencies / "libcjson.so"),
        "-Wl,-rpath," + str(directory), "-o", str(library),
    ], input=program, text=True, check=True)
    implementation = ctypes.CDLL(str(library), mode=os.RTLD_LOCAL)
    implementation.run_query.argtypes = [ctypes.c_char_p]
    implementation.run_query.restype = ctypes.c_int
    implementation.encode_timestamp.argtypes = [ctypes.c_uint64]
    implementation.encode_timestamp.restype = ctypes.c_int

    def field(name, value=None):
        kind = ctypes.c_uint64 if name.endswith("_ms") else ctypes.c_int
        variable = kind.in_dll(implementation, name)
        if value is not None:
            variable.value = value
        return variable.value

    def request():
        return {
            "Version": "1.0", "SubDocName": "UnassocStaQuery", "VapIndex": 7,
            "UnassocStaQueryList": [{"opclass": 115, "channels": [
                {"channel": 36, "sta_macs": ["02:00:00:00:00:01", "02:00:00:00:00:02"]}
            ]}],
        }

    def run(payload, *, now=1000123, clock=0, failing=-1, hal_delay=3100, publish_delay=27000):
        field("test_now_ms", now)
        field("clock_failure", clock)
        field("failing_station", failing)
        field("hal_delay_ms", hal_delay)
        field("publish_delay_ms", publish_delay)
        result = implementation.run_query(json.dumps(payload).encode())
        published = ctypes.c_char_p.in_dll(implementation, "published").value
        return result, json.loads(published) if published else None

    for identifier in (0, 1, 65535, 32768, 0):
        payload = request()
        payload["QueryId"] = identifier
        result, response = run(payload)
        assert result == 0 and response["QueryId"] == identifier
        assert response["CollectedMonotonicMs"] == 1000123
        assert field("decoded_has_query_id") == 1 and field("decoded_query_id") == identifier
        assert field("clock_calls") == 1 and field("hal_calls") == 2
        assert field("test_now_ms") == 1033323
        stations = response["UnassociatedSTALinkMetricsResponse"]["sta_list"]
        assert len(stations) == 2 and stations[0]["rcpi"] == 96
        assert stations[0]["channel"] == 36 and stations[0]["op_class"] == 115
    print("PASS: MID zero/boundaries, real JSON round-trip, one pre-HAL timestamp despite collection/publication delay")

    for invalid in (-1, 65536, 0.5, 65534.5, "7", None, True, False, {}, [], 1e100):
        payload = request()
        payload["QueryId"] = invalid
        result, response = run(payload)
        assert result != 0 and response is None and field("hal_calls") == 0, invalid
    for clock in (1, 2, 3):
        result, response = run({**request(), "QueryId": 1}, clock=clock)
        assert result != 0 and response is None and field("hal_calls") == 0
    result, response = run({**request(), "QueryId": 1}, now=0)
    assert result != 0 and response is None
    print("PASS: invalid tags and missing/invalid clock fail closed without HAL work")

    for failing, expected in ((2, 1), (256, 0)):
        result, response = run({**request(), "QueryId": 45}, failing=failing)
        assert result == 0 and response["QueryId"] == 45
        assert response["CollectedMonotonicMs"] == 1000123
        assert response["UnassociatedSTALinkMetricsResponse"]["num_sta"] == expected
    payload = {**request(), "QueryId": 46, "UnassocStaQueryList": []}
    result, response = run(payload)
    assert result == 0 and response["QueryId"] == 46 and field("hal_calls") == 0
    print("PASS: partial/all-failed/empty collection retains correlation and original timestamp")

    result, response = run(request(), clock=1)
    assert result == 0 and "QueryId" not in response and "CollectedMonotonicMs" not in response
    assert field("decoded_has_query_id") == 0 and field("clock_calls") == 0
    assert response["UnassociatedSTALinkMetricsResponse"]["num_sta"] == 2
    for now in (2**40 + 123, 2**53 - 1):
        result, response = run({**request(), "QueryId": 0}, now=now)
        assert result == 0 and response["CollectedMonotonicMs"] == now
    assert implementation.encode_timestamp(0) != 0
    assert implementation.encode_timestamp(2**53) != 0
    result, response = run({**request(), "QueryId": 0}, now=2**53)
    assert result != 0 and response is None and field("hal_calls") == 0
    print("PASS: legacy requests unchanged, tagged/untagged isolation, 64-bit timestamps and exact JSON-number bounds")

    payload = {**request(), "QueryId": 77}
    result, first = run(payload, now=400000, hal_delay=0, publish_delay=0)
    assert result == 0
    result, second = run({**payload, "QueryId": 78}, now=440000, hal_delay=0, publish_delay=0)
    assert result == 0 and first["QueryId"] != second["QueryId"]
    assert first["CollectedMonotonicMs"] == 400000 and second["CollectedMonotonicMs"] == 440000
    payload["UnassocStaQueryList"] = [
        {"opclass": 115, "channels": [
            {"channel": 36, "sta_macs": [f"02:00:00:00:00:{station:02x}" for station in range(1, 9)]}
            for channel in range(8)
        ]} for operating_class in range(8)
    ]
    result, response = run(payload, hal_delay=1)
    assert result == 0 and field("hal_calls") == 512 and field("clock_calls") == 1
    assert response["UnassociatedSTALinkMetricsResponse"]["num_sta"] == 512
    assert response["CollectedMonotonicMs"] == 1000123
    print("PASS: repeated rounds stay distinct; maximum bounded 512-entry batch preserves conservative collection age")
