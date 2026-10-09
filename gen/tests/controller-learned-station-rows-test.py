#!/usr/bin/env python3
"""Learned backhaul station rows known by their mode and MAC, not by having no radio (0248).

Takes the fully patched unified-wifi-mesh source tree. Compiles the Topology Response's Device
Information station slice (from the reported-station list to the removal of stations no longer
reported) against a small model of the data model, with AddressSanitizer, and plays an agent
without RDK's vendor TLV (an EMOSA pod) whose 2.4 GHz station shares its MAC with its radio's
identifier:
- its 5 GHz station is learned as a row of its own;
- a move to its 2.4 GHz station keeps one station row: the 2.4 GHz one, the 5 GHz row goes;
- the way back removes the 2.4 GHz row, although a radio has its identifier;
- a 2.4 GHz row reloaded from the database (AP mode, no station) is restored, not learned twice;
- a response with no station removes every learned row;
- the agent's own AP BSSes are never touched, nor anything of an agent with the vendor TLV;
- every prefix of a response is read only as far as it goes.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile


parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("source_root", type=Path)
args = parser.parse_args()
root = args.source_root
configuration = (root / "src/em/config/em_configuration.cpp").read_text()
start_marker = "    /* the station interfaces this response reports, each with its network membership */\n"
end_marker = "    if (em_mgr_t *mgr = get_mgr()) {\n"
if start_marker not in configuration:          # the series before 0248: the same slice, played as is
    start_marker = "    bool standard_bsta_reported = false;\n"
assert configuration.count(start_marker) == 1, "the Topology Response's Device Information station slice"
slice_start = configuration.index(start_marker)
slice_end = configuration.index(end_marker, slice_start)
stations = configuration[slice_start:slice_end]
assert "Backhaul STA no longer reported" in stations, "the removal of stations no longer reported"

program = r'''
#include <arpa/inet.h>
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
#define em_printfout(...) ((void)0)
#define EM_MAX_BSSS 24
#define EM_MEDIA_WIFI_ROLE_STA 0x40
typedef unsigned char mac_address_t[6];
typedef char em_long_string_t[64];
static const mac_address_t ZERO_MAC_ADDR = {0, 0, 0, 0, 0, 0};
enum { em_tlv_type_eom = 0, em_tlv_type_device_info = 3 };
struct em_tlv_t { unsigned char type; unsigned short len; unsigned char value[0]; } __attribute__((__packed__));
struct em_device_info_type_t {
    mac_address_t al_mac_addr;
    unsigned char local_interface_num;
    unsigned char local_interface[0];
} __attribute__((__packed__));
enum em_haul_type_t { em_haul_type_fronthaul, em_haul_type_backhaul };
enum em_vap_mode_t { em_vap_mode_ap, em_vap_mode_sta };
enum db_cfg_type_t { db_cfg_type_bss_list_update };
enum em_freq_band_t { em_freq_band_24, em_freq_band_5, em_freq_band_6 };
struct em_interface_t { mac_address_t mac; };
struct em_bss_id_t { em_long_string_t net_id; mac_address_t dev_mac, ruid, bssid; em_haul_type_t haul_type; };
struct em_bss_info_t {
    em_bss_id_t id; em_interface_t bssid, ruid; em_vap_mode_t vap_mode; bool enabled; mac_address_t sta_mac;
};
struct dm_bss_t { em_bss_info_t m_bss_info; void init() { memset(&m_bss_info, 0, sizeof(m_bss_info)); } };
struct dm_radio_t { struct { mac_address_t mac; em_freq_band_t band; } m_radio_info; };
struct dm_device_t { struct { struct { em_long_string_t net_id; } id; em_interface_t intf; } m_device_info; };
namespace util { inline std::string mac_to_string(const unsigned char *) { return ""; } }
struct dm_easy_mesh_t {
    dm_bss_t m_bss[EM_MAX_BSSS];
    unsigned int m_num_bss = 0;
    std::vector<dm_radio_t> radios;
    dm_device_t m_device{};
    int updates = 0;
    unsigned int get_num_bss() { return m_num_bss; }
    void set_num_bss(unsigned int n) { m_num_bss = n; }
    em_bss_info_t *get_bss_info(unsigned int i) { return i < m_num_bss ? &m_bss[i].m_bss_info : nullptr; }
    dm_radio_t *get_radio(const unsigned char *mac)
    {
        for (auto &r : radios) if (memcmp(r.m_radio_info.mac, mac, 6) == 0) return &r;
        return nullptr;
    }
    void remove_bss_by_index(unsigned int index)
    {
        assert(index < m_num_bss);
        for (unsigned int i = index; i < m_num_bss - 1; i++) m_bss[i] = m_bss[i + 1];
        m_num_bss--;
    }
    void set_db_cfg_param(db_cfg_type_t, const char *) { updates++; }
    /* the rows removed, for their database rows to go too (0251) */
    std::vector<em_bss_info_t> removed;
    void remember_removed_bss(const em_bss_info_t *bss) { removed.push_back(*bss); }
};

static int stations(dm_easy_mesh_t *dm, unsigned char *device_cursor, unsigned int device_remaining,
    bool vendor_bss_snapshot)
{
    int ret = 0;
@SLICE@
    return ret;
}

static const mac_address_t RADIO_24 = {0x02, 0, 0, 0, 0x6c, 0};       /* also the 2.4 GHz station */
static const mac_address_t STA_5 = {0x02, 0, 0, 0, 0x6d, 0};          /* no radio of the agent's */
static const mac_address_t GATEWAY_5 = {0x02, 0, 0, 0x4d, 0x06, 0x73};
static const mac_address_t POD1_BH = {0x72, 0, 0, 0, 0x6a, 0};
static const mac_address_t OWN_BH = {0x72, 0, 0, 0, 0x6c, 0};
static const mac_address_t OWN_FH = {0x82, 0, 0, 0, 0x6c, 0};
static const mac_address_t ETH = {0x02, 0xc2, 0xb8, 0x31, 0x3a, 0xf8};

struct entry { const unsigned char *mac; const unsigned char *parent; unsigned char band; };
/* one Device Information TLV, then the end of message */
static std::vector<unsigned char> response(std::vector<entry> entries)
{
    std::vector<unsigned char> value(ETH, ETH + 6);
    value.push_back(static_cast<unsigned char>(entries.size()));
    for (auto &e : entries) {
        value.insert(value.end(), e.mac, e.mac + 6);
        if (e.parent == nullptr) {                       /* Ethernet: no media data */
            value.push_back(0x00); value.push_back(0x01); value.push_back(0);
            continue;
        }
        value.push_back(0x01); value.push_back(e.band == 0x01 ? 0x03 : 0x04); value.push_back(10);
        value.insert(value.end(), e.parent, e.parent + 6);
        value.push_back(EM_MEDIA_WIFI_ROLE_STA); value.push_back(e.band); value.push_back(0); value.push_back(0);
    }
    std::vector<unsigned char> frame{em_tlv_type_device_info,
        static_cast<unsigned char>(value.size() >> 8), static_cast<unsigned char>(value.size())};
    frame.insert(frame.end(), value.begin(), value.end());
    frame.push_back(em_tlv_type_eom); frame.push_back(0); frame.push_back(0);
    return frame;
}
static int run(dm_easy_mesh_t &dm, const std::vector<unsigned char> &frame, unsigned int len, bool vendor)
{
    /* exactly len bytes on the heap: AddressSanitizer catches any read past them */
    unsigned char *buff = new unsigned char[len ? len : 1];
    memcpy(buff, frame.data(), len < frame.size() ? len : frame.size());
    int rc = stations(&dm, buff, len, vendor);
    delete[] buff;
    return rc;
}
static int play(dm_easy_mesh_t &dm, std::vector<entry> entries, bool vendor = false)
{
    auto frame = response(entries);
    return run(dm, frame, static_cast<unsigned int>(frame.size()), vendor);
}
static void ap(dm_easy_mesh_t &dm, const unsigned char *bssid, em_haul_type_t role)
{
    em_bss_info_t &b = dm.m_bss[dm.m_num_bss++].m_bss_info;
    memset(&b, 0, sizeof(b));
    memcpy(b.ruid.mac, RADIO_24, 6); memcpy(b.id.ruid, RADIO_24, 6);
    memcpy(b.bssid.mac, bssid, 6); memcpy(b.id.bssid, bssid, 6);
    b.vap_mode = em_vap_mode_ap; b.id.haul_type = role; b.enabled = true;
}
static dm_easy_mesh_t pod()
{
    dm_easy_mesh_t dm;
    dm_radio_t radio{};
    memcpy(radio.m_radio_info.mac, RADIO_24, 6);
    radio.m_radio_info.band = em_freq_band_24;
    dm.radios.push_back(radio);
    ap(dm, OWN_BH, em_haul_type_backhaul);
    ap(dm, OWN_FH, em_haul_type_fronthaul);
    return dm;
}
static unsigned int station_rows(dm_easy_mesh_t &dm)
{
    unsigned int n = 0;
    for (unsigned int i = 0; i < dm.m_num_bss; i++) {
        const em_bss_info_t &b = dm.m_bss[i].m_bss_info;
        if (b.id.haul_type == em_haul_type_backhaul && !(b.vap_mode == em_vap_mode_ap && dm.get_radio(b.ruid.mac) &&
                memcmp(b.bssid.mac, OWN_BH, 6) == 0)) n++;
    }
    return n;
}
static const em_bss_info_t *station(dm_easy_mesh_t &dm, const unsigned char *mac)
{
    for (unsigned int i = 0; i < dm.m_num_bss; i++) {
        const em_bss_info_t &b = dm.m_bss[i].m_bss_info;
        if (b.vap_mode == em_vap_mode_sta && memcmp(b.sta_mac, mac, 6) == 0) return &b;
    }
    return nullptr;
}
static bool own_aps(dm_easy_mesh_t &dm)
{
    int found = 0;
    for (unsigned int i = 0; i < dm.m_num_bss; i++) {
        const em_bss_info_t &b = dm.m_bss[i].m_bss_info;
        if (b.vap_mode == em_vap_mode_ap && (memcmp(b.bssid.mac, OWN_BH, 6) == 0 || memcmp(b.bssid.mac, OWN_FH, 6) == 0))
            found++;
    }
    return found == 2;
}
int main()
{
    dm_easy_mesh_t dm = pod();
    /* its 5 GHz station on the gateway */
    play(dm, {{ETH, nullptr, 0}, {STA_5, GATEWAY_5, 0x03}});
    assert(station_rows(dm) == 1 && station(dm, STA_5) && memcmp(station(dm, STA_5)->bssid.mac, GATEWAY_5, 6) == 0);
    assert(own_aps(dm));
    /* moved to its 2.4 GHz station on pod-1's backhaul BSS: the 5 GHz row goes */
    play(dm, {{ETH, nullptr, 0}, {RADIO_24, POD1_BH, 0x01}});
    assert(station(dm, RADIO_24) && memcmp(station(dm, RADIO_24)->bssid.mac, POD1_BH, 6) == 0);
    assert(!station(dm, STA_5));
    assert(station_rows(dm) == 1);
    if (@RECORDS@) {   /* 0251: the removed row is recorded for the database */
        assert(!dm.removed.empty() && memcmp(dm.removed.back().ruid.mac, STA_5, 6) == 0);
    }
    assert(own_aps(dm));
    /* the same again: nothing changes */
    unsigned int rows = dm.m_num_bss;
    play(dm, {{ETH, nullptr, 0}, {RADIO_24, POD1_BH, 0x01}});
    assert(dm.m_num_bss == rows && station_rows(dm) == 1);
    /* back to 5 GHz: the 2.4 GHz row goes although a radio has its identifier */
    play(dm, {{ETH, nullptr, 0}, {STA_5, GATEWAY_5, 0x03}});
    assert(!station(dm, RADIO_24) && station(dm, STA_5) && station_rows(dm) == 1);
    assert(own_aps(dm));
    /* no station reported (a wired uplink): every learned row goes */
    play(dm, {{ETH, nullptr, 0}});
    assert(station_rows(dm) == 0 && own_aps(dm));

    /* a 2.4 GHz row reloaded from the database: AP mode, no station; restored, not learned twice */
    dm_easy_mesh_t reloaded = pod();
    em_bss_info_t &r = reloaded.m_bss[reloaded.m_num_bss++].m_bss_info;
    memset(&r, 0, sizeof(r));
    memcpy(r.ruid.mac, RADIO_24, 6); memcpy(r.id.ruid, RADIO_24, 6);
    memcpy(r.bssid.mac, POD1_BH, 6); memcpy(r.id.bssid, POD1_BH, 6);
    r.id.haul_type = em_haul_type_backhaul; r.vap_mode = em_vap_mode_ap; r.enabled = true;
    play(reloaded, {{ETH, nullptr, 0}, {RADIO_24, POD1_BH, 0x01}});
    assert(reloaded.m_num_bss == 3 && station(reloaded, RADIO_24) && station_rows(reloaded) == 1);
    assert(own_aps(reloaded));

    /* an agent with RDK's vendor TLV: its station rows are its own business */
    dm_easy_mesh_t native = pod();
    em_bss_info_t &n = native.m_bss[native.m_num_bss++].m_bss_info;
    memset(&n, 0, sizeof(n));
    memcpy(n.ruid.mac, RADIO_24, 6); memcpy(n.sta_mac, STA_5, 6); memcpy(n.bssid.mac, GATEWAY_5, 6);
    n.id.haul_type = em_haul_type_backhaul; n.vap_mode = em_vap_mode_sta; n.enabled = true;
    play(native, {{ETH, nullptr, 0}}, true);
    assert(native.m_num_bss == 3 && station(native, STA_5));

    /* every prefix of a response: read only as far as it goes */
    auto frame = response({{ETH, nullptr, 0}, {RADIO_24, POD1_BH, 0x01}, {STA_5, GATEWAY_5, 0x03}});
    for (unsigned int len = 0; len <= frame.size(); len++) {
        dm_easy_mesh_t t = pod();
        run(t, frame, len, false);
        assert(own_aps(t));
    }
    return 0;
}
'''.replace("@SLICE@", stations).replace(
    "@RECORDS@", "true" if "remember_removed_bss" in stations else "false")

with tempfile.TemporaryDirectory() as tmp:
    src, exe = Path(tmp) / "stations.cpp", Path(tmp) / "stations"
    src.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-O0", "-g", "-Wall", "-Wextra", "-Wno-unused-parameter",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-o", str(exe), str(src)],
                   check=True)
    subprocess.run([str(exe)], check=True)
print("controller learned backhaul station rows: ok")
