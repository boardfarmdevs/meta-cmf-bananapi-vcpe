"""Compile OneWifi's real AP-query dispatch, collection and report-building path."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile


native = Path(sys.argv[1])
dependencies = Path(sys.argv[2]) if len(sys.argv) > 2 else (
    Path(__file__).resolve().parent / "onewifi-query-test-deps"
)
source = (native / "source/apps/em/wifi_em.c").read_text()
header = (native / "include/wifi_base.h").read_text()


def function(signature):
    return re.search(re.escape(signature) + r"\([^;]*?\)\s*\{.*?\n\}", source, re.S).group()


def structure(contents, name):
    return re.search(r"typedef struct \{(?:(?!typedef struct).)*?\} " + name + ";",
                     contents, re.S).group()


types = "\n".join(structure(header, name) for name in (
    "radio_metrics_policy_t", "radio_metrics_policies_t",
    "assoc_sta_link_metrics_data_t", "assoc_sta_link_metrics_t", "error_code_t",
    "assoc_sta_ext_link_metrics_data_t", "assoc_sta_ext_link_metrics_t", "per_sta_metrics_t",
    "assoc_sta_traffic_stats_t", "ap_metrics_t", "radio_metrics_t", "em_vap_metrics_t",
    "em_per_radio_report_t", "em_ap_metrics_report_t",
))
cache_types = "\n".join(structure(source, name) for name in (
    "em_ap_report_callback_arg_t", "wifi_associated_dev3_timestamp_t", "ap_metrics_data_t",
    "em_ap_radio_report_t", "em_ap_metrics_report_cache_t",
))
dispatch = function("void handle_em_command_event")
query_case = dispatch.split("    case wifi_event_type_em_ap_metrics_query:", 1)[1].split(
    "    case wifi_event_type_notify_monitor_done:", 1
)[0]
query_helpers = "\n".join(function(signature) for signature in (
    "static int em_ap_query_bssids", "static int em_refresh_ap_survey",
    "static int em_refresh_ap_clients", "static int em_handle_ap_metrics_query",
) if signature + "(" in source)
production = "\n".join((
    function("static int em_rssi_to_rcpi"),
    function("static int em_get_radio_index_from_mac"),
    function("int em_client_stats_store"),
    function("static int em_client_stats_clear"),
    function("static int prepare_sta_traffic_stats_data"),
    function("static int prepare_sta_lins_metrics_data"),
    function("static int ap_report_push_cb"),
    query_helpers,
    "void handle_em_command_event(wifi_app_t *app, wifi_event_t *event) {\n"
    "switch (event->sub_type) {\ncase wifi_event_type_em_ap_metrics_query:" + query_case +
    "default: assert(false);\n}\n}",
    function("static bus_error_t em_request_ap_metrics"),
))
program = r"""
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "cJSON.h"
#define MAX_NUM_RADIOS 4
#define MAX_NUM_VAP_PER_RADIO 4
#define EM_MAX_RADIO_POLICY 4
#define STA_MAX_BSS_ASSOCIATIONS 4
#define BSS_MAX_NUM_STATIONS 128
#define RETURN_OK 0
#define RETURN_ERR -1
#define TRUE 1
#define FALSE 0
#define WIFI_EM_AP_METRICS_REPORT "Device.WiFi.EM.APMetricsReport"
#define wifi_util_error_print(...) ((void)0)
#define wifi_util_info_print(...) ((void)0)
#define wifi_util_dbg_print(...) ((void)0)
typedef unsigned char mac_addr_t[6];
typedef unsigned char mac_address_t[6];
typedef unsigned char bssid_t[6];
typedef char mac_addr_str_t[18];
typedef unsigned int UINT;
typedef int INT;
typedef unsigned long ULONG;
typedef int em_policy_req_type_t;
typedef int bus_error_t;
enum {em_ap_metrics_only, em_ap_metrics_link, em_ap_metrics_traffic, em_ap_metrics_link_and_traffic};
enum {wifi_event_type_command, wifi_event_type_em_ap_metrics_query,
      bus_data_type_string, bus_error_success, bus_error_invalid_input, bus_error_general,
      webconfig_subdoc_type_em_ap_metrics_report, webconfig_error_none,
      wifi_vap_mode_ap, wifi_vap_mode_sta};
PRODUCTION_TYPES
typedef struct {
    struct {int interval;} ap_metric_policy;
    radio_metrics_policies_t radio_metrics_policies;
} em_config_t;
typedef struct {int handle; int webconfig; void *sched;} wifi_ctrl_t;
typedef struct {
    wifi_ctrl_t *ctrl;
    struct {struct {struct {em_config_t em_config;} em_data;} u;} data;
} wifi_app_t;
typedef struct {
    unsigned int vap_index;
    unsigned int radio_index;
    int vap_mode;
    bool enabled;
    union {struct {bssid_t bssid; bool enabled;} bss_info;} u;
} wifi_vap_info_t;
typedef struct {unsigned int num_vaps; wifi_vap_info_t vap_array[MAX_NUM_VAP_PER_RADIO];} wifi_vap_info_map_t;
typedef struct {
    struct {unsigned int channel;} oper;
    struct {unsigned int num_vaps; wifi_vap_info_map_t vap_map;} vaps;
} rdk_wifi_radio_t;
typedef struct {int radio_index; char interface_name[32];} radio_interface_mapping_t;
typedef struct {radio_interface_mapping_t radio_interface_map[MAX_NUM_RADIOS];} wifi_platform_property_t;
typedef struct {
    rdk_wifi_radio_t radio_config[MAX_NUM_RADIOS];
    struct {wifi_platform_property_t wifi_prop;} hal_cap;
} wifi_mgr_t;
typedef struct {
    mac_addr_t cli_MACAddress;
    bool cli_Active;
    int cli_RSSI;
    unsigned int cli_LastDataDownlinkRate, cli_LastDataUplinkRate;
    unsigned long cli_BytesSent, cli_BytesReceived, cli_PacketsSent, cli_PacketsReceived;
    unsigned long cli_ErrorsSent, cli_RxErrors, cli_RetransCount;
} wifi_associated_dev3_t;
typedef struct {unsigned int count; char *keys[128]; void *rows[128];} hash_map_t;
typedef struct {char client_type[32];} sta_client_info_t;
PRODUCTION_CACHE_TYPES
static em_ap_metrics_report_cache_t em_ap_metrics_report_cache;
static struct {struct {hash_map_t *client_type_map;} sta_client_type;} client_type_info;
typedef struct {
    int data_type;
    struct {void *bytes;} raw_data;
    size_t raw_data_len;
} raw_data_t;
typedef struct {int sub_type; struct {struct {char *msg; size_t len;} core_data;} u;} wifi_event_t;
typedef struct {
    unsigned int ch_number;
    bool ch_in_pool;
    int ch_noise;
    uint64_t ch_utilization_total, ch_utilization_busy, ch_utilization_busy_tx;
    uint64_t ch_utilization_busy_rx, ch_utilization_busy_self;
} wifi_channelStats_t;
typedef wifi_channelStats_t radio_chan_data_t;
typedef struct {struct {int radio_index;} args; void *stat_pointer; size_t stat_array_size;} wifi_provider_response_t;
typedef struct {
    int type;
    struct {
        struct {
            em_ap_metrics_report_t em_ap_metrics_report;
            rdk_wifi_radio_t radios[MAX_NUM_RADIOS];
            __typeof__(((wifi_mgr_t *)0)->hal_cap) hal_cap;
        } decoded;
        struct {char *raw;} encoded;
    } u;
} webconfig_subdoc_data_t;
static wifi_mgr_t manager;
static wifi_ctrl_t controller;
static wifi_app_t application;
static uint64_t now_ms = 100000;
static unsigned int radio_count = 2;
static int failed_survey = -1, failed_clients = -1, failed_mapping = -1, clock_failure;
static bool hal_null_rows, hal_overflow;
static unsigned int survey_calls[MAX_NUM_RADIOS], client_calls[16], publications;
static wifi_associated_dev3_t hal_clients[16][4];
static unsigned int hal_counts[16];
static cJSON *published;
static char pending_query[4097];
static struct timespec last_sample[16];
static int test_clock(clockid_t identifier, struct timespec *result) {
    assert(identifier == CLOCK_MONOTONIC);
    result->tv_sec = now_ms / 1000;
    result->tv_nsec = (now_ms % 1000) * 1000000;
    return clock_failure;
}
#define clock_gettime test_clock
static wifi_mgr_t *get_wifimgr_obj(void) {return &manager;}
static wifi_ctrl_t *get_wifictrl_obj(void) {return &controller;}
static unsigned int getNumberRadios(void) {return radio_count;}
static rdk_wifi_radio_t *find_radio_config_by_index(int index) {
    return index >= 0 && (unsigned int)index < radio_count ? &manager.radio_config[index] : NULL;
}
static wifi_vap_info_t *getVapInfo(unsigned int vap_index) {
    for (unsigned int radio = 0; radio < radio_count; ++radio)
        for (unsigned int vap = 0; vap < manager.radio_config[radio].vaps.num_vaps; ++vap)
            if (manager.radio_config[radio].vaps.vap_map.vap_array[vap].vap_index == vap_index)
                return &manager.radio_config[radio].vaps.vap_map.vap_array[vap];
    return NULL;
}
static void *get_wifidb_vap_map(unsigned int radio) {return &manager.radio_config[radio].vaps.vap_map;}
static bool isVapSTAMesh(unsigned int vap) {return getVapInfo(vap)->vap_mode == wifi_vap_mode_sta;}
static void to_mac_str(const unsigned char *mac, char *output) {
    snprintf(output, 18, "%02x:%02x:%02x:%02x:%02x:%02x", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}
static int mac_address_from_name(const char *name, mac_addr_t mac) {
    for (unsigned int radio = 0; radio < radio_count; ++radio) {
        if (strcmp(manager.hal_cap.wifi_prop.radio_interface_map[radio].interface_name, name) == 0) {
            if ((int)radio == failed_mapping) return RETURN_ERR;
            memset(mac, 0, 6);
            mac[0] = 2;
            mac[5] = radio + 1;
            return RETURN_OK;
        }
    }
    return RETURN_ERR;
}
static hash_map_t *hash_map_create(void) {return calloc(1, sizeof(hash_map_t));}
static void *hash_map_get(hash_map_t *map, const char *key) {
    if (map != NULL)
        for (unsigned int index = 0; index < map->count; ++index)
            if (strcmp(map->keys[index], key) == 0) return map->rows[index];
    return NULL;
}
static void hash_map_put(hash_map_t *map, char *key, void *row) {
    assert(map != NULL && map->count < 128);
    map->keys[map->count] = key;
    map->rows[map->count++] = row;
}
static void hash_map_cleanup(hash_map_t *map) {
    assert(map != NULL);
    for (unsigned int index = 0; index < map->count; ++index) {
        free(map->keys[index]);
        free(map->rows[index]);
    }
    map->count = 0;
}
static unsigned int hash_map_count(hash_map_t *map) {return map == NULL ? 0 : map->count;}
static void *hash_map_get_first(hash_map_t *map) {return hash_map_count(map) ? map->rows[0] : NULL;}
static void *hash_map_get_next(hash_map_t *map, void *row) {
    for (unsigned int index = 0; index + 1 < map->count; ++index)
        if (map->rows[index] == row) return map->rows[index + 1];
    return NULL;
}
static int wifi_getRadioChannelStats(int radio, wifi_channelStats_t *sample, int count) {
    assert(radio >= 0 && (unsigned int)radio < radio_count && count == 1);
    ++survey_calls[radio];
    now_ms += 17;
    if (radio == failed_survey) return RETURN_ERR;
    sample->ch_utilization_total = 10000 * survey_calls[radio];
    sample->ch_utilization_busy = (radio + 1) * 1000 * survey_calls[radio];
    sample->ch_noise = -95;
    return RETURN_OK;
}
static int radio_chan_stats_response(wifi_provider_response_t *response) {
    const unsigned int radio = response->args.radio_index;
    const radio_chan_data_t *sample = response->stat_pointer;
    assert(response->stat_array_size == 1 && sample->ch_utilization_total > 0);
    em_ap_metrics_report_cache.radio_report[radio].radio_metrics.ruid[0] = 2;
    em_ap_metrics_report_cache.radio_report[radio].radio_metrics.ruid[5] = radio + 1;
    for (unsigned int vap = 0; vap < manager.radio_config[radio].vaps.num_vaps; ++vap)
        em_ap_metrics_report_cache.radio_report[radio].ap_data[vap].ap_metrics.channel_util =
            sample->ch_utilization_busy * 255 / sample->ch_utilization_total;
    return RETURN_OK;
}
static int wifi_getApAssociatedDeviceDiagnosticResult3(INT vap, wifi_associated_dev3_t **rows, UINT *count) {
    assert(vap >= 0 && vap < 16 && getVapInfo(vap) != NULL && !isVapSTAMesh(vap));
    ++client_calls[vap];
    assert(test_clock(CLOCK_MONOTONIC, &last_sample[vap]) == clock_failure);
    now_ms += 23;
    *rows = NULL;
    *count = 0;
    if (vap == failed_clients) return RETURN_ERR;
    if (hal_null_rows || hal_overflow) {
        *count = hal_overflow ? BSS_MAX_NUM_STATIONS + 1 : 1;
        return RETURN_OK;
    }
    *count = hal_counts[vap];
    if (*count != 0) {
        *rows = malloc(*count * sizeof(**rows));
        assert(*rows != NULL);
        memcpy(*rows, hal_clients[vap], *count * sizeof(**rows));
    }
    return RETURN_OK;
}
#define wifi_hal_getApAssociatedDeviceDiagnosticResult3 wifi_getApAssociatedDeviceDiagnosticResult3
static int webconfig_encode(void *config, webconfig_subdoc_data_t *data, int type) {
    assert(type == webconfig_subdoc_type_em_ap_metrics_report);
    const em_ap_metrics_report_t *report = &data->u.decoded.em_ap_metrics_report;
    assert(report->radio_count > 0 && report->radio_count <= MAX_NUM_RADIOS);
    cJSON *document = cJSON_CreateObject();
    cJSON *radios = cJSON_AddArrayToObject(document, "radios");
    for (int radio = 0; radio < report->radio_count; ++radio) {
        const em_per_radio_report_t *entry = &report->radio_reports[radio];
        cJSON *encoded_radio = cJSON_CreateObject();
        cJSON_AddItemToArray(radios, encoded_radio);
        cJSON_AddNumberToObject(encoded_radio, "radio", entry->radio_index);
        cJSON *vaps = cJSON_AddArrayToObject(encoded_radio, "vaps");
        for (unsigned int vap = 0; vap < MAX_NUM_VAP_PER_RADIO; ++vap) {
            const em_vap_metrics_t *metrics = &entry->vap_reports[vap];
            if (memcmp(metrics->vap_metrics.bssid, (unsigned char[6]){0}, 6) == 0) continue;
            cJSON *encoded_vap = cJSON_CreateObject();
            cJSON_AddItemToArray(vaps, encoded_vap);
            char address[18];
            to_mac_str(metrics->vap_metrics.bssid, address);
            cJSON_AddStringToObject(encoded_vap, "bssid", address);
            cJSON_AddNumberToObject(encoded_vap, "count", metrics->sta_cnt);
            cJSON_AddNumberToObject(encoded_vap, "ap_count", metrics->vap_metrics.num_of_assoc_stas);
            cJSON_AddNumberToObject(encoded_vap, "util", metrics->vap_metrics.channel_util);
            cJSON_AddBoolToObject(encoded_vap, "links", metrics->is_sta_link_metrics_enabled);
            cJSON *clients = cJSON_AddArrayToObject(encoded_vap, "clients");
            if (metrics->is_sta_link_metrics_enabled) {
                for (int station = 0; station < metrics->sta_cnt; ++station) {
                    assert(metrics->sta_link_metrics != NULL);
                    const per_sta_metrics_t *row = &metrics->sta_link_metrics[station];
                    const assoc_sta_link_metrics_data_t *link = &row->assoc_sta_link_metrics.assoc_sta_link_metrics_data[0];
                    assert(row->assoc_sta_link_metrics.num_bssid == 1);
                    assert(memcmp(link->bssid, metrics->vap_metrics.bssid, 6) == 0);
                    cJSON *client = cJSON_CreateObject();
                    cJSON_AddItemToArray(clients, client);
                    to_mac_str(row->sta_mac, address);
                    cJSON_AddStringToObject(client, "mac", address);
                    cJSON_AddNumberToObject(client, "rcpi", link->rcpi);
                    cJSON_AddNumberToObject(client, "age", link->time_delta);
                    cJSON_AddNumberToObject(client, "down", link->est_mac_rate_down);
                }
            }
        }
    }
    data->u.encoded.raw = cJSON_PrintUnformatted(document);
    cJSON_Delete(document);
    return webconfig_error_none;
}
static int publish(int *handle, const char *event, raw_data_t *data) {
    assert(handle == &controller.handle && strcmp(event, WIFI_EM_AP_METRICS_REPORT) == 0);
    assert(data->data_type == bus_data_type_string);
    assert(data->raw_data_len == strlen(data->raw_data.bytes) + 1);
    cJSON_Delete(published);
    published = cJSON_Parse(data->raw_data.bytes);
    assert(published != NULL);
    ++publications;
    return bus_error_success;
}
static struct {int (*bus_event_publish_fn)(int *, const char *, raw_data_t *);} bus = {publish};
static __typeof__(bus) *get_bus_descriptor(void) {return &bus;}
static int push_event_to_ctrl_queue(void *data, size_t length, int type, int subtype, void *route) {
    assert(type == wifi_event_type_command && subtype == wifi_event_type_em_ap_metrics_query);
    assert(length > 0 && length <= sizeof(pending_query));
    memcpy(pending_query, data, length);
    assert(pending_query[length - 1] == 0);
    return RETURN_OK;
}
PRODUCTION_FUNCTIONS
static void setup(void) {
    application.ctrl = &controller;
    for (unsigned int radio = 0; radio < radio_count; ++radio) {
        rdk_wifi_radio_t *config = &manager.radio_config[radio];
        config->oper.channel = radio == 0 ? 6 : 36;
        config->vaps.num_vaps = 2;
        config->vaps.vap_map.num_vaps = 2;
        manager.hal_cap.wifi_prop.radio_interface_map[radio].radio_index = radio;
        snprintf(manager.hal_cap.wifi_prop.radio_interface_map[radio].interface_name, 32, "radio%u", radio);
        for (unsigned int vap = 0; vap < MAX_NUM_VAP_PER_RADIO; ++vap) {
            ap_metrics_data_t *cached = &em_ap_metrics_report_cache.radio_report[radio].ap_data[vap];
            cached->client_stats_map = hash_map_create();
            cached->vap_index = radio * 4 + vap;
            wifi_vap_info_t *info = &config->vaps.vap_map.vap_array[vap];
            info->vap_index = radio * 4 + vap;
            info->radio_index = radio;
            info->vap_mode = vap == 0 ? wifi_vap_mode_ap : wifi_vap_mode_sta;
            info->enabled = info->u.bss_info.enabled = true;
            info->u.bss_info.bssid[0] = 2;
            info->u.bss_info.bssid[5] = 0x10 + info->vap_index;
        }
    }
}
static void associate(unsigned int vap, unsigned int slot, unsigned int identity, int rssi, bool active) {
    wifi_associated_dev3_t *row = &hal_clients[vap][slot];
    memset(row, 0, sizeof(*row));
    row->cli_MACAddress[0] = 2;
    row->cli_MACAddress[5] = identity;
    row->cli_Active = active;
    row->cli_RSSI = rssi;
    row->cli_LastDataDownlinkRate = 54000 + identity;
    row->cli_LastDataUplinkRate = 24000 + identity;
    if (hal_counts[vap] < slot + 1) hal_counts[vap] = slot + 1;
}
static void dispatch(const char *encoded) {
    raw_data_t data = {bus_data_type_string, {(void *)encoded}, strlen(encoded) + 1};
    assert(em_request_ap_metrics(NULL, &data, NULL) == bus_error_success);
    assert(strcmp(pending_query, encoded) == 0);
    wifi_event_t event = {wifi_event_type_em_ap_metrics_query, {{pending_query, strlen(pending_query) + 1}}};
    unsigned int before = publications;
    handle_em_command_event(&application, &event);
    if (publications > before) {
        const cJSON *echo = cJSON_GetObjectItemCaseSensitive(published, "APMetricsQuery");
        assert(cJSON_IsString(echo) && strcmp(echo->valuestring, encoded) == 0);
    }
}
static void query(unsigned short mid) {
    char encoded[128];
    snprintf(encoded, sizeof(encoded),
        "020000000002020000000001893a0000800b%04x008093000d02020000000010020000000014000000", mid);
    dispatch(encoded);
}
static cJSON *vap_report(unsigned int wanted_radio) {
    cJSON *radios = cJSON_GetObjectItemCaseSensitive(published, "radios");
    cJSON *radio = NULL;
    cJSON_ArrayForEach(radio, radios) {
        if (cJSON_GetObjectItemCaseSensitive(radio, "radio")->valueint == (int)wanted_radio) {
            cJSON *vaps = cJSON_GetObjectItemCaseSensitive(radio, "vaps");
            cJSON *vap = NULL;
            char bssid[18];
            to_mac_str(getVapInfo(wanted_radio * 4)->u.bss_info.bssid, bssid);
            cJSON_ArrayForEach(vap, vaps)
                if (strcmp(cJSON_GetObjectItemCaseSensitive(vap, "bssid")->valuestring, bssid) == 0)
                    return vap;
        }
    }
    assert(!"requested AP missing from published report");
    return NULL;
}
static void check_clients(unsigned int radio, int count, unsigned int identity, int rssi) {
    cJSON *vap = vap_report(radio);
    assert(cJSON_GetObjectItemCaseSensitive(vap, "count")->valueint == count);
    assert(cJSON_GetObjectItemCaseSensitive(vap, "ap_count")->valueint == count);
    assert(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(vap, "links")));
    assert(cJSON_GetObjectItemCaseSensitive(vap, "util")->valueint == (int)((radio + 1) * 255 / 10));
    cJSON *clients = cJSON_GetObjectItemCaseSensitive(vap, "clients");
    assert(cJSON_GetArraySize(clients) == count);
    if (count) {
        cJSON *client = cJSON_GetArrayItem(clients, 0);
        char address[18];
        unsigned char mac[6] = {2,0,0,0,0,identity};
        to_mac_str(mac, address);
        assert(strcmp(cJSON_GetObjectItemCaseSensitive(client, "mac")->valuestring, address) == 0);
        assert(cJSON_GetObjectItemCaseSensitive(client, "rcpi")->valueint == em_rssi_to_rcpi(rssi));
        assert(cJSON_GetObjectItemCaseSensitive(client, "down")->valueint == (int)(54000 + identity));
        double age = cJSON_GetObjectItemCaseSensitive(client, "age")->valuedouble;
        uint64_t collected = last_sample[radio * 4].tv_sec * 1000 + last_sample[radio * 4].tv_nsec / 1000000;
        assert(age >= now_ms - collected && age < 1000);
    }
}
int main(int count, char **arguments) {
    assert(count == 2);
    setup();
    associate(0, 0, 0xa1, -71, true);
    associate(4, 0, 0xb1, -43, true);
    associate(4, 1, 0xb2, -25, false);
    if (strcmp(arguments[1], "cold") == 0) {
        assert(em_ap_metrics_report_cache.args.app == NULL);
        assert(em_ap_metrics_report_cache.args.policy_config.radio_metrics_policies.radio_count == 0);
        for (unsigned int radio = 0; radio < radio_count; ++radio) {
            free(em_ap_metrics_report_cache.radio_report[radio].ap_data[0].client_stats_map);
            em_ap_metrics_report_cache.radio_report[radio].ap_data[0].client_stats_map = NULL;
        }
        query(0);
        assert(publications == 1 && "cold native AP query must publish without periodic policy");
        assert(survey_calls[0] == 1 && survey_calls[1] == 1);
        assert(client_calls[0] == 1 && client_calls[4] == 1);
        check_clients(0, 1, 0xa1, -71);
        check_clients(1, 1, 0xb1, -43);
        assert(em_ap_metrics_report_cache.args.app == NULL);
        assert(em_ap_metrics_report_cache.args.policy_config.radio_metrics_policies.radio_count == 0);
        puts("PASS: cold query MID zero reaches HAL and publishes real BSTA RCPI on both radios without installing policy");
    } else if (strcmp(arguments[1], "interval-zero") == 0) {
        em_ap_metrics_report_cache.args.app = &application;
        em_ap_metrics_report_cache.args.sched_id = 0;
        em_ap_metrics_report_cache.args.current_interval = 0;
        query(65535);
        assert(publications == 1);
        check_clients(0, 1, 0xa1, -71);
        check_clients(1, 1, 0xb1, -43);
        assert(em_ap_metrics_report_cache.args.sched_id == 0);
        assert(em_ap_metrics_report_cache.args.current_interval == 0);
        puts("PASS: interval-zero request with no cached radio policy publishes correlated MID 65535");
    } else if (strcmp(arguments[1], "replace-empty") == 0) {
        query(10);
        assert(publications == 1);
        now_ms += 5000;
        hal_counts[0] = 0;
        hal_counts[4] = 0;
        associate(4, 0, 0xc1, -57, true);
        query(11);
        assert(publications == 2 && client_calls[0] == 2 && client_calls[4] == 2);
        check_clients(0, 0, 0, 0);
        check_clients(1, 1, 0xc1, -57);
        hal_counts[4] = 0;
        query(12);
        assert(publications == 3);
        check_clients(0, 0, 0, 0);
        check_clients(1, 0, 0, 0);
        puts("PASS: each query replaces authoritative HAL rows, drops stale clients and publishes genuinely empty APs");
    } else if (strcmp(arguments[1], "failures") == 0) {
        query(20);
        assert(publications == 1);
        failed_clients = 4;
        query(21);
        assert(publications == 1 && "client HAL failure cannot publish cached rows as fresh");
        failed_clients = -1;
        failed_survey = 0;
        query(22);
        assert(publications == 1 && "survey failure cannot publish cached survey as fresh");
        failed_survey = -1;
        query(23);
        assert(publications == 2);
        check_clients(1, 1, 0xb1, -43);
        puts("PASS: failed survey/client collections do not fabricate a response; subsequent query recovers");
    } else if (strcmp(arguments[1], "selection-policy") == 0) {
        em_ap_metrics_report_cache.args.app = &application;
        em_ap_metrics_report_cache.args.sched_id = 77;
        em_ap_metrics_report_cache.args.current_interval = 12;
        em_ap_metrics_report_cache.args.policy_config.ap_metric_policy.interval = 12;
        em_ap_metrics_report_cache.args.policy_config.radio_metrics_policies.radio_count = 1;
        radio_metrics_policy_t *policy = &em_ap_metrics_report_cache.args.policy_config.radio_metrics_policies.radio_metrics_policy[0];
        policy->ruid[0] = 2;
        policy->ruid[5] = 1;
        policy->ap_util_threshold = 99;
        policy->link_metrics = false;
        policy->traffic_stats = true;
        em_ap_report_callback_arg_t saved = em_ap_metrics_report_cache.args;
        failed_survey = 0;
        failed_clients = 0;
        dispatch("020000000002020000000001893a0000800b0101008093000701020000000014000000");
        assert(publications == 1 && "unrequested broken radio must not block selected radio");
        assert(survey_calls[0] == 0 && survey_calls[1] == 1);
        assert(client_calls[0] == 0 && client_calls[4] == 1);
        assert(cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(published, "radios")) == 1);
        check_clients(1, 1, 0xb1, -43);
        assert(memcmp(&saved, &em_ap_metrics_report_cache.args, sizeof(saved)) == 0);
        puts("PASS: native requested-BSSID selection ignores unrelated policy/failing radio and preserves periodic configuration");
    } else if (strcmp(arguments[1], "invalid") == 0) {
        dispatch("020000000002020000000001893a0000800b0101008093000701020000000099000000");
        assert(publications == 0 && survey_calls[0] == 0 && survey_calls[1] == 0);
        dispatch("020000000002020000000001893a0000800b0101008093000702020000000014000000");
        assert(publications == 0 && client_calls[4] == 0);
        dispatch("020000000002020000000001893a0000800b0101008093000701020000000014000001");
        assert(publications == 0 && survey_calls[1] == 0);
        puts("PASS: unknown BSSID and malformed count/EOM produce no HAL request or fabricated report");
    } else if (strcmp(arguments[1], "all-bounded") == 0) {
        dispatch("020000000002020000000001893a0000800b0001008093000100000000");
        assert(publications == 1 && survey_calls[0] == 1 && survey_calls[1] == 1);
        check_clients(0, 1, 0xa1, -71);
        check_clients(1, 1, 0xb1, -43);
        char maximum[4097] = "020000000002020000000001893a0000800b000200809305fbff";
        size_t position = strlen(maximum);
        for (unsigned int index = 0; index < 255; ++index) {
            int written = snprintf(maximum + position, sizeof(maximum) - position,
                "02000000%02x%02x", index / 256, index % 256);
            assert(written == 12);
            position += written;
        }
        memcpy(maximum + position, "000000", 7);
        dispatch(maximum);
        assert(publications == 2 && survey_calls[0] == 2 && survey_calls[1] == 2);
        check_clients(0, 1, 0xa1, -71);
        check_clients(1, 1, 0xb1, -43);
        puts("PASS: zero-BSSID query selects all AP radios and 255-BSSID query stays bounded and collects each radio once");
    } else if (strcmp(arguments[1], "clock-hal-validation") == 0) {
        clock_failure = -1;
        query(30);
        assert(publications == 0 && client_calls[0] == 0 && client_calls[4] == 0);
        clock_failure = 0;
        hal_null_rows = true;
        query(31);
        assert(publications == 0);
        hal_null_rows = false;
        hal_overflow = true;
        query(32);
        assert(publications == 0);
        hal_overflow = false;
        failed_mapping = 0;
        query(33);
        assert(publications == 0);
        failed_mapping = -1;
        query(34);
        assert(publications == 1);
        check_clients(0, 1, 0xa1, -71);
        puts("PASS: missing sample clock, NULL nonempty HAL data, oversized HAL count and unmapped RUID fail closed then recover");
    } else assert(false);
    return 0;
}
""".replace("PRODUCTION_TYPES", types).replace("PRODUCTION_CACHE_TYPES", cache_types).replace(
    "PRODUCTION_FUNCTIONS", production
)

with tempfile.TemporaryDirectory(prefix="onewifi-ap-query-") as temporary:
    executable = Path(temporary) / "test"
    (Path(temporary) / "libcjson.so.1").symlink_to((dependencies / "libcjson.so").resolve())
    subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                    "-Wno-unused-function", "-Wno-unused-variable", "-Wno-sign-compare",
                    "-Wno-pointer-sign", "-x", "c", "-",
                    "-I", str(dependencies), "-x", "none", str(dependencies / "libcjson.so"),
                    "-Wl,-rpath," + temporary, "-o", str(executable)],
                   input=program, text=True, check=True)
    failed = []
    for scenario in ("cold", "interval-zero", "replace-empty", "failures", "selection-policy", "invalid",
                     "all-bounded", "clock-hal-validation"):
        result = subprocess.run([str(executable), scenario], text=True)
        if result.returncode != 0:
            failed.append(scenario)
            print(f"FAIL: {scenario} exits {result.returncode}", flush=True)
    if failed:
        raise SystemExit("FAIL: " + ", ".join(failed))
