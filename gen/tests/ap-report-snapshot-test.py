"""Compile production AP snapshot parsing and full response building with isolated endpoints."""

import copy
import ctypes
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile


native = Path(sys.argv[1])
dependencies = Path(sys.argv[2]) if len(sys.argv) > 2 else (
    Path(__file__).resolve().parent / "onewifi-query-test-deps"
)
header = (native / "inc/em_base.h").read_text()
params = re.search(r"typedef struct \{\n    int num_radios;.*?em_cmd_ap_metrics_rprt_params_t;", header, re.S).group()
macros = "\n".join(re.search(r"^#define\s+" + name + r"\s+.*$", header, re.M).group()
                   for name in ("EM_MAX_BANDS", "EM_MAX_RADIO_PER_AGENT", "EM_MAX_BSSS"))
metrics = (native / "src/em/metrics/em_metrics.cpp").read_text()


def function(signature):
    return re.search(re.escape(signature) + r"\(.*?\n\}", metrics, re.S).group()


methods = "\n\n".join(function(signature) for signature in (
    "int em_metrics_t::send_ap_metrics_response",
    "short em_metrics_t::create_ap_report_backhaul_link_metrics_tlv",
    "short em_metrics_t::create_assoc_sta_link_metrics_tlv",
))
program = r"""
#include <arpa/inet.h>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <vector>
#include <algorithm>
#include "cjson/cJSON.h"
using mac_address_t = unsigned char[6];
MACROS
PARAMS
#include "em_ap_metrics_query.h"
constexpr unsigned int MAX_EM_BUFF_SZ = 1024;
constexpr unsigned int EM_MAX_TLV_MEMBERS = 64;
constexpr unsigned short ETH_P_1905 = 0x893a;
enum { em_vap_mode_ap, em_vap_mode_sta, em_haul_type_backhaul, em_haul_type_fronthaul };
enum { em_profile_type_1 = 1, em_profile_type_2, em_profile_type_3 };
constexpr int em_msg_type_ap_metrics_rsp = 0x800c;
enum { em_tlv_type_eom, em_tlv_type_ap_metrics = 0x94,
       em_tlv_type_assoc_sta_link_metric = 0x96, em_tlv_type_ap_ext_metric,
       em_tlv_type_assoc_sta_traffic_sts, em_tlv_type_assoc_sta_ext_link_metric,
       em_tlv_type_assoc_wifi6_sta_rprt, em_tlv_type_vendor_specific, em_tlv_type_radio_metric };
struct em_raw_hdr_t { unsigned char bytes[14]; };
struct __attribute__((packed)) em_cmdu_t {
    unsigned char version, reserved;
    unsigned short type, id;
    unsigned char fragment, last_frag_ind;
};
struct __attribute__((packed)) em_tlv_t {
    unsigned char type;
    unsigned short len;
    unsigned char value[0];
};
struct __attribute__((packed)) em_assoc_link_metrics_t {
    mac_address_t bssid;
    unsigned int time_delta_ms, est_mac_data_rate_dl, est_mac_data_rate_ul;
    unsigned char rcpi;
};
struct __attribute__((packed)) em_assoc_sta_link_metrics_t {
    mac_address_t sta_mac;
    unsigned char num_bssids;
    em_assoc_link_metrics_t assoc_link_metrics[0];
};
static_assert(sizeof(em_assoc_link_metrics_t) == 19, "wire metric size");
struct Interface { mac_address_t mac{}; };
struct em_bss_info_t {
    Interface bssid, ruid;
    int vap_mode = em_vap_mode_ap;
    struct { int haul_type = em_haul_type_backhaul; } id;
};
struct dm_bss_t {
    em_bss_info_t m_bss_info;
    em_bss_info_t *get_bss_info() { return &m_bss_info; }
};
struct em_sta_info_t {
    mac_address_t id{}, bssid{};
    unsigned int delta_ms = 0, est_dl_rate = 10, est_ul_rate = 20;
    unsigned char rcpi = 218;
};
struct dm_sta_t {
    em_sta_info_t m_sta_info;
    em_sta_info_t *get_sta_info() { return &m_sta_info; }
};
using StationMap = std::vector<dm_sta_t *>;
size_t hash_map_count(StationMap *stations) { return stations->size(); }
void *hash_map_get_first(StationMap *stations) { return stations->empty() ? nullptr : stations->front(); }
void *hash_map_get_next(StationMap *stations, void *station) {
    auto found = std::find(stations->begin(), stations->end(), station);
    return found == stations->end() || ++found == stations->end() ? nullptr : *found;
}
struct dm_easy_mesh_t {
    unsigned int m_num_bss = 2;
    dm_bss_t m_bss[EM_MAX_BSSS];
    StationMap stations;
    StationMap *m_sta_map = &stations;
    mac_address_t controller{2,0,0,0,0,0xc1}, agent{2,0,0,0,0,0xc2};
    unsigned int get_num_bss() { return m_num_bss; }
    em_bss_info_t *get_bss_info(unsigned int index) { return &m_bss[index].m_bss_info; }
    unsigned char *get_ctl_mac() { return controller; }
    unsigned char *get_agent_al_interface_mac() { return agent; }
};
#include "em_ap_report_snapshot.h"
void em_printfout(const char *, ...) {}
namespace util { const char *mac_to_string(const unsigned char *) = delete; }
struct Label { const char *c_str() const { return "agent"; } };
namespace util { Label mac_to_string(unsigned char *) { return {}; } }
struct em_msg_t {
    em_msg_t(int, int, unsigned char *, unsigned int) {}
    int validate(char **) { return 1; }
};
struct Manager { unsigned short get_next_msg_id() { return 77; } };
std::vector<unsigned char> captured;
struct em_metrics_t {
    dm_easy_mesh_t model;
    Manager manager;
    dm_easy_mesh_t *get_data_model() { return &model; }
    Manager *get_mgr() { return &manager; }
    int get_profile_type() { return em_profile_type_3; }
    int send_frame(unsigned char *frame, unsigned int length) {
        captured.assign(frame, frame + length);
        return static_cast<int>(length);
    }
    short create_ap_metrics_tlv(unsigned char *output, dm_bss_t &bss, const em_cmd_ap_metrics_rprt_params_t &) {
        memcpy(output, bss.m_bss_info.bssid.mac, 6);
        return 6;
    }
    short create_ap_ext_metrics_tlv(unsigned char *, dm_bss_t &, const em_cmd_ap_metrics_rprt_params_t &) { return 1; }
    short create_radio_metrics_tlv(unsigned char *, int, const em_cmd_ap_metrics_rprt_params_t &) { return 1; }
    short create_assoc_sta_traffic_stats_tlv(unsigned char *, dm_sta_t *) { return 1; }
    short create_assoc_ext_sta_link_metrics_tlv(unsigned char *, mac_address_t, dm_sta_t *) { return 1; }
    short create_assoc_wifi6_sta_sta_report_tlv(unsigned char *, dm_sta_t *) { return 1; }
    short create_assoc_vendor_sta_link_metrics_tlv(unsigned char *, mac_address_t, dm_sta_t *) { return 1; }
    short create_device_uptime_tlv(unsigned char *) { return 1; }
    int send_ap_metrics_response(const em_cmd_ap_metrics_rprt_params_t &);
    short create_ap_report_backhaul_link_metrics_tlv(unsigned char *, const em_cmd_ap_metrics_rprt_params_t &, unsigned int);
    short create_assoc_sta_link_metrics_tlv(unsigned char *, mac_address_t, const dm_sta_t *const);
};
METHODS
extern "C" {
unsigned int snapshot_count;
unsigned int params_size = sizeof(em_cmd_ap_metrics_rprt_params_t);
unsigned int snapshot_capacity = EM_MAX_BSSS * EM_MAX_RADIO_PER_AGENT;
const void *frame_data() { return captured.data(); }
size_t frame_size() { return captured.size(); }
int run_report(const char *document, int mode) {
    captured.clear();
    snapshot_count = 0;
    em_metrics_t metrics;
    auto &model = metrics.model;
    mac_address_t backhaul{2,0,0,0,0,0x10}, fronthaul{2,0,0,0,0,0x20};
    mac_address_t ruid{2,0,0,0,0,1};
    for (unsigned int index = 0; index < 2; ++index) {
        memcpy(model.m_bss[index].m_bss_info.ruid.mac, ruid, 6);
        memcpy(model.m_bss[index].m_bss_info.bssid.mac, index == 0 ? backhaul : fronthaul, 6);
    }
    model.m_bss[1].m_bss_info.id.haul_type = em_haul_type_fronthaul;
    dm_sta_t reported, omitted, client;
    reported.m_sta_info.id[0] = omitted.m_sta_info.id[0] = client.m_sta_info.id[0] = 2;
    reported.m_sta_info.id[5] = 0xa1;
    omitted.m_sta_info.id[5] = 0xa2;
    client.m_sta_info.id[5] = 0xb1;
    memcpy(reported.m_sta_info.bssid, backhaul, 6);
    memcpy(omitted.m_sta_info.bssid, backhaul, 6);
    memcpy(client.m_sta_info.bssid, fronthaul, 6);
    client.m_sta_info.rcpi = 100;
    model.stations = {&reported, &omitted, &client};
    cJSON *root = cJSON_Parse(document);
    if (root == nullptr) return -1;
    cJSON *reports = cJSON_GetObjectItemCaseSensitive(root, "EMAPMetricsReport");
    em_cmd_ap_metrics_rprt_params_t params{};
    params.num_radios = cJSON_GetArraySize(reports);
    if (params.num_radios > EM_MAX_RADIO_PER_AGENT) { cJSON_Delete(root); return -1; }
    for (int slot = 0; slot < params.num_radios; ++slot) {
        cJSON *radio = cJSON_GetArrayItem(reports, slot);
        unsigned int radio_index;
        if (!em_ap_report_uint(radio, "Radio Index", radio_index) || radio_index >= EM_MAX_RADIO_PER_AGENT) {
            cJSON_Delete(root); return -1;
        }
        memcpy(params.ruid[slot], ruid, 6);
        params.ruid[slot][5] = static_cast<unsigned char>(radio_index + 1);
    }
    const bool valid = em_collect_ap_report_backhaul(reports, model, params);
    cJSON_Delete(root);
    if (!valid) return -1;
    snapshot_count = params.report_backhaul_sta_count;
    em_cmd_ap_metrics_rprt_params_t owned = params;
    memset(&params, 0, sizeof(params));
    reported.m_sta_info.rcpi = 220;
    reported.m_sta_info.delta_ms = 0;
    if (mode == 1) model.stations = {&client};
    if (mode == 2) model.m_bss[0].m_bss_info.id.haul_type = em_haul_type_fronthaul;
    if (mode == 3) {
        owned.query = true;
        owned.query_id = 0x1234;
        memcpy(owned.query_source, model.controller, 6);
        owned.query_bss_count = 1;
        memcpy(owned.query_bssids[0], fronthaul, 6);
    }
    if (mode == 4) model.m_bss[0].m_bss_info.ruid.mac[5] = 2;
    return metrics.send_ap_metrics_response(owned) > 0 ? 0 : -1;
}
}
""".replace("MACROS", macros).replace("PARAMS", params).replace("METHODS", methods)

with tempfile.TemporaryDirectory(prefix="ap-report-snapshot-") as temporary:
    directory = Path(temporary)
    (directory / "cjson").mkdir()
    (directory / "cjson/cJSON.h").symlink_to((dependencies / "cJSON.h").resolve())
    (directory / "libcjson.so.1").symlink_to((dependencies / "libcjson.so").resolve())
    library = directory / "test.so"
    subprocess.run([
        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
        "-shared", "-fPIC", "-x", "c++", "-", "-x", "none",
        "-I", str(directory), "-I", str(native / "inc"), str(dependencies / "libcjson.so"),
        "-Wl,-rpath," + str(directory), "-o", str(library),
    ], input=program, text=True, check=True)
    implementation = ctypes.CDLL(str(library))
    implementation.run_report.argtypes = [ctypes.c_char_p, ctypes.c_int]
    implementation.frame_data.restype = ctypes.c_void_p
    implementation.frame_size.restype = ctypes.c_size_t

    def station(mac="02:00:00:00:00:a1", rcpi=80, age=345):
        return {"STA MAC": mac, "Associated STA Link Metrics": {
            "Number of BSSIDs": 1, "Per BSSID Metrics": [{
                "BSSID": "02:00:00:00:00:10", "Time Delta": age, "RCPI": rcpi,
                "Estimated Mac Rate Down": 123456, "Estimated Mac Rate Up": 654321,
            }],
        }}

    def document():
        return {"EMAPMetricsReport": [{"Radio Index": 0, "Vap Info": [{
            "AP Metrics": {"BSSID": "02:00:00:00:00:10"},
            "Associated STA Link Metrics Report": [station()],
        }, {"AP Metrics": {"BSSID": "02:00:00:00:00:20"}}]}]}

    def run(payload, mode=0):
        result = implementation.run_report(json.dumps(payload).encode(), mode)
        if result != 0:
            return result, []
        packet = ctypes.string_at(implementation.frame_data(), implementation.frame_size())
        samples = []
        offset = 22
        while offset + 3 <= len(packet):
            tag, length = struct.unpack_from("!BH", packet, offset)
            offset += 3
            assert offset + length <= len(packet)
            if tag == 0x96:
                value = packet[offset:offset + length]
                assert length == 26 and value[6] == 1
                samples.append({"station": value[:6].hex(), "bssid": value[7:13].hex(),
                                "age": struct.unpack_from("!I", value, 13)[0],
                                "down": struct.unpack_from("!I", value, 17)[0],
                                "up": struct.unpack_from("!I", value, 21)[0], "rcpi": value[25]})
            offset += length
            if tag == 0:
                assert offset == len(packet)
                break
        return result, samples

    for mode in (0, 1, 2):
        result, samples = run(document(), mode)
        assert result == 0 and len(samples) == 2, (mode, samples)
        backhaul = next(sample for sample in samples if sample["station"] == "0200000000a1")
        assert backhaul == {"station": "0200000000a1", "bssid": "020000000010",
                            "age": 345, "down": 123456, "up": 654321, "rcpi": 80}
        assert all(sample["station"] != "0200000000a2" for sample in samples)
        assert next(sample for sample in samples if sample["station"] == "0200000000b1")["rcpi"] == 100
    print("PASS: actual AP builder emits owned BSTA values, no omitted cached BSTA, cold cache works, role changes cannot revive cached RCPI")

    for empty in ([], None):
        payload = document()
        vap = payload["EMAPMetricsReport"][0]["Vap Info"][0]
        if empty is None:
            del vap["Associated STA Link Metrics Report"]
        else:
            vap["Associated STA Link Metrics Report"] = empty
        result, samples = run(payload)
        assert result == 0 and len(samples) == 1 and samples[0]["station"] == "0200000000b1"
    for name, invalid in (("Time Delta", None), ("Time Delta", -1), ("Time Delta", 0.5),
                          ("Time Delta", 2**32), ("RCPI", 255), ("RCPI", "80")):
        payload = document()
        metric = payload["EMAPMetricsReport"][0]["Vap Info"][0]["Associated STA Link Metrics Report"][0]["Associated STA Link Metrics"]["Per BSSID Metrics"][0]
        if invalid is None:
            del metric[name]
        else:
            metric[name] = invalid
        result, samples = run(payload)
        assert result == 0 and len(samples) == 1
    payload = document()
    payload["EMAPMetricsReport"][0]["Vap Info"][0]["Associated STA Link Metrics Report"] = [station(age=2**32 - 1)]
    result, samples = run(payload)
    assert result == 0 and samples[0]["age"] == 2**32 - 1
    print("PASS: absent/empty/invalid rows never borrow live values; unknown age rejected, stale age preserved without restamping")

    for mode in (3, 4):
        result, samples = run(document(), mode)
        assert result == 0 and len(samples) == 1 and samples[0]["station"] == "0200000000b1"
    payload = document()
    payload["EMAPMetricsReport"][0]["Radio Index"] = 1
    result, samples = run(payload)
    assert result == 0 and samples == []
    print("PASS: requested-BSSID and RUID filtering prevent cross-radio evidence; fronthaul path unchanged")

    for mutation in ("duplicate_station", "duplicate_vap", "foreign_bssid", "bad_mac", "overflow"):
        payload = document()
        vaps = payload["EMAPMetricsReport"][0]["Vap Info"]
        stations = vaps[0]["Associated STA Link Metrics Report"]
        if mutation == "duplicate_station":
            stations.append(copy.deepcopy(stations[0]))
        elif mutation == "duplicate_vap":
            vaps.append(copy.deepcopy(vaps[0]))
        elif mutation == "foreign_bssid":
            stations[0]["Associated STA Link Metrics"]["Per BSSID Metrics"][0]["BSSID"] = "02:00:00:00:00:20"
        elif mutation == "bad_mac":
            stations[0]["STA MAC"] = "02:00:00:00:00:a1junk"
        else:
            capacity = ctypes.c_uint.in_dll(implementation, "snapshot_capacity").value
            vaps[0]["Associated STA Link Metrics Report"] = [station() for unused in range(capacity + 1)]
        result, samples = run(payload)
        assert result != 0 and samples == [], mutation
    print("PASS: duplicates, cross-BSSID samples, malformed addresses and bounded-array overflow fail closed")
    print("AP event parameter bytes:", ctypes.c_uint.in_dll(implementation, "params_size").value)

agent = (native / "src/agent/dm_easy_mesh_agent.cpp").read_text()
analysis = re.search(r"int dm_easy_mesh_agent_t::analyze_ap_metrics_report\(.*?\n\}", agent, re.S).group()
assert analysis.index("em_collect_ap_report_backhaul") < analysis.index("translate_and_decode_onewifi_subdoc")
assert analysis.index("em_collect_ap_report_backhaul") < analysis.index("new em_cmd_ap_metrics_report_t")
serializer = function("short em_metrics_t::create_ap_report_backhaul_link_metrics_tlv")
assert "get_data_model" not in serializer and "get_current_cmd" not in serializer
print("PASS: snapshot captured before mutable translation; serializer only consumes event-owned values")

if len(sys.argv) > 3:
    provider = Path(sys.argv[3]).read_text()
    provider_params = re.search(r"typedef struct \{\n    int num_radios;.*?em_cmd_ap_metrics_rprt_params_t;", provider, re.S).group()
    assert provider_params == params, "Header provider AP event ABI differs from runtime"
    print("PASS: installed-header provider AP parameter definition exactly matches runtime")
