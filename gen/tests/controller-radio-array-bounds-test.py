#!/usr/bin/env python3
"""A model built from the network starts with no radios, and the radio array stays bounded.

Takes the fully patched unified-wifi-mesh source tree (0243). Compiles the model's two
constructors over memory full of garbage, the radio copy in operator= against a source that
claims a thousand radios, and both Radio Basic Capability handlers' new-radio step against a
full array; then checks that every other radio append checks EM_MAX_BANDS first.
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
model = (root / "src/dm/dm_easy_mesh.cpp").read_text()


def extract(pattern, text, what):
    found = re.search(pattern, text, re.S)
    assert found, what
    return found.group(0)


default_ctor = extract(r"dm_easy_mesh_t::dm_easy_mesh_t\(\)\n.*?\n\}\n", model,
                       "the default constructor")
network_ctor = extract(r"dm_easy_mesh_t::dm_easy_mesh_t\(const dm_network_t& net\)\n.*?\n\}\n",
                       model, "the constructor from a dm_network_t")
assignment = extract(r"dm_easy_mesh_t& dm_easy_mesh_t::operator = \(dm_easy_mesh_t const& obj\)"
                     r".*?\n\}\n", model, "operator=")
radio_copy = extract(r"    this->m_num_radios = obj\.m_num_radios;.*?m_radio\[i\] = obj\.m_radio\[i\];\s*\}",
                     assignment, "operator= copies the radios")


def handler_step(path, cls):
    source = (root / path).read_text()
    body = source.split(f"int {cls}::handle_ap_radio_basic_cap(unsigned char *buff, unsigned int len)", 1)
    assert len(body) == 2, f"{path} has {cls}::handle_ap_radio_basic_cap"
    return extract(r"\tif \(radio_exists == false\) \{\n.*?\n\t\}\n", body[1],
                   f"{path}: the new-radio step")


capability_step = handler_step("src/em/capability/em_capability.cpp", "em_capability_t")
configuration_step = handler_step("src/em/config/em_configuration.cpp", "em_configuration_t")

program = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <new>
#define em_printfout(...) ((void)0)
#define EM_MAX_BANDS 3
typedef unsigned char mac_address_t[6];
struct em_interface_t { mac_address_t mac; char name[32]; };
struct em_device_info_t { em_interface_t id, backhaul_alid, backhaul_mac, intf; };
struct em_network_info_t { em_interface_t ctrl_id; };
struct dm_network_t { em_network_info_t m_net_info; };
struct dm_device_t { em_device_info_t m_device_info; };
enum { db_cfg_type_none = 0 };
struct em_db_cfg_param_t { int db_cfg_type; };
struct webconfig_subdoc_data_t;
struct dm_easy_mesh_t {
    webconfig_subdoc_data_t *m_wifi_data;
    unsigned int m_num_preferences, m_num_interfaces, m_num_radios, m_num_opclass, m_num_policy,
        m_num_bss, m_num_ap_mld, m_num_net_ssids, m_num_assoc_sta_mld;
    unsigned int m_num_removed_bss = 0;    /* 0251: the BSS rows removed, for the database */
    unsigned int m_num_unreported_bsta = 0;    /* 0254: learned stations between parents */
    em_db_cfg_param_t m_db_cfg_param;
    bool m_colocated, m_is_ctlr;
    dm_device_t m_device;
    dm_easy_mesh_t();
    dm_easy_mesh_t(const dm_network_t& net);
    static int name_from_mac_address(const mac_address_t *, char *) { return 0; }
};
@DEFAULT_CTOR@
@NETWORK_CTOR@

struct radio_t { int value; };
struct copy_model_t {
    unsigned int m_num_radios;
    radio_t m_radio[EM_MAX_BANDS];
    radio_t beyond[1024];
    void copy(const copy_model_t& obj);
};
void copy_model_t::copy(const copy_model_t& obj)
{
@RADIO_COPY@
}

struct em_radio_info_t { unsigned char intf[16]; };
struct dm_radio_t { em_radio_info_t m_radio_info; };
struct model_t {
    unsigned int radios;
    dm_radio_t radio[EM_MAX_BANDS];
    unsigned int get_num_radios() { return radios; }
    dm_radio_t *get_radio(unsigned int index) { return index < EM_MAX_BANDS ? &radio[index] : NULL; }
    void set_num_radios(unsigned int num) { radios = num; }
};
static int capability_step(model_t *dm, char *mac_str)
{
    dm_radio_t *radio = NULL;
    bool radio_exists = false;
@CAPABILITY_STEP@
    return radio == NULL ? 1 : 0;
}
static int configuration_step(model_t *dm, char *mac_str)
{
    dm_radio_t *radio = NULL;
    bool radio_exists = false;
@CONFIGURATION_STEP@
    return radio == NULL ? 1 : 0;
}

int main()
{
    alignas(dm_easy_mesh_t) unsigned char garbage[sizeof(dm_easy_mesh_t)];
    memset(garbage, 0xa5, sizeof(garbage));
    dm_network_t net;
    memset(&net, 0, sizeof(net));
    dm_easy_mesh_t *built = new (garbage) dm_easy_mesh_t(net);
    assert(built->m_num_radios == 0);
    assert(built->m_num_bss == 0 && built->m_num_opclass == 0 && built->m_num_policy == 0);
    assert(built->m_num_net_ssids == 0 && built->m_num_ap_mld == 0 && built->m_num_assoc_sta_mld == 0);
    assert(built->m_num_interfaces == 0 && built->m_num_preferences == 0);

    static copy_model_t source, target;
    source.m_num_radios = 1000;
    for (auto &r : source.m_radio) r.value = 7;
    for (auto &r : source.beyond) r.value = 7;
    target.copy(source);
    assert(target.m_num_radios == EM_MAX_BANDS);
    for (auto &r : target.m_radio) assert(r.value == 7);
    for (auto &r : target.beyond) assert(r.value == 0);
    source.m_num_radios = 2;
    target.copy(source);
    assert(target.m_num_radios == 2);

    char mac[] = "02:00:00:00:00:01";
    int (*steps[])(model_t *, char *) = { capability_step, configuration_step };
    for (auto step : steps) {
        model_t full = {};
        full.radios = EM_MAX_BANDS;
        assert(step(&full, mac) == -1);
        assert(full.radios == EM_MAX_BANDS);
        model_t room = {};
        room.radios = EM_MAX_BANDS - 1;
        assert(step(&room, mac) == 0);
        assert(room.radios == EM_MAX_BANDS);
    }
    return 0;
}
'''
program = (program.replace("@DEFAULT_CTOR@", default_ctor)
           .replace("@NETWORK_CTOR@", network_ctor)
           .replace("@RADIO_COPY@", radio_copy)
           .replace("@CAPABILITY_STEP@", capability_step)
           .replace("@CONFIGURATION_STEP@", configuration_step))

with tempfile.TemporaryDirectory() as tmp:
    src = Path(tmp) / "bounds.cpp"
    exe = Path(tmp) / "bounds"
    src.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-O0", "-Wall", "-Wno-unused-variable", "-o", str(exe),
                    str(src)], check=True)
    subprocess.run([str(exe)], check=True)

# Every other radio append checks the array first.
appends = {
    "src/dm/dm_easy_mesh.cpp": [r"m_radio\[m_num_radios\] = \*\(radio\);",
                                r"m_radio\[m_num_radios\] = cmd->m_data_model\.m_radio\[0\];",
                                r"m_radio\[m_num_radios\]\.decode\("],
    "src/dm/dm_easy_mesh_list.cpp": [r"dm->set_num_radios\(dm->get_num_radios\(\) \+ 1\);"],
    "src/ctrl/dm_easy_mesh_ctrl.cpp": [r"memcpy\(dm\.m_radio\[dm\.m_num_radios\]",
                                       r"tgt\.m_radio\[tgt\.m_num_radios\] = "],
}
for path, patterns in appends.items():
    lines = (root / path).read_text().splitlines()
    for pattern in patterns:
        hits = [i for i, line in enumerate(lines) if re.search(pattern, line)]
        assert hits, f"{path}: no append matches {pattern}"
        for i in hits:
            window = "\n".join(lines[max(0, i - 6):i])
            assert ">= EM_MAX_BANDS" in window, f"{path}:{i + 1}: append without an EM_MAX_BANDS check"
ctrl = (root / "src/ctrl/dm_easy_mesh_ctrl.cpp").read_text()
assert "m_num_radios >= EM_MAX_RADIO_PER_AGENT" not in ctrl, \
    "the policy request guards m_radio[EM_MAX_BANDS] with EM_MAX_RADIO_PER_AGENT"
print("controller radio array bounds: ok")
