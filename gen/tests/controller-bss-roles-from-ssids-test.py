#!/usr/bin/env python3
"""A BSS's role from the controller's own network SSID when the agent says none (0247).

Takes the fully patched unified-wifi-mesh source tree. Compiles
handle_bss_roles_from_network_ssids() against a small model of the data model, with
AddressSanitizer: an AP BSS whose SSID the controller configures for backhaul only becomes a
backhaul BSS, one whose SSID it configures without backhaul (fronthaul, IoT, hotspot) a fronthaul
BSS, also back from backhaul; an SSID configured for backhaul and fronthaul, one the controller
does not configure, an empty SSID and a station row stay as they are; the database is asked to
update only when a role changed. Then checks the Topology Response calls it only without the
vendor operational BSS TLV and without a BSS Configuration Report.
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
signature = "int em_configuration_t::handle_bss_roles_from_network_ssids()"
handler = configuration.split(signature, 1)
assert len(handler) == 2, "em_configuration_t::handle_bss_roles_from_network_ssids"
body = handler[1].split("\n}\n", 1)[0] + "\n}\n"

program = r'''
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
#define em_printfout(...) ((void)0)
#define EM_MAX_HAUL_TYPES 4
typedef unsigned char mac_address_t[6];
typedef char ssid_t[33];
struct mac_t { mac_address_t mac; };
enum em_haul_type_t { em_haul_type_fronthaul, em_haul_type_backhaul, em_haul_type_iot,
                      em_haul_type_configurator, em_haul_type_hotspot, em_haul_type_max };
enum em_vap_mode_t { em_vap_mode_ap, em_vap_mode_sta };
enum db_cfg_type_t { db_cfg_type_bss_list_update };
struct em_bss_id_t { em_haul_type_t haul_type; };
struct em_bss_info_t { em_bss_id_t id; mac_t bssid; ssid_t ssid; em_vap_mode_t vap_mode; };
struct em_network_ssid_info_t { ssid_t ssid; unsigned char num_hauls; em_haul_type_t haul_type[EM_MAX_HAUL_TYPES]; };
struct dm_network_ssid_t {
    em_network_ssid_info_t m_network_ssid_info;
    em_network_ssid_info_t *get_network_ssid_info() { return &m_network_ssid_info; }
};
namespace util { inline std::string mac_to_string(const unsigned char *) { return ""; } }
struct dm_easy_mesh_t {
    std::vector<em_bss_info_t> bss;
    std::vector<dm_network_ssid_t> ssids;
    int updates = 0;
    unsigned int get_num_bss() { return static_cast<unsigned int>(bss.size()); }
    em_bss_info_t *get_bss_info(unsigned int i) { return i < bss.size() ? &bss[i] : nullptr; }
    unsigned int get_num_network_ssid() { return static_cast<unsigned int>(ssids.size()); }
    dm_network_ssid_t *get_network_ssid(unsigned int i) { return &ssids[i]; }
    void set_db_cfg_param(db_cfg_type_t, const char *) { updates++; }
};
struct em_configuration_t {
    dm_easy_mesh_t model;
    dm_easy_mesh_t *get_data_model() { return &model; }
    int handle_bss_roles_from_network_ssids();
};
int em_configuration_t::handle_bss_roles_from_network_ssids()
@BODY@
static em_bss_info_t row(const char *ssid, em_vap_mode_t mode, em_haul_type_t role)
{
    em_bss_info_t r{};
    strncpy(r.ssid, ssid, sizeof(r.ssid) - 1);
    r.vap_mode = mode;
    r.id.haul_type = role;
    return r;
}
static dm_network_ssid_t network(const char *ssid, std::vector<em_haul_type_t> hauls)
{
    dm_network_ssid_t n{};
    strncpy(n.m_network_ssid_info.ssid, ssid, sizeof(n.m_network_ssid_info.ssid) - 1);
    n.m_network_ssid_info.num_hauls = static_cast<unsigned char>(hauls.size());
    for (size_t i = 0; i < hauls.size(); i++) n.m_network_ssid_info.haul_type[i] = hauls[i];
    return n;
}
int main()
{
    em_configuration_t c;
    c.model.ssids = {network("private_ssid", {em_haul_type_fronthaul}),
                     network("iot_ssid", {em_haul_type_iot}),
                     network("mesh_backhaul", {em_haul_type_backhaul}),
                     network("hotspot", {em_haul_type_hotspot}),
                     network("combined", {em_haul_type_backhaul, em_haul_type_fronthaul})};
    c.model.bss = {row("mesh_backhaul", em_vap_mode_ap, em_haul_type_fronthaul),   /* 0: the pod's b-ap-24 */
                   row("private_ssid", em_vap_mode_ap, em_haul_type_backhaul),    /* 1: back to fronthaul */
                   row("iot_ssid", em_vap_mode_ap, em_haul_type_fronthaul),       /* 2: stays fronthaul */
                   row("hotspot", em_vap_mode_ap, em_haul_type_fronthaul),        /* 3: stays fronthaul */
                   row("combined", em_vap_mode_ap, em_haul_type_fronthaul),       /* 4: ambiguous, kept */
                   row("unknown", em_vap_mode_ap, em_haul_type_fronthaul),        /* 5: not configured, kept */
                   row("", em_vap_mode_ap, em_haul_type_fronthaul),               /* 6: no SSID, kept */
                   row("private_ssid", em_vap_mode_sta, em_haul_type_backhaul)};  /* 7: a station row, kept */
    assert(c.handle_bss_roles_from_network_ssids() == 0);
    assert(c.model.bss[0].id.haul_type == em_haul_type_backhaul);
    assert(c.model.bss[1].id.haul_type == em_haul_type_fronthaul);
    assert(c.model.bss[2].id.haul_type == em_haul_type_fronthaul);
    assert(c.model.bss[3].id.haul_type == em_haul_type_fronthaul);
    assert(c.model.bss[4].id.haul_type == em_haul_type_fronthaul);
    assert(c.model.bss[5].id.haul_type == em_haul_type_fronthaul);
    assert(c.model.bss[6].id.haul_type == em_haul_type_fronthaul);
    assert(c.model.bss[7].id.haul_type == em_haul_type_backhaul && c.model.bss[7].vap_mode == em_vap_mode_sta);
    assert(c.model.updates == 1);
    assert(c.handle_bss_roles_from_network_ssids() == 0 && c.model.updates == 1);   /* no change, no update */
    /* an SSID of the full 32 octets matches */
    em_configuration_t t;
    const char *full = "abcdefghijklmnopqrstuvwxyz012345";
    t.model.ssids = {network(full, {em_haul_type_backhaul})};
    t.model.bss = {row(full, em_vap_mode_ap, em_haul_type_fronthaul)};
    assert(t.handle_bss_roles_from_network_ssids() == 0 && t.model.bss[0].id.haul_type == em_haul_type_backhaul);
    /* no network SSIDs at all: nothing changes */
    em_configuration_t e;
    e.model.bss = {row("mesh_backhaul", em_vap_mode_ap, em_haul_type_fronthaul)};
    assert(e.handle_bss_roles_from_network_ssids() == 0 && e.model.bss[0].id.haul_type == em_haul_type_fronthaul);
    assert(e.model.updates == 0);
    return 0;
}
'''.replace("@BODY@", body)

with tempfile.TemporaryDirectory() as tmp:
    src, exe = Path(tmp) / "roles.cpp", Path(tmp) / "roles"
    src.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-O0", "-g", "-Wall", "-Wextra", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-o", str(exe), str(src)], check=True)
    subprocess.run([str(exe)], check=True)

call = configuration.split("// bss_conf_rep is optional; reset cursor so subsequent TLV searches still run", 1)
assert len(call) == 2, "the Topology Response's branch without a BSS Configuration Report"
assert call[1].split("\n    }\n", 1)[0].count("if (!vendor_bss_snapshot) {\n            handle_bss_roles_from_network_ssids();") == 1, \
    "without a BSS Configuration Report, and without the vendor TLV, the roles come from the network SSIDs"
assert configuration.count("handle_bss_roles_from_network_ssids();") == 1, "called in that branch only"
print("controller BSS roles from the controller's network SSIDs: ok")
