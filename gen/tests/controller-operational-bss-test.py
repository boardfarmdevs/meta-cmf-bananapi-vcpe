#!/usr/bin/env python3
"""The AP Operational BSS TLV: a radio with no BSS accepted, every entry within the TLV's length.

Takes the fully patched unified-wifi-mesh source tree (0245). Compiles the check that
handle_ap_operational_bss() makes before reading the TLV against well-formed TLVs (a radio with
no BSS among them) and against ones whose radios or BSSes run past their length; then checks the
Topology Response's minimum is the header and the number of radios, the caller passes the length
in host order, and a new BSS checks EM_MAX_BSSS first.
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
handler = configuration.split("int em_configuration_t::handle_ap_operational_bss(unsigned char *buff, unsigned int len)", 1)
assert len(handler) == 2, "em_configuration_t::handle_ap_operational_bss"
check = re.search(r"    // the radios and BSSes the TLV declares within its length.*?\n    \}\n", handler[1], re.S)
assert check, "handle_ap_operational_bss checks the TLV's entries against its length first"

program = r'''
#include <cassert>
#include <cstddef>
#include <cstdio>
#include <vector>
#define em_printfout(...) ((void)0)
typedef unsigned char mac_address_t[6];
typedef struct { mac_address_t bssid; unsigned char ssid_len; char ssid[0]; } __attribute__((__packed__)) em_ap_operational_bss_t;
typedef struct { mac_address_t ruid; unsigned char bss_num; em_ap_operational_bss_t bss[0]; } __attribute__((__packed__)) em_ap_op_bss_radio_t;
typedef struct { unsigned char radios_num; em_ap_op_bss_radio_t radios[0]; } __attribute__((__packed__)) em_ap_op_bss_t;
static int check(unsigned char *buff, unsigned int len)
{
@CHECK@
    return 0;
}
static std::vector<unsigned char> tlv(std::vector<std::vector<int>> radios)
{
    /* each radio: its BSSes' SSID lengths */
    std::vector<unsigned char> v{static_cast<unsigned char>(radios.size())};
    for (auto &r : radios) {
        for (int i = 0; i < 6; i++) v.push_back(0x02);
        v.push_back(static_cast<unsigned char>(r.size()));
        for (int ssid : r) {
            for (int i = 0; i < 6; i++) v.push_back(0x82);
            v.push_back(static_cast<unsigned char>(ssid));
            for (int i = 0; i < ssid; i++) v.push_back('x');
        }
    }
    return v;
}
int main()
{
    auto none = tlv({{}});                 /* one radio operating no BSS: 8 bytes */
    assert(none.size() == 8 && check(none.data(), 8) == 0);
    auto two = tlv({{12, 0}, {}, {5}});    /* BSSes with and without an SSID, a radio with none */
    assert(check(two.data(), static_cast<unsigned int>(two.size())) == 0);
    assert(check(two.data(), static_cast<unsigned int>(two.size()) - 1) == -1);  /* the last SSID cut */
    auto empty = tlv({});
    assert(check(empty.data(), 1) == 0);
    assert(check(empty.data(), 0) == -1);
    auto claims = tlv({{3}});
    claims[0] = 2;                          /* two radios declared, one present */
    assert(check(claims.data(), static_cast<unsigned int>(claims.size())) == -1);
    auto bss = tlv({{3}});
    bss[7] = 4;                             /* four BSSes declared, one present */
    assert(check(bss.data(), static_cast<unsigned int>(bss.size())) == -1);
    return 0;
}
'''.replace("@CHECK@", check.group(0))

with tempfile.TemporaryDirectory() as tmp:
    src, exe = Path(tmp) / "opbss.cpp", Path(tmp) / "opbss"
    src.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-O0", "-Wall", "-Wno-zero-length-bounds", "-o", str(exe), str(src)],
                   check=True)
    subprocess.run([str(exe)], check=True)

message = (root / "src/em/em_msg.cpp").read_text()
topology = message.split("void em_msg_t::topo_resp()", 1)[1].split("\n}\n", 1)[0]
assert re.search(r"em_tlv_type_operational_bss, mandatory, \"17\.2\.4[^\"]*\", 4\)", topology), \
    "the Topology Response's AP Operational BSS minimum is the header and the number of radios"
assert "handle_ap_operational_bss(tlv->value, ntohs(tlv->len))" in configuration, \
    "the caller passes the TLV's length in host order"
appends = handler[1].split("\n}\n", 1)[0]
assert re.search(r"dm_bss == NULL && dm->get_num_bss\(\) >= EM_MAX_BSSS", appends), \
    "a new BSS checks EM_MAX_BSSS first"
print("controller operational BSS: ok")
