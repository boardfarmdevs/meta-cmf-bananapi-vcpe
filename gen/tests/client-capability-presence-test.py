#!/usr/bin/env python3
import argparse
from pathlib import Path
import subprocess
import tempfile


parser = argparse.ArgumentParser(description="Compile native capability merging without resurrecting associations")
parser.add_argument("source_root", type=Path)
args = parser.parse_args()
source = (args.source_root / "src/em/capability/em_capability.cpp").read_text()
start = source.index("static bool merge_associated_client_capabilities(")
helper = source[start:source.index("\n}\n", start) + 3]
start = source.index("int em_capability_t::handle_client_cap_report(")
handler = source[start:source.index("\n}\n", start)]
assert "sta_info.associated = true" not in handler
assert handler.count("merge_associated_client_capabilities(dm,") == 2
assert "sizeof(sta_info.frame_body)" in handler
program = r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
using mac_addr_str_t = char[18];
using em_long_string_t = char[256];
using hash_map_t = std::map<std::string, void *>;
struct em_sta_info_t {
    unsigned char id[6] = {}, bssid[6] = {}, radiomac[6] = {};
    bool associated = false;
    unsigned int frame_body_len = 0;
    unsigned char frame_body[512] = {};
    int rcpi = 100;
    unsigned long last_conn_time = 91, assoc_start_boottime_sec = 700;
};
struct dm_sta_t {
    em_sta_info_t m_sta_info;
    explicit dm_sta_t(em_sta_info_t *value): m_sta_info(*value) {}
};
void *hash_map_get(hash_map_t *table, const char *key) {
    auto found = table->find(key);
    return found == table->end() ? nullptr : found->second;
}
void hash_map_put(hash_map_t *table, char *key, void *value) {
    (*table)[key] = value;
    free(key);
}
struct dm_easy_mesh_t {
    hash_map_t current, pending;
    hash_map_t *m_sta_map = &current, *m_sta_assoc_map = &pending;
    static void macbytes_to_string(unsigned char *mac, char *text) {
        snprintf(text, 18, "%02x:%02x:%02x:%02x:%02x:%02x", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    }
    ~dm_easy_mesh_t() {
        for (auto &entry: pending) delete static_cast<dm_sta_t *>(entry.second);
        for (auto &entry: current) delete static_cast<dm_sta_t *>(entry.second);
    }
};
''' + helper + r'''
int main() {
    const char *key = "00:00:00:00:00:00@00:00:00:00:00:00@00:00:00:00:00:00";
    dm_easy_mesh_t model;
    em_sta_info_t report;
    report.frame_body_len = 3;
    memcpy(report.frame_body, "cap", 3);
    assert(!merge_associated_client_capabilities(&model, report));
    assert(model.pending.empty());
    em_sta_info_t association;
    model.current[key] = new dm_sta_t(&association);
    assert(!merge_associated_client_capabilities(&model, report));
    auto *current = static_cast<dm_sta_t *>(model.current[key]);
    current->m_sta_info.associated = true;
    report.rcpi = 0;
    report.last_conn_time = 0;
    report.assoc_start_boottime_sec = 0;
    assert(merge_associated_client_capabilities(&model, report));
    auto *pending = static_cast<dm_sta_t *>(model.pending[key]);
    assert(pending->m_sta_info.associated);
    assert(pending->m_sta_info.rcpi == 100);
    assert(pending->m_sta_info.last_conn_time == 91);
    assert(pending->m_sta_info.assoc_start_boottime_sec == 700);
    assert(pending->m_sta_info.frame_body_len == 3);
    assert(memcmp(pending->m_sta_info.frame_body, "cap", 3) == 0);
    delete current;
    model.current.clear();
    assert(merge_associated_client_capabilities(&model, report));
    assert(model.current.empty() && model.pending.size() == 1);
    pending->m_sta_info.associated = false;
    assert(!merge_associated_client_capabilities(&model, report));
    pending->m_sta_info.associated = true;
    report.frame_body_len = 513;
    assert(!merge_associated_client_capabilities(&model, report));
    assert(pending->m_sta_info.frame_body_len == 3);
    report.frame_body_len = 3;
    report.bssid[5] = 1;
    assert(!merge_associated_client_capabilities(&model, report));
    report.bssid[5] = 0;
    report.radiomac[5] = 1;
    assert(!merge_associated_client_capabilities(&model, report));
    puts("PASS capability metadata preserves exact active ownership, metrics and age; missing/withdrawn links stay absent");
}
'''
with tempfile.TemporaryDirectory(prefix="client-capability-presence-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2",
                    "-x", "c++", "-", "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
