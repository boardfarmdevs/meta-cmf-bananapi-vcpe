#!/usr/bin/env python3
"""SteerWiFiBackhaul() sends the target's operating class on every band (0249).

Takes the fully patched unified-wifi-mesh source tree. Compiles the two helpers of
SteerWiFiBackhaul() against a small model, with AddressSanitizer:
- a target the controller models (an AP BSS of any device) takes its radio's current operating
  class and channel; a station row with that BSSID, another radio's class, a class that is not
  the current one and an unknown BSSID give none;
- a Channel alone gives the 20 MHz class of the one band it names (IEEE 802.11 Annex E), and none
  for a number two bands use (2.4 GHz 1, 5, 9, 13 and 5 GHz 149-177 are 6 GHz numbers too) or
  that no band uses.
Then checks the method uses them: the model first, a Channel that is not the known target's
refused, an unknown target on no single band refused, and no 5 GHz-only derivation left.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile


parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("source_root", type=Path)
args = parser.parse_args()
root = args.source_root
source = (root / "src/ctrl/dm_easy_mesh_ctrl.cpp").read_text()
operation = source[source.index("static bool backhaul_target_operation("):]
operation = operation[:operation.index("\n}\n") + 3]
of_channel = source[source.index("static unsigned char backhaul_op_class_of_channel("):]
of_channel = of_channel[:of_channel.index("\n}\n") + 3]

program = r'''
#include <cassert>
#include <cstring>
#include <mutex>
#include <vector>
#define EM_MAX_OPCLASS 8
typedef unsigned char mac_address_t[6];
std::recursive_mutex g_network_topology_mutex;
enum em_vap_mode_t { em_vap_mode_ap, em_vap_mode_sta };
enum em_op_class_type_t { em_op_class_type_none, em_op_class_type_current, em_op_class_type_preference };
struct em_interface_t { mac_address_t mac; };
struct em_bss_info_t { em_interface_t bssid, ruid; em_vap_mode_t vap_mode; };
struct em_op_class_id_t { mac_address_t ruid; em_op_class_type_t type; };
struct em_op_class_info_t { em_op_class_id_t id; unsigned int op_class; unsigned int channel; };
struct dm_easy_mesh_t {
    std::vector<em_bss_info_t> bss;
    em_op_class_info_t ops[EM_MAX_OPCLASS];
    unsigned int m_num_opclass = 0;
    unsigned int get_num_bss() { return static_cast<unsigned int>(bss.size()); }
    em_bss_info_t *get_bss_info(unsigned int i) { return i < bss.size() ? &bss[i] : nullptr; }
    em_op_class_info_t *get_op_class_info(unsigned int i) { return &ops[i]; }
};
struct dm_easy_mesh_ctrl_t {
    std::vector<dm_easy_mesh_t *> models;
    dm_easy_mesh_t *get_first_dm() { return models.empty() ? nullptr : models[0]; }
    dm_easy_mesh_t *get_next_dm(dm_easy_mesh_t *dm)
    {
        for (size_t i = 0; i + 1 < models.size(); i++) if (models[i] == dm) return models[i + 1];
        return nullptr;
    }
};
@OPERATION@
@OF_CHANNEL@
static void mac(mac_address_t m, unsigned char last) { memset(m, 0x02, 6); m[5] = last; }
static em_bss_info_t bss(unsigned char bssid, unsigned char ruid, em_vap_mode_t mode)
{
    em_bss_info_t b{};
    mac(b.bssid.mac, bssid); mac(b.ruid.mac, ruid); b.vap_mode = mode;
    return b;
}
static void op(dm_easy_mesh_t &m, unsigned char ruid, em_op_class_type_t type, unsigned int cls, unsigned int ch)
{
    em_op_class_info_t &o = m.ops[m.m_num_opclass++];
    memset(&o, 0, sizeof(o));
    mac(o.id.ruid, ruid); o.id.type = type; o.op_class = cls; o.channel = ch;
}
int main()
{
    dm_easy_mesh_t gateway, pod;
    gateway.bss = {bss(0x73, 0x10, em_vap_mode_ap)};
    op(gateway, 0x10, em_op_class_type_preference, 118, 52);
    op(gateway, 0x10, em_op_class_type_current, 115, 36);
    pod.bss = {bss(0x61, 0x20, em_vap_mode_sta),       /* a station row on the gateway's BSSID 0x61 */
               bss(0x6a, 0x20, em_vap_mode_ap),        /* the pod's backhaul BSS */
               bss(0x6b, 0x21, em_vap_mode_ap)};       /* a BSS of a radio with no current class */
    op(pod, 0x21, em_op_class_type_preference, 81, 1);
    op(pod, 0x20, em_op_class_type_current, 81, 6);
    dm_easy_mesh_ctrl_t ctrl;
    ctrl.models = {&gateway, &pod};
    mac_address_t target;
    unsigned char cls = 0, ch = 0;
    mac(target, 0x6a);
    assert(backhaul_target_operation(&ctrl, target, &cls, &ch) && cls == 81 && ch == 6);
    mac(target, 0x73);
    assert(backhaul_target_operation(&ctrl, target, &cls, &ch) && cls == 115 && ch == 36);
    cls = ch = 0;
    mac(target, 0x61);
    assert(!backhaul_target_operation(&ctrl, target, &cls, &ch) && cls == 0 && ch == 0);
    mac(target, 0x6b);
    assert(!backhaul_target_operation(&ctrl, target, &cls, &ch));
    mac(target, 0x99);
    assert(!backhaul_target_operation(&ctrl, target, &cls, &ch));
    dm_easy_mesh_ctrl_t empty;
    assert(!backhaul_target_operation(&empty, target, &cls, &ch));

    const int unique[][2] = {{2, 81}, {6, 81}, {11, 81}, {14, 82}, {36, 115}, {48, 115}, {52, 118},
                             {64, 118}, {100, 121}, {144, 121}, {17, 131}, {37, 131}, {145, 131},
                             {181, 131}, {233, 131}};
    for (auto &u : unique) assert(backhaul_op_class_of_channel(u[0]) == u[1]);
    const int none[] = {-1, 0, 1, 5, 9, 13, 15, 34, 38, 68, 96, 149, 153, 165, 177, 178, 234, 255};
    for (int n : none) assert(backhaul_op_class_of_channel(n) == 0);
    return 0;
}
'''.replace("@OPERATION@", operation).replace("@OF_CHANNEL@", of_channel)

with tempfile.TemporaryDirectory() as tmp:
    src, exe = Path(tmp) / "opclass.cpp", Path(tmp) / "opclass"
    src.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-O0", "-g", "-Wall", "-Wextra", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-o", str(exe), str(src)], check=True)
    subprocess.run([str(exe)], check=True)

method = source[source.index("bus_error_t em_ctrl_t::cmd_steerwifibh("):]
method = method[:method.index("\n}\n")]
assert "backhaul_target_operation(dm_ctrl, target_mac, &op_class, &op_channel)" in method, "the model first"
assert "if (channel > 0 && channel != op_channel)" in method, "a Channel that is not the known target's is refused"
assert "op_class = backhaul_op_class_of_channel(channel);" in method, "else the class of the one band Channel names"
assert "requested.op_class = op_class;" in method and "requested.channel = op_channel;" in method
assert "channel >= 149 ? 125" not in method, "no 5 GHz-only derivation left"
print("controller SteerWiFiBackhaul() operating class on every band: ok")
