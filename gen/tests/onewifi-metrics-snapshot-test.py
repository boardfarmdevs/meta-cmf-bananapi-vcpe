#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile


source = Path(sys.argv[1]).read_text()
implementations = []
for name in ("em_client_stats_clear", "handle_ready_client_stats"):
    start = source.index("static int " + name + "(")
    implementations.append(source[start:source.index("\n}\n", start) + 3])

program = r"""
#include <cassert>
#include <cstddef>
#define MAX_NUM_RADIOS 3
#define MAX_NUM_VAP_PER_RADIO 4
#define RETURN_OK 0
#define RETURN_ERR -1
#define wifi_util_dbg_print(...) ((void)0)
#define wifi_util_error_print(...) ((void)0)
enum { em_app_event_type_assoc_stats_rcpi_monitor, em_app_event_type_assoc_dev_stats_periodic };
struct hash_map_t { unsigned int count; unsigned int clients[20]; };
struct vap_cache_t { unsigned int vap_index, sta_count; hash_map_t *client_stats_map; };
struct radio_cache_t { vap_cache_t ap_data[4]; };
struct { radio_cache_t radio_report[3]; } em_ap_metrics_report_cache;
struct device_t { bool cli_Active; int cli_RSSI; unsigned int identity; };
struct sta_data_t { device_t dev_stats; int timestamp; };
struct client_assoc_data_t { size_t stat_array_size; sta_data_t assoc_stats[20]; unsigned int hit_count; bool threshold_hit[20]; };
struct policy_t { int sta_rcpi_threshold, sta_rcpi_hysteresis; };
struct policies_t { policy_t radio_metrics_policy[3]; };
struct wifi_app_t { struct { struct { struct { struct { policies_t radio_metrics_policies; } em_config; } em_data; } u; } data; };
struct wifi_mgr_t { struct { int wifi_prop; } hal_cap; };
wifi_mgr_t *get_wifimgr_obj() { static wifi_mgr_t manager{}; return &manager; }
int em_match_radio_index_to_policy_index(policies_t *, unsigned int) { return 0; }
int convert_vap_index_to_vap_array_index(int *, unsigned int vap) { return vap < 4 ? static_cast<int>(vap) : -1; }
int em_rssi_to_rcpi(int rssi) { return 2 * (rssi + 110); }
void em_sta_stats_publish(wifi_app_t *, client_assoc_data_t *, int, unsigned int) {}
void hash_map_cleanup(hash_map_t *map) { map->count = 0; }
int em_client_stats_store(unsigned int radio, unsigned int vap, int count, device_t *device, int *) {
    auto &cache = em_ap_metrics_report_cache.radio_report[radio].ap_data[vap];
    cache.sta_count = count;
    cache.client_stats_map->clients[cache.client_stats_map->count++] = device->identity;
    return RETURN_OK;
}
""" + "\n".join(implementations) + r"""
int main() {
    hash_map_t maps[3][4]{};
    for (unsigned int radio = 0; radio < 3; radio++) {
        for (unsigned int vap = 0; vap < 4; vap++) {
            maps[radio][vap] = {2, {1, 2}};
            em_ap_metrics_report_cache.radio_report[radio].ap_data[vap] = {vap, 2, &maps[radio][vap]};
        }
    }
    wifi_app_t app{};
    client_assoc_data_t snapshots[4]{};
    snapshots[0].stat_array_size = 2;
    snapshots[0].assoc_stats[0] = {{true, -50, 3}, 42};
    snapshots[0].assoc_stats[1] = {{false, -50, 4}, 42};
    assert(handle_ready_client_stats(&app, snapshots, 4, 1, 0, 0, em_app_event_type_assoc_dev_stats_periodic, 2) == 0);
    assert(maps[0][0].count == 1 && maps[0][0].clients[0] == 3);
    assert(maps[0][1].count == 2 && maps[1][0].count == 2);
    snapshots[0].stat_array_size = 0;
    assert(handle_ready_client_stats(&app, snapshots, 4, 1, 0, 0, em_app_event_type_assoc_stats_rcpi_monitor, 0) == 0);
    assert(maps[0][0].count == 1);
    assert(handle_ready_client_stats(&app, snapshots, 4, 0, 0, 0, em_app_event_type_assoc_dev_stats_periodic, 0) == 0);
    assert(maps[0][0].count == 1);
    assert(handle_ready_client_stats(&app, snapshots, 4, 1, 0, 0, em_app_event_type_assoc_dev_stats_periodic, 0) == 0);
    assert(maps[0][0].count == 0);
    assert(em_ap_metrics_report_cache.radio_report[0].ap_data[0].sta_count == 0);
    assert(maps[0][1].count == 2 && maps[1][0].count == 2);
    assert(em_client_stats_clear(3, 0) == RETURN_ERR);
    assert(em_client_stats_clear(0, 99) == RETURN_ERR);
}
"""
with tempfile.TemporaryDirectory(prefix="onewifi-snapshot-test-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-x", "c++",
                    "-", "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
print("PASS: production periodic snapshots replace stale rows, including empty VAPs, without clearing other radios or RCPI-only samples")
