#!/usr/bin/env python3
"""A DPP chirp's 1905 TLV length in host order, and a chirp without DPP answered by WSC while needed.

Takes the fully patched unified-wifi-mesh source tree (0244). Compiles the AP-Autoconfiguration
Search's chirp branch against a small model of the Easy Connect manager and the agent's radios:
the chirp's length reaches it in host order (a 34-byte chirp, not 8704); a chirp it handles ends
the search; one it does not handle is answered as a search without a chirp while one of the
agent's radios is not configured, and left unanswered once all are. Then checks no chirp length
goes through SWAP_LITTLE_ENDIAN().
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
provisioning = (root / "src/em/prov/em_provisioning.cpp").read_text()
search = configuration.split("Found DPP Chirp in Autoconfig Search (extended), forwarding to EC\");\n", 1)
assert len(search) == 2, "the AP-Autoconfiguration Search's chirp branch"
branch = re.search(r"\A(.*?)\n    \}\n", search[1], re.S)
assert branch, "the chirp branch's body"
header = (root / "inc/em_base.h").read_text()
states = re.search(r"(em_state_ctrl_unconfigured = 0x100,(?:\s*em_state_ctrl_\w+,)+)", header)
assert states, "the controller's states"

program = r'''
#include <algorithm>
#include <arpa/inet.h>
#include <cassert>
#include <string>
#include <vector>
#define em_printfout(...) ((void)0)
enum { @STATES@ };
typedef unsigned char mac_address_t[6];
struct em_dpp_chirp_value_t { unsigned char hash[1]; };
struct em_tlv_t { unsigned char type; unsigned short len; unsigned char value[64]; } __attribute__((__packed__));
struct em_cmdu_t { unsigned short id; };
namespace util { std::string mac_to_string(const unsigned char *) { return ""; } }
struct em_t {
    int state;
    int get_state() { return state; }
};
struct em_mgr_t {
    std::vector<em_t *> radios;
    void get_all_em_for_al_mac(unsigned char *, std::vector<em_t *> &out) { out = radios; }
};
struct ec_manager_t {
    bool handles = false;
    size_t seen_len = 0;
    bool handle_autoconf_chirp(em_dpp_chirp_value_t *, size_t len, unsigned char *, unsigned short, bool)
    {
        seen_len = len;
        return handles;
    }
};
static em_mgr_t manager;
static em_mgr_t *get_mgr() { return &manager; }
static int search(ec_manager_t &ec_mgr, em_tlv_t *dpp_chirp_tlv, unsigned char *al_mac, em_cmdu_t *cmdu)
{
    bool peer_is_emplus = false;
    if (dpp_chirp_tlv) {
@BRANCH@
    }
    return 42; /* the search answered without a chirp */
}
int main()
{
    em_tlv_t chirp = {0x8d, htons(34), {0}};
    em_cmdu_t cmdu = {htons(7)};
    mac_address_t al = {2, 0, 0, 0, 0, 1};
    em_t configured_radio = {em_state_ctrl_configured}, new_radio = {em_state_ctrl_wsc_m1_pending},
         broken = {em_state_ctrl_misconfigured};
    ec_manager_t ec;
    ec.handles = true;
    assert(search(ec, &chirp, al, &cmdu) == 1 && ec.seen_len == 34);
    ec.handles = false;
    manager.radios = {};
    assert(search(ec, &chirp, al, &cmdu) == 42);     /* an agent the controller does not know yet */
    manager.radios = {&configured_radio, &new_radio};
    assert(search(ec, &chirp, al, &cmdu) == 42);     /* one radio still unconfigured */
    manager.radios = {&configured_radio, &broken};
    assert(search(ec, &chirp, al, &cmdu) == 42);     /* one misconfigured */
    manager.radios = {&configured_radio, &configured_radio};
    assert(search(ec, &chirp, al, &cmdu) == 0);      /* all configured: no response */
    assert(search(ec, nullptr, al, &cmdu) == 42);    /* no chirp */
    return 0;
}
'''.replace("@STATES@", states.group(1)).replace("@BRANCH@", branch.group(1))

with tempfile.TemporaryDirectory() as tmp:
    src, exe = Path(tmp) / "chirp.cpp", Path(tmp) / "chirp"
    src.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-O0", "-Wall", "-o", str(exe), str(src)], check=True)
    subprocess.run([str(exe)], check=True)

for name, text in (("em_configuration.cpp", configuration), ("em_provisioning.cpp", provisioning)):
    assert not re.search(r"SWAP_LITTLE_ENDIAN\((dpp_chirp_tlv|tlv)->len\)", text), \
        f"{name}: a 1905 TLV's length through SWAP_LITTLE_ENDIAN()"
assert "handle_autoconf_resp_chirp(reinterpret_cast<em_dpp_chirp_value_t*>(dpp_chirp_tlv->value), ntohs(dpp_chirp_tlv->len)" in configuration
assert "process_chirp_notification(chirp, ntohs(tlv->len)" in provisioning
print("controller chirp: ok")
