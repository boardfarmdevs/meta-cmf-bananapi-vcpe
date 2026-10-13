#!/usr/bin/env python3
"""SteerWiFiBackhaul() to an unmodelled target on a shared channel number takes the band of the
moving station's own radio (0267).

Takes the fully patched unified-wifi-mesh source tree. On a gateway with two-radio pods
(12 October) the steer of a pod back to the gateway's pod-backhaul BSS, outside the model by
design, on channel 149 was refused: 0249 derives an unmodelled target's class from Channel only when the number belongs to
one band, and 149-177 (and 2.4 GHz 1, 5, 9, 13) are 6 GHz numbers too. Compiles 0267's helper
against a small model, with AddressSanitizer: the band comes from the classes the moving radio's
AP Radio Basic Capabilities advertised (the model's capability rows for its RUID), and a number
that radio could operate in more than one band, or in none, still gives none. Then checks the
method falls back to it only after 0249's derivation and keeps the refusal.
--expect-refused reproduces the defect on a source without 0267: 149 gives no class, and the
method refuses an unmodelled target there whatever the station's radio.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile


parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("source_root", type=Path)
parser.add_argument("--expect-refused", action="store_true")
args = parser.parse_args()
source = (args.source_root / "src/ctrl/dm_easy_mesh_ctrl.cpp").read_text()


def function(name):
    text = source[source.index(name):]
    return text[:text.index("\n}\n") + 3]


method = source[source.index("bus_error_t em_ctrl_t::cmd_steerwifibh("):]
method = method[:method.index("\n}\n")]
of_channel = function("static unsigned char backhaul_op_class_of_channel(")

if args.expect_refused:
    assert "backhaul_op_class_for_radio(" not in source, "this source has 0267"
    program = r'''
#include <cassert>
@OF_CHANNEL@
int main() { assert(backhaul_op_class_of_channel(149) == 0); return 0; }
'''.replace("@OF_CHANNEL@", of_channel)
    with tempfile.TemporaryDirectory() as tmp:
        src, exe = Path(tmp) / "band.cpp", Path(tmp) / "band"
        src.write_text(program)
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-o", str(exe), str(src)], check=True)
        subprocess.run([str(exe)], check=True)
    derive = method.index("op_class = backhaul_op_class_of_channel(channel);")
    refuse = method.index("if (op_class == 0)", derive)
    assert "backhaul_op_class_for_radio" not in method[derive:refuse]
    print("REPRODUCED: an unmodelled target on 149 gets no class and is refused, whatever the station's radio")
    raise SystemExit(0)

for_radio = function("static unsigned char backhaul_op_class_for_radio(")
program = r'''
#include <cassert>
#include <cstring>
#include <mutex>
#define EM_MAX_OPCLASS 16
typedef unsigned char mac_address_t[6];
std::recursive_mutex g_network_topology_mutex;
enum em_op_class_type_t { em_op_class_type_none, em_op_class_type_current, em_op_class_type_capability,
                          em_op_class_type_preference };
struct em_op_class_id_t { mac_address_t ruid; em_op_class_type_t type; };
struct em_op_class_info_t { em_op_class_id_t id; unsigned int op_class; unsigned int channel; };
struct dm_easy_mesh_t {
    em_op_class_info_t ops[EM_MAX_OPCLASS];
    unsigned int m_num_opclass = 0;
    em_op_class_info_t *get_op_class_info(unsigned int i) { return &ops[i]; }
};
@FOR_RADIO@
static void mac(mac_address_t m, unsigned char last) { memset(m, 0x02, 6); m[5] = last; }
static void op(dm_easy_mesh_t &m, unsigned char ruid, em_op_class_type_t type, unsigned int cls)
{
    em_op_class_info_t &o = m.ops[m.m_num_opclass++];
    memset(&o, 0, sizeof(o));
    mac(o.id.ruid, ruid); o.id.type = type; o.op_class = cls;
}
static unsigned char of(dm_easy_mesh_t &m, unsigned char ruid, int channel)
{
    mac_address_t r;
    mac(r, ruid);
    return backhaul_op_class_for_radio(&m, r, channel);
}
int main()
{
    dm_easy_mesh_t pod;
    /* radio 0x20: a two-radio pod's radio B, 5 GHz only (EMOSA advertises 115, 124, 125) */
    op(pod, 0x20, em_op_class_type_capability, 115);
    op(pod, 0x20, em_op_class_type_capability, 124);
    op(pod, 0x20, em_op_class_type_capability, 125);
    op(pod, 0x20, em_op_class_type_current, 125);
    /* radio 0x21: 2.4 and 5 GHz; radio 0x22: 5 and 6 GHz; radio 0x23: 6 GHz only */
    op(pod, 0x21, em_op_class_type_capability, 81);
    op(pod, 0x21, em_op_class_type_capability, 115);
    op(pod, 0x22, em_op_class_type_capability, 125);
    op(pod, 0x22, em_op_class_type_capability, 131);
    op(pod, 0x23, em_op_class_type_capability, 131);
    /* radio 0x24: a current and a preference class only, no capability */
    op(pod, 0x24, em_op_class_type_current, 125);
    op(pod, 0x24, em_op_class_type_preference, 131);
    assert(of(pod, 0x20, 149) == 125);   /* a gateway's pod-backhaul BSS on 149 */
    assert(of(pod, 0x20, 165) == 125);
    assert(of(pod, 0x20, 36) == 115);
    assert(of(pod, 0x20, 1) == 0);       /* not a band this radio operates */
    assert(of(pod, 0x21, 1) == 81);      /* 1 is 6 GHz too, but this radio has no 6 GHz */
    assert(of(pod, 0x21, 149) == 125);
    assert(of(pod, 0x22, 149) == 0);     /* 5 and 6 GHz both have 149: refused, not guessed */
    assert(of(pod, 0x22, 37) == 131);
    assert(of(pod, 0x23, 149) == 131);
    assert(of(pod, 0x24, 149) == 0);     /* only capability rows count */
    assert(of(pod, 0x25, 149) == 0);     /* a radio the model has no rows for */
    for (int n : {-1, 0, 15, 34, 178, 234, 255}) assert(of(pod, 0x21, n) == 0 && of(pod, 0x22, n) == 0);
    return 0;
}
'''.replace("@FOR_RADIO@", for_radio)

with tempfile.TemporaryDirectory() as tmp:
    src, exe = Path(tmp) / "band.cpp", Path(tmp) / "band"
    src.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-O0", "-g", "-Wall", "-Wextra", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-o", str(exe), str(src)], check=True)
    subprocess.run([str(exe)], check=True)

derive = method.index("op_class = backhaul_op_class_of_channel(channel);")
fallback = method.index("op_class = backhaul_op_class_for_radio(dm, bsta->ruid.mac, channel);", derive)
refuse = method.index("if (op_class == 0)", fallback)
assert derive < fallback < refuse, "0249's derivation, then the station's radio, then the refusal"
assert "backhaul_target_operation(dm_ctrl, target_mac, &op_class, &op_channel)" in method, "the model first"
print("controller SteerWiFiBackhaul() unmodelled target on a shared number, by the station's radio: ok")
