#!/usr/bin/env python3
"""A BSS's role from the BSS Configuration Report when the vendor operational BSS TLV gives none.

Takes the fully patched unified-wifi-mesh source tree (0246). Compiles
handle_bss_configuration_report() against a small model of the data model, with AddressSanitizer:
a BSS flagged backhaul (0x80) becomes a backhaul BSS of its radio and one flagged fronthaul (0x40)
a fronthaul one; a station row with the same BSSID, a BSS of another radio and an entry with
neither flag stay as they are; nothing changes unless the caller asks for the report's roles;
a TLV whose entries run past its length is read only as far as they fit. Then checks the
Topology Response passes the length in host order and asks for the roles only without the
vendor operational BSS TLV.
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
signature = ("int em_configuration_t::handle_bss_configuration_report(unsigned char *buff, unsigned int len, "
             "bool roles_from_report)")
handler = configuration.split(signature, 1)
assert len(handler) == 2, "em_configuration_t::handle_bss_configuration_report with roles_from_report"
body = handler[1].split("\n}\n", 1)[0] + "\n}\n"

program = r'''
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
#define em_printfout(...) ((void)0)
typedef unsigned char mac_address_t[6];
struct mac_t { mac_address_t mac; };
enum em_haul_type_t { em_haul_type_fronthaul, em_haul_type_backhaul, em_haul_type_iot,
                      em_haul_type_configurator, em_haul_type_max };
enum em_vap_mode_t { em_vap_mode_ap, em_vap_mode_sta };
enum db_cfg_type_t { db_cfg_type_bss_list_update };
struct em_bss_id_t { em_haul_type_t haul_type; };
struct em_bss_info_t { em_bss_id_t id; mac_t ruid; mac_t bssid; em_vap_mode_t vap_mode; };
namespace util { inline std::string mac_to_string(const unsigned char *) { return ""; } }
struct dm_easy_mesh_t {
    std::vector<em_bss_info_t> bss;
    int updates = 0;
    unsigned int get_num_bss() { return static_cast<unsigned int>(bss.size()); }
    em_bss_info_t *get_bss_info(unsigned int i) { return i < bss.size() ? &bss[i] : nullptr; }
    void set_db_cfg_param(db_cfg_type_t, const char *) { updates++; }
};
struct em_configuration_t {
    dm_easy_mesh_t model;
    dm_easy_mesh_t *get_data_model() { return &model; }
    int handle_bss_configuration_report(unsigned char *buff, unsigned int len, bool roles_from_report);
};
int em_configuration_t::handle_bss_configuration_report(unsigned char *buff, unsigned int len, bool roles_from_report)
@BODY@
static em_bss_info_t row(unsigned char radio, unsigned char last, em_vap_mode_t mode, em_haul_type_t role)
{
    em_bss_info_t r{};
    for (int i = 0; i < 6; i++) { r.ruid.mac[i] = 0x02; r.bssid.mac[i] = 0x72; }
    r.ruid.mac[5] = radio;
    r.bssid.mac[5] = last;
    r.vap_mode = mode;
    r.id.haul_type = role;
    return r;
}
/* one radio's entries: (last BSSID octet, flags, SSID length) */
static std::vector<unsigned char> report(unsigned char radio, std::vector<std::vector<int>> entries)
{
    std::vector<unsigned char> v{1, 0x02, 0x02, 0x02, 0x02, 0x02, radio,
                                 static_cast<unsigned char>(entries.size())};
    for (auto &e : entries) {
        for (int i = 0; i < 5; i++) v.push_back(0x72);
        v.push_back(static_cast<unsigned char>(e[0]));
        v.push_back(static_cast<unsigned char>(e[1]));
        v.push_back(0);
        v.push_back(static_cast<unsigned char>(e[2]));
        for (int i = 0; i < e[2]; i++) v.push_back('x');
    }
    return v;
}
static int run(em_configuration_t &c, const std::vector<unsigned char> &v, unsigned int len, bool roles)
{
    /* exactly len bytes on the heap: AddressSanitizer catches any read past them */
    unsigned char *buff = new unsigned char[len ? len : 1];
    memcpy(buff, v.data(), len < v.size() ? len : v.size());
    int rc = c.handle_bss_configuration_report(buff, len, roles);
    delete[] buff;
    return rc;
}
int main()
{
    em_configuration_t c;
    c.model.bss = {row(0x10, 0x01, em_vap_mode_ap, em_haul_type_fronthaul),     /* the backhaul BSS */
                   row(0x10, 0x02, em_vap_mode_ap, em_haul_type_backhaul),      /* a fronthaul one */
                   row(0x10, 0x03, em_vap_mode_sta, em_haul_type_backhaul),     /* a station row */
                   row(0x11, 0x01, em_vap_mode_ap, em_haul_type_fronthaul),     /* another radio */
                   row(0x10, 0x04, em_vap_mode_ap, em_haul_type_fronthaul)};    /* no flag */
    auto v = report(0x10, {{0x01, 0x80, 13}, {0x02, 0x40, 0}, {0x03, 0x40, 4}, {0x04, 0x00, 2}});
    assert(run(c, v, static_cast<unsigned int>(v.size()), false) == 0);
    assert(c.model.bss[0].id.haul_type == em_haul_type_fronthaul && c.model.updates == 0);
    assert(run(c, v, static_cast<unsigned int>(v.size()), true) == 0);
    assert(c.model.bss[0].id.haul_type == em_haul_type_backhaul);
    assert(c.model.bss[1].id.haul_type == em_haul_type_fronthaul);
    assert(c.model.bss[2].id.haul_type == em_haul_type_backhaul && c.model.bss[2].vap_mode == em_vap_mode_sta);
    assert(c.model.bss[3].id.haul_type == em_haul_type_fronthaul);
    assert(c.model.bss[4].id.haul_type == em_haul_type_fronthaul);
    assert(c.model.updates == 1);
    assert(run(c, v, static_cast<unsigned int>(v.size()), true) == 0 && c.model.updates == 1);  /* no change */
    /* cut anywhere: what fits is taken, nothing past the length is read */
    for (unsigned int len = 0; len < v.size(); len++) {
        em_configuration_t t;
        t.model.bss = {row(0x10, 0x01, em_vap_mode_ap, em_haul_type_fronthaul)};
        assert(run(t, v, len, true) == 0);
        assert(t.model.bss[0].id.haul_type == (len >= 8 + 9 + 13 ? em_haul_type_backhaul : em_haul_type_fronthaul));
    }
    auto claims = report(0x10, {{0x01, 0x80, 3}});
    claims[0] = 3;                                     /* three radios declared, one present */
    em_configuration_t t;
    t.model.bss = {row(0x10, 0x01, em_vap_mode_ap, em_haul_type_fronthaul)};
    assert(run(t, claims, static_cast<unsigned int>(claims.size()), true) == 0);
    assert(t.model.bss[0].id.haul_type == em_haul_type_backhaul);
    return 0;
}
'''.replace("@BODY@", body)

with tempfile.TemporaryDirectory() as tmp:
    src, exe = Path(tmp) / "roles.cpp", Path(tmp) / "roles"
    src.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-O0", "-g", "-Wall", "-Wextra", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-o", str(exe), str(src)], check=True)
    subprocess.run([str(exe)], check=True)

assert "handle_bss_configuration_report(tlv->value, ntohs(tlv->len), !vendor_bss_snapshot)" in configuration, \
    "the Topology Response passes the length in host order and asks for the roles without the vendor TLV"
print("controller BSS roles from the BSS Configuration Report: ok")
