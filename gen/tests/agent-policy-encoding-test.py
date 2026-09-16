"""Run real native policy types, OneWifi translator and encoder; record cJSON calls."""

from pathlib import Path
import subprocess
import sys
import tempfile

from native_policy_test_support import method, policy_types


native = Path(sys.argv[1])
libweb = Path(sys.argv[2])
types = policy_types((native / 'inc/em_base.h').read_text())
wifi_header = (libweb / 'include/wifi_base.h').read_text()
wifi_types = wifi_header.split('typedef char marker_name[32];', 1)[1].split('} em_config_t;', 1)[0]
wifi_types = 'typedef char marker_name[32];' + wifi_types + '} em_config_t;'
translator = method((libweb / 'source/webconfig/wifi_easymesh_translator.c').read_text(),
                    'webconfig_error_t translate_policy_cfg_object_from_easymesh_to_em_cfg')
encoder = method((libweb / 'source/webconfig/wifi_encoder.c').read_text(),
                 'webconfig_error_t encode_em_config_object')
program = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <vector>
#define wifi_util_error_print(...) ((void)0)
#define wifi_util_dbg_print(...) ((void)0)
using mac_address_t = unsigned char[6];
using mac_addr_t = unsigned char[6];
using bssid_t = unsigned char[6];
constexpr int MAC_ADDR_LEN = 6;
TYPES
WIFI_TYPES
using webconfig_error_t = int;
constexpr int webconfig_error_none = 0, webconfig_error_translate_from_easymesh = 1;
constexpr int webconfig_error_invalid_subdoc = 2, webconfig_error_encode = 3;
struct webconfig_external_easymesh_t { em_policy_cfg_params_t *policy_config; };
struct webconfig_subdoc_decoded_data_t { void *external_protos; em_config_t em_config; };
struct webconfig_subdoc_data_t { struct { webconfig_subdoc_decoded_data_t decoded; } u; };
struct cJSON {
    std::map<std::string, cJSON *> fields;
    std::vector<cJSON *> items;
    std::string text;
    double number = 0;
    cJSON &operator[](const char *key) { return *fields.at(key); }
};
std::vector<std::unique_ptr<cJSON>> json_nodes;
cJSON *cJSON_CreateObject() {
    json_nodes.emplace_back(new cJSON);
    return json_nodes.back().get();
}
cJSON *cJSON_CreateArray() { return cJSON_CreateObject(); }
void cJSON_AddItemToObject(cJSON *parent, const char *key, cJSON *value) { parent->fields[key] = value; }
void cJSON_AddItemToArray(cJSON *parent, cJSON *value) { parent->items.push_back(value); }
cJSON *cJSON_CreateString(const char *text) {
    auto *result = cJSON_CreateObject();
    result->text = text;
    return result;
}
void cJSON_AddSafeStringToObject(cJSON *parent, const char *key, const char *text, size_t length) {
    auto *value = cJSON_CreateObject();
    value->text.assign(text, strnlen(text, length));
    cJSON_AddItemToObject(parent, key, value);
}
void cJSON_AddStringToObject(cJSON *parent, const char *key, const char *text) {
    cJSON_AddSafeStringToObject(parent, key, text, strlen(text));
}
void cJSON_AddNumberToObject(cJSON *parent, const char *key, double number) {
    auto *value = cJSON_CreateObject();
    value->number = number;
    cJSON_AddItemToObject(parent, key, value);
}
void cJSON_AddBoolToObject(cJSON *parent, const char *key, bool value) { cJSON_AddNumberToObject(parent, key, value); }
void uint8_mac_to_string_mac(uint8_t *mac, char *text) {
    snprintf(text, 32, "%02x:%02x:%02x:%02x:%02x:%02x", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}
TRANSLATOR
ENCODER
void address(unsigned char *target) { const mac_addr_t mac = {2, 3, 4, 5, 6, 7}; memcpy(target, mac, 6); }
void check(bool enabled) {
    em_policy_cfg_params_t policy{};
    policy.metrics_policy.interval = enabled ? 7 : 0;
    policy.metrics_policy.radios_num = 1;
    auto &radio = policy.metrics_policy.radios[0];
    address(radio.ruid);
    radio.rcpi_thres = 100; radio.rcpi_hysteresis = 9; radio.util_thres = 201;
    radio.sta_policy = enabled ? 0xe0 : 0;
    strcpy(policy.vendor_policy.link_stats_alarm_policy_cfg.collection_start_time, "2030-01-01T00:00:00Z");
    policy.vendor_policy.link_stats_alarm_policy_cfg.reporting_interval = enabled ? 9 : 0;
    policy.vendor_policy.link_stats_alarm_policy_cfg.link_quality_threshold = 23.5;
    strcpy(policy.vendor_policy.managed_client_marker, "managed-test");
    policy.steering_policy.local_steer_policy.num_sta = 1;
    address(policy.steering_policy.local_steer_policy.sta_mac[0]);
    policy.steering_policy.btm_steer_policy.num_sta = 1;
    address(policy.steering_policy.btm_steer_policy.sta_mac[0]);
    policy.steering_policy.radio_num = 1;
    auto &steer = policy.steering_policy.radio_steer_policy[0];
    address(steer.ruid); steer.steering_policy = 2; steer.channel_util_thresh = 202; steer.rssi_steering_thresh = 101;
    policy.num_bh_bss_cfg = 1;
    address(policy.bh_bss_cfg_policy[0].bssid);
    policy.bh_bss_cfg_policy[0].p1_bsta_disallowed = enabled;
    policy.bh_bss_cfg_policy[0].p2_bsta_disallowed = enabled;
    policy.def_8021q_settings.primary_vlan_id = 234;
    policy.def_8021q_settings.default_pcp = 5;
    policy.channel_scan_policy.rprt_ind_ch_scan = enabled;
    policy.unsuccessful_assoc_policy.rprt_flag = enabled;
    policy.unsuccessful_assoc_policy.max_rprt_rate = enabled ? 37 : 0;
    policy.num_qos_mgmt = 1;
    policy.qos_mgmt_policy[0].mscs_disallowed_num = 1;
    address(policy.qos_mgmt_policy[0].mac_addr_mscs_disallowed[0].sta_mac_addr);
    policy.qos_mgmt_policy[0].scs_disallowed_num = 1;
    address(policy.qos_mgmt_policy[0].mac_addr_scs_disallowed[0].sta_mac_addr);
    webconfig_external_easymesh_t proto{&policy};
    webconfig_subdoc_data_t data{};
    data.u.decoded.external_protos = &proto;
    assert(translate_policy_cfg_object_from_easymesh_to_em_cfg(&data) == webconfig_error_none);
    auto *document = cJSON_CreateObject();
    assert(encode_em_config_object(&data.u.decoded.em_config, document) == webconfig_error_none);
    auto &output = (*document)["Policy"];
    assert(output.fields.size() == 9);
    auto &alarm = output["Algorithm Run Policy"];
    assert(alarm["Collection Start Time"].text == "2030-01-01T00:00:00Z");
    assert(alarm["Reporting Interval"].number == (enabled ? 9 : 0));
    assert(alarm["Link Quality Threshold"].number == 23.5);
    auto &metrics = output["AP Metrics Reporting Policy"];
    assert(metrics["Interval"].number == (enabled ? 7 : 0));
    assert(metrics["Managed Client Marker"].text == "managed-test");
    auto &radio_metrics = *output["Radio Specific Metrics Policy"].items.at(0);
    assert(radio_metrics.fields.size() == 7);
    assert(radio_metrics["ID"].text == "02:03:04:05:06:07");
    assert(radio_metrics["STA RCPI Threshold"].number == 100);
    assert(radio_metrics["STA RCPI Hysteresis"].number == 9);
    assert(radio_metrics["AP Utilization Threshold"].number == 201);
    for (const char *flag : {"STA Traffic Stats", "STA Link Metrics", "STA Status"}) assert(radio_metrics[flag].number == enabled);
    auto &steering = output["Steering Policies"];
    for (const char *kind : {"Local Steering Disallowed Policy", "BTM Steering Disallowed Policy"}) {
        assert((*steering[kind]["Disallowed STA"].items.at(0))["MAC"].text == "02:03:04:05:06:07");
    }
    auto &radio_steering = *steering["Radio Steering Parameters"].items.at(0);
    assert(radio_steering["ID"].text == "02:03:04:05:06:07");
    assert(radio_steering["Steering Policy"].number == 2);
    assert(radio_steering["Utilization Threshold"].number == 202);
    assert(radio_steering["RCPI Threshold"].number == 101);
    auto &backhaul = *output["Backhaul BSS Configuration Policy"].items.at(0);
    assert(backhaul["BSSID"].text == "02:03:04:05:06:07");
    assert(backhaul["Profile-1 bSTA Disallowed"].number == enabled);
    assert(backhaul["Profile-2 bSTA Disallowed"].number == enabled);
    assert(output["Channel Scan Reporting Policy"]["Report Independent Channel Scans"].number == enabled);
    assert(output["Unsuccessful Association Policy"]["Report Unsuccessful Associations"].number == enabled);
    assert(output["Unsuccessful Association Policy"]["Maximum Reporting Rate"].number == (enabled ? 37 : 0));
    auto &qos = *output["QoS Management Policy"].items.at(0);
    for (const char *kind : {"MSCS Disallowed STA List", "SCS Disallowed STA List"}) assert(qos[kind].items.at(0)->text == "02:03:04:05:06:07");
    assert(output["Default 802.1Q Settings Policy"]["Primary VLAN ID"].number == 234);
    assert(output["Default 802.1Q Settings Policy"]["Default PCP"].number == 5);
}
int main() {
    check(false);
    check(true);
    std::puts("PASS: real policy translator/encoder preserve zero intervals and disabled flags, plus every emitted policy group and value with non-default fields");
}
'''.replace('WIFI_TYPES', wifi_types).replace('TYPES', types).replace('TRANSLATOR', translator).replace('ENCODER', encoder)
with tempfile.TemporaryDirectory(prefix='agent-policy-encoding-') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                    '-x', 'c++', '-', '-o', str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
print('LIMITATION: existing translator omits traffic-separation and vendor client-filter policy; byte retention does not add encoder support.')
