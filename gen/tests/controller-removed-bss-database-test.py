#!/usr/bin/env python3
"""A BSS row the model removes leaves the database, also its radio's last (0251).

Takes the fully patched unified-wifi-mesh source tree. Checks that both places in the Topology
Response that remove a learned backhaul station's row record it first, then compiles the BSS list
update's reconciliation (dm_bss_list_t::reconcile_device_bss) and the model's record of removed
rows against a small model of the database and the data model, with AddressSanitizer, and plays
an EMOSA pod that moved its backhaul from its 5 GHz station to its 2.4 GHz one:
- the 5 GHz station's row, its radio's only one, leaves the database once the model removed it;
- a row of a radio the model has not seen yet stays (an agent's incremental onboarding);
- a row of a radio the model holds goes when the model does not hold it, as before;
- the rows the model holds stay, and so does every other device's;
- the record is forgotten once its rows are gone, and a row the model holds again stays.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("source_root", type=Path)
args = parser.parse_args()
root = args.source_root

configuration = (root / "src/em/config/em_configuration.cpp").read_text()
for removal in ("dm->remove_bss_by_index(\n                                static_cast<unsigned int>(stale_idx));",
                "dm->remove_bss_by_index(static_cast<unsigned int>(index));"):
    assert configuration.count(removal) == 1, removal
    before = configuration[:configuration.index(removal)].rstrip().splitlines()[-1].strip()
    assert before.startswith("dm->remember_removed_bss("), f"not recorded before {removal!r}: {before!r}"

bss_list = (root / "src/dm/dm_bss_list.cpp").read_text()
start = bss_list.index("int dm_bss_list_t::reconcile_device_bss(db_client_t& db_client,")
end = bss_list.index("\nint dm_bss_list_t::set_config(", start)
reconcile = bss_list[start:end]
assert "is_removed_bss" in reconcile and "clear_removed_bss" in reconcile, "the reconciliation reads the record"

easy_mesh = (root / "src/dm/dm_easy_mesh.cpp").read_text()
methods = ""
for name in ("void dm_easy_mesh_t::remember_removed_bss(const em_bss_info_t *bss)",
             "bool dm_easy_mesh_t::is_removed_bss(const unsigned char *ruid, const unsigned char *bssid,"):
    begin = easy_mesh.index(name)
    methods += easy_mesh[begin:easy_mesh.index("\n}\n", begin) + 3] + "\n"

program = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#define em_printfout(...) ((void)0)
#define EM_MAX_BSSS 24
typedef unsigned char mac_address_t[6];
typedef char em_long_string_t[128];
typedef char mac_addr_str_t[18];
typedef char db_query_t[512];
enum em_haul_type_t { em_haul_type_fronthaul, em_haul_type_backhaul };
enum dm_orch_type_t { dm_orch_type_db_delete };
struct em_interface_t { mac_address_t mac; };
struct em_bss_id_t { em_long_string_t net_id; mac_address_t dev_mac, ruid, bssid; em_haul_type_t haul_type; };
struct em_bss_info_t { em_bss_id_t id; em_interface_t bssid, ruid; };
struct em_device_info_t { em_interface_t intf; };

static void mac_of(const char *s, unsigned char *mac)
{
    unsigned int b[6];
    assert(sscanf(s, "%x:%x:%x:%x:%x:%x", &b[0], &b[1], &b[2], &b[3], &b[4], &b[5]) == 6);
    for (int i = 0; i < 6; i++) mac[i] = static_cast<unsigned char>(b[i]);
}

struct dm_bss_t {
    em_bss_info_t m_bss_info;
    void init() { memset(&m_bss_info, 0, sizeof(m_bss_info)); }
    em_bss_info_t *get_bss_info() { return &m_bss_info; }
};

struct row_t { std::string id, bssid, ruid; };
struct db_client_t {
    std::vector<row_t> rows;
    size_t cursor = 0;
    void *execute(const char *query) { assert(strcmp(query, "select ID,BSSID,RUID from BSSList") == 0); cursor = 0; return this; }
    bool next_result(void *) { return cursor++ < rows.size(); }
    void get_string(void *, char *out, int column)
    {
        const row_t &r = rows[cursor - 1];
        strcpy(out, (column == 1 ? r.id : column == 2 ? r.bssid : r.ruid).c_str());
    }
    bool has(const std::string &id) const { for (auto &r : rows) if (r.id == id) return true; return false; }
};

struct dm_easy_mesh_t {
    em_device_info_t device{};
    std::vector<em_bss_info_t> bss;
    unsigned int m_num_removed_bss = 0;
    em_bss_id_t m_removed_bss[EM_MAX_BSSS];
    em_device_info_t *get_device_info() { return &device; }
    unsigned int get_num_bss() { return static_cast<unsigned int>(bss.size()); }
    em_bss_info_t *get_bss_info(unsigned int i) { return i < bss.size() ? &bss[i] : nullptr; }
    void remember_removed_bss(const em_bss_info_t *bss);
    bool is_removed_bss(const unsigned char *ruid, const unsigned char *bssid, em_haul_type_t haul_type);
    void clear_removed_bss() { m_num_removed_bss = 0; }
    static void string_to_macbytes(const char *s, unsigned char *mac) { mac_of(s, mac); }
};
@METHODS@

struct dm_bss_list_t {
    db_client_t *db;
    static void parse_bss_id_from_key(const char *key, em_bss_id_t *id)
    {
        char net[128], dev[18], ruid[18], bssid[18]; int haul;
        memset(id, 0, sizeof(*id));
        assert(sscanf(key, "%127[^@]@%17[^@]@%17[^@]@%17[^@]@%d", net, dev, ruid, bssid, &haul) == 5);
        strcpy(id->net_id, net); mac_of(dev, id->dev_mac); mac_of(ruid, id->ruid); mac_of(bssid, id->bssid);
        id->haul_type = static_cast<em_haul_type_t>(haul);
    }
    static int update_db(db_client_t &db_client, dm_orch_type_t, em_bss_info_t *info)
    {
        for (size_t i = 0; i < db_client.rows.size(); i++) {
            em_bss_id_t id; parse_bss_id_from_key(db_client.rows[i].id.c_str(), &id);
            unsigned char bssid[6], ruid[6];
            mac_of(db_client.rows[i].bssid.c_str(), bssid); mac_of(db_client.rows[i].ruid.c_str(), ruid);
            if (memcmp(id.dev_mac, info->id.dev_mac, 6) == 0 && memcmp(ruid, info->ruid.mac, 6) == 0 &&
                    memcmp(bssid, info->bssid.mac, 6) == 0 && id.haul_type == info->id.haul_type) {
                db_client.rows.erase(db_client.rows.begin() + static_cast<long>(i));
                return 0;
            }
        }
        return -1;
    }
    static void update_list(dm_bss_t &, dm_orch_type_t) {}
    int reconcile_device_bss(db_client_t& db_client, dm_easy_mesh_t& dm);
};
@RECONCILE@

static em_bss_info_t row(const char *dev, const char *ruid, const char *bssid, em_haul_type_t haul)
{
    em_bss_info_t b; memset(&b, 0, sizeof(b));
    strcpy(b.id.net_id, "OneWifiMesh");
    mac_of(dev, b.id.dev_mac); mac_of(ruid, b.ruid.mac); mac_of(bssid, b.bssid.mac);
    memcpy(b.id.ruid, b.ruid.mac, 6); memcpy(b.id.bssid, b.bssid.mac, 6);
    b.id.haul_type = haul;
    return b;
}
static std::string key(const char *dev, const char *ruid, const char *bssid, int haul)
{
    return std::string("OneWifiMesh@") + dev + "@" + ruid + "@" + bssid + "@" + std::to_string(haul);
}
static void insert(db_client_t &db, const char *dev, const char *ruid, const char *bssid, int haul)
{
    db.rows.push_back({key(dev, ruid, bssid, haul), bssid, ruid});
}

int main()
{
    const char *pod = "02:c2:b8:31:3a:f8", *other = "02:00:00:00:69:20";
    const char *radio24 = "02:00:00:00:6c:00", *sta50 = "02:00:00:00:6d:00", *radio6 = "02:00:00:00:6e:00";
    db_client_t db;
    // the pod: its 2.4 GHz radio's BSSes, its 2.4 GHz station on pod-1, its old 5 GHz station on the gateway
    insert(db, pod, radio24, "82:00:00:00:6c:00", 0);
    insert(db, pod, radio24, "72:00:00:00:6c:00", 1);
    insert(db, pod, radio24, "72:00:00:00:6a:00", 1);
    insert(db, pod, sta50, "02:00:00:4d:06:73", 1);
    insert(db, pod, radio6, "92:00:00:00:6e:00", 0);           // a radio not seen yet
    insert(db, pod, radio24, "a2:00:00:00:6c:00", 0);          // gone from the model, radio present
    insert(db, other, "02:00:00:65:53:be", "02:00:00:68:b6:cc", 1);
    dm_easy_mesh_t dm;
    mac_of(pod, dm.device.intf.mac);
    dm.bss.push_back(row(pod, radio24, "82:00:00:00:6c:00", em_haul_type_fronthaul));
    dm.bss.push_back(row(pod, radio24, "72:00:00:00:6c:00", em_haul_type_backhaul));
    dm.bss.push_back(row(pod, radio24, "72:00:00:00:6a:00", em_haul_type_backhaul));
    em_bss_info_t old_station = row(pod, sta50, "02:00:00:4d:06:73", em_haul_type_backhaul);
    dm.remember_removed_bss(&old_station);
    dm.remember_removed_bss(&old_station);                      // once
    assert(dm.m_num_removed_bss == 1);
    dm_bss_list_t list{&db};
    assert(list.reconcile_device_bss(db, dm) == 0);
    assert(!db.has(key(pod, sta50, "02:00:00:4d:06:73", 1)));  // the radio's last row, removed: gone
    assert(db.has(key(pod, radio6, "92:00:00:00:6e:00", 0)));  // a radio not seen yet: kept
    assert(!db.has(key(pod, radio24, "a2:00:00:00:6c:00", 0)));// a present radio's stale row: gone
    assert(db.has(key(pod, radio24, "82:00:00:00:6c:00", 0)) && db.has(key(pod, radio24, "72:00:00:00:6c:00", 1)) &&
           db.has(key(pod, radio24, "72:00:00:00:6a:00", 1)));
    assert(db.has(key(other, "02:00:00:65:53:be", "02:00:00:68:b6:cc", 1)));
    assert(dm.m_num_removed_bss == 0);                           // forgotten
    // removed, then held again before the update: it stays
    em_bss_info_t back = row(pod, sta50, "02:00:00:4d:06:73", em_haul_type_backhaul);
    insert(db, pod, sta50, "02:00:00:4d:06:73", 1);
    dm.remember_removed_bss(&back);
    dm.bss.push_back(back);
    assert(list.reconcile_device_bss(db, dm) == 0);
    assert(db.has(key(pod, sta50, "02:00:00:4d:06:73", 1)));
    // the record is full: nothing beyond it, nothing overwritten
    for (unsigned int i = 0; i < EM_MAX_BSSS + 2; i++) {
        char bssid[18]; snprintf(bssid, sizeof(bssid), "02:00:00:00:00:%02x", i);
        em_bss_info_t r = row(pod, sta50, bssid, em_haul_type_backhaul);
        dm.remember_removed_bss(&r);
    }
    assert(dm.m_num_removed_bss == EM_MAX_BSSS);
    puts("PASS: a removed BSS row leaves the database, also its radio's last");
    return 0;
}
'''
program = program.replace("@METHODS@", methods).replace("@RECONCILE@", reconcile)
with tempfile.TemporaryDirectory() as work:
    source = Path(work) / "removed_bss.cpp"
    source.write_text(program)
    binary = Path(work) / "removed_bss"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-g", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: controller-removed-bss-database-test")
