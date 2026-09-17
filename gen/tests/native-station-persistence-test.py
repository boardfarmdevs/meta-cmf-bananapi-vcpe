from pathlib import Path
import subprocess
import sys
import tempfile


root = Path(sys.argv[1])
station_source = (root / "src/dm/dm_sta_list.cpp").read_text()
controller_source = (root / "src/ctrl/dm_easy_mesh_ctrl.cpp").read_text()
update = station_source[station_source.index("void dm_sta_list_t::update_list("):station_source.index("void dm_sta_list_t::delete_list(")]
configure = station_source[station_source.index("int dm_sta_list_t::set_config(db_client_t& db_client, dm_sta_t& sta"):station_source.index("dm_orch_type_t dm_sta_list_t::get_dm_orch_type(")]
begin = controller_source.index("int dm_easy_mesh_ctrl_t::update_tables(")
start = controller_source.index("    if (dm->db_cfg_type_is_set(db_cfg_type_sta_list_update))", begin)
lock = controller_source.find("    std::unique_lock<std::recursive_mutex> station_lock", begin, start)
if lock != -1:
    start = lock
end = controller_source.index("    if (dm->db_cfg_type_is_set(db_cfg_type_network_ssid_list_update))", start)
transaction = controller_source[start:end]
program = r'''
#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <future>
#include <iostream>
#include <mutex>
#include <thread>
#define em_printfout(...) (void)0
using mac_addr_str_t = char[18];
using em_long_string_t = char[128];
using em_2xlong_string_t = char[256];
using mac_address_t = unsigned char[6];
using db_client_t = int;
enum dm_orch_type_t {dm_orch_type_db_insert, dm_orch_type_db_update, dm_orch_type_db_delete};
enum {db_cfg_type_sta_list_update, db_cfg_type_sta_list_delete, db_cfg_type_sta_metrics_update};
struct em_sta_info_t {
    mac_address_t id{2}, bssid{4}, radiomac{6};
    bool associated = true;
    unsigned int counter = 0;
};
struct dm_sta_t {
    em_sta_info_t m_sta_info;
    em_sta_info_t *get_sta_info() {return &m_sta_info;}
};
struct dm_easy_mesh_t {
    void *m_sta_assoc_map = nullptr;
    void *m_sta_dassoc_map = nullptr;
    void *m_sta_map = nullptr;
    bool metrics = true;
    bool db_cfg_type_is_set(int kind) {return kind == db_cfg_type_sta_metrics_update && metrics;}
    char *db_cfg_type_get_criteria(int) {return nullptr;}
    void reset_db_cfg_type(int) {metrics = false;}
    static void macbytes_to_string(unsigned char *address, char *output) {
        snprintf(output, 18, "%02x:%02x:%02x:%02x:%02x:%02x", address[0], address[1],
            address[2], address[3], address[4], address[5]);
    }
};
void *hash_map_get_first(void *map) {return map;}
void *hash_map_get_next(void *, void *) {return nullptr;}
void hash_map_remove(void *, const char *) {}
std::recursive_mutex g_network_topology_mutex;
std::atomic<dm_sta_t *> current{nullptr};
std::atomic<bool> removed{false};
bool removed_before_commit = false;
std::promise<void> persistence_started;
std::promise<void> removal_attempted;
auto attempted = removal_attempted.get_future();
unsigned int inserted = 0;
class dm_sta_list_t {
public:
    dm_sta_t *get_sta(const char *) {return current.load();}
    void put_sta(const char *, const dm_sta_t *) {++inserted;}
    void remove_sta(const char *) {current = nullptr;}
    void enforce_single_assoc(db_client_t &, dm_sta_t &) {}
    dm_orch_type_t get_dm_orch_type(db_client_t &, const dm_sta_t &) {
        return current.load() ? dm_orch_type_db_update : dm_orch_type_db_insert;
    }
    int update_db(db_client_t &, dm_orch_type_t, em_sta_info_t *) {
        persistence_started.set_value();
        attempted.wait();
        removed_before_commit = removed.load();
        return 0;
    }
    int set_config(db_client_t &, dm_sta_t &, void *);
    void update_list(const dm_sta_t &, dm_orch_type_t);
};
CONFIGURE
UPDATE
class dm_easy_mesh_ctrl_t : public dm_sta_list_t {
public:
    db_client_t m_db_client = 0;
    void persist(dm_easy_mesh_t *dm) {
        dm_sta_t *sta, *tmp;
        mac_addr_str_t sta_mac_str, bssid_str, radio_mac_str;
        em_2xlong_string_t key;
        char *criteria;
        bool sta_topology_changed = false;
TRANSACTION
    }
};
int main() {
    dm_easy_mesh_ctrl_t controller;
    dm_sta_t incoming;
    incoming.m_sta_info.counter = 53;
    controller.update_list(incoming, dm_orch_type_db_update);
    assert(current.load() == nullptr && inserted == 0);
    dm_sta_t stored;
    current = &stored;
    dm_easy_mesh_t model;
    model.m_sta_map = &incoming;
    auto started = persistence_started.get_future();
    std::thread departure([&] {
        started.wait();
        if (g_network_topology_mutex.try_lock()) {
            removed = true;
            current = nullptr;
            g_network_topology_mutex.unlock();
            removal_attempted.set_value();
        } else {
            removal_attempted.set_value();
            std::lock_guard<std::recursive_mutex> lock(g_network_topology_mutex);
            removed = true;
            current = nullptr;
        }
    });
    controller.persist(&model);
    departure.join();
    assert(!removed_before_commit);
    assert(stored.m_sta_info.counter == 53);
    assert(removed && current.load() == nullptr && inserted == 0);
    assert(!model.metrics);
    assert(g_network_topology_mutex.try_lock());
    g_network_topology_mutex.unlock();
    std::cout << "PASS: actual station persistence serializes lookup/DB/map commit against departure, releases the topology lock, and never resurrects an absent update\n";
}
'''.replace("CONFIGURE", configure).replace("UPDATE", update).replace("TRANSACTION", transaction)
with tempfile.TemporaryDirectory(prefix="native-station-persistence-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
                    "-Wno-unused-parameter", "-Wno-unused-but-set-variable", "-x", "c++",
                    "-", "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True, timeout=10)
