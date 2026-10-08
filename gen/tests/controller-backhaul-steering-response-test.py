#!/usr/bin/env python3
"""A Backhaul Steering Response that names another of the agent's stations (0250).

Takes the fully patched unified-wifi-mesh source tree. Compiles the controller's native backhaul
frame handler against its own state (em_ctrl.h) and plays the responses to an outstanding
request:
- from the agent asked, for the request's target, under another MID and naming the agent's
  station on the target's band (EasyMesh 17.2.33: the station associated after the move): taken,
  success, that station kept;
- the same naming the requested station under the request's MID: taken, no other station kept;
- from another agent, or for another target: not taken;
- a failure naming another station: the request ends and the agent is marked uncertain.
Then checks the tick verifies a move by the requested station or the one the response named.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile


parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("source_root", type=Path)
args = parser.parse_args()
root = args.source_root
source = (root / "src/ctrl/em_backhaul_ctrl.cpp").read_text()
handler = source[source.index("bool em_ctrl_t::handle_native_backhaul_frame"):]
header = (root / "inc/em_ctrl.h").read_text()
state = header[header.index("    struct backhaul_query_t"):header.index("    void handle_native_backhaul_tick();")]

program = r'''
#include "em_backhaul_policy.h"
#include "em_backhaul_wire.h"
#include "em_rooted_admission_probe.h"
#include <cassert>
#include <chrono>
#include <deque>
#include <mutex>
#include <iostream>
#define em_printfout(...) (void)0
struct em_t { int send_native_backhaul_frame(unsigned char *, unsigned int length) { return static_cast<int>(length); } };
struct __attribute__((packed)) em_assoc_link_metrics_t { unsigned char bytes[19]; };
struct __attribute__((packed)) em_unassoc_sta_metric_t { unsigned char bytes[12]; };
struct __attribute__((packed)) em_bh_steering_resp_t { unsigned char bytes[13]; };
enum {
    em_msg_type_1905_ack = 0x8000,
    em_msg_type_ap_metrics_rsp = 0x800c,
    em_msg_type_unassoc_sta_link_metrics_rsp = 0x8010,
    em_msg_type_bh_steering_rsp = 0x801a,
    em_tlv_type_assoc_sta_link_metric = 0x96,
    em_tlv_type_unassoc_sta_link_metric_rsp = 0x98,
    em_tlv_type_bh_steering_rsp = 0x9f
};
int64_t backhaul_now() { return 12000; }
std::string backhaul_mac(const unsigned char *bytes) { return std::string(reinterpret_cast<const char *>(bytes), 6); }
std::string backhaul_label(const std::string &mac) { return mac; }
class em_ctrl_t {
public:
STATE
    bool handle_native_backhaul_frame(unsigned char *data, unsigned int len, em_t *al_em);
};
HANDLER
int main() {
    const std::string control("\x02\x00\x00\x00\x00\x01", 6);
    const std::string parent("\x02\x00\x00\x00\x00\x02", 6);
    const std::string child("\x02\x00\x00\x00\x00\x03", 6);
    const std::string other("\x02\x00\x00\x00\x00\x05", 6);
    const std::string station_5("\x02\x00\x00\x00\x6d\x00", 6);
    const std::string station_24("\x02\x00\x00\x00\x6c\x00", 6);
    const std::string bssid("\x02\x00\x00\x4d\x06\x73", 6);
    const std::string target_bssid("\x72\x00\x00\x00\x6a\x00", 6);
    auto fresh = [&](em_ctrl_t &c) {
        c.m_backhaul_controller = control;
        c.m_backhaul_network.root = parent;
        c.m_backhaul_network.nodes[child] = {child, station_5, bssid, {}};
        c.m_backhaul_steer = {{child, station_5, bssid, target_bssid, 62, 92, 66}, 80, 11000, false};
    };
    auto reply = [&](const std::string &sta, const std::string &target, unsigned char result) {
        std::vector<unsigned char> value(sta.begin(), sta.end());
        value.insert(value.end(), target.begin(), target.end());
        value.push_back(result);
        return value;
    };
    auto send = [](em_ctrl_t &c, std::vector<unsigned char> packet) {
        return c.handle_native_backhaul_frame(packet.data(), static_cast<unsigned int>(packet.size()), nullptr);
    };
    {   /* the agent's 2.4 GHz station, another MID: the request's response */
        em_ctrl_t c; fresh(c);
        assert(send(c, em_backhaul::frame(control, child, 0x801a, 81, 0x9f, reply(station_24, target_bssid, 0))));
        assert(c.m_backhaul_steer.response && c.m_backhaul_steer.acknowledged);
        assert(c.m_backhaul_steer.associated == station_24 && c.m_backhaul_steer.mid == 80);
    }
    {   /* the requested station, the request's MID: as before, no other station */
        em_ctrl_t c; fresh(c);
        assert(send(c, em_backhaul::frame(control, child, 0x801a, 80, 0x9f, reply(station_5, target_bssid, 0))));
        assert(c.m_backhaul_steer.response && c.m_backhaul_steer.associated.empty());
    }
    {   /* another agent's response: not the request's */
        em_ctrl_t c; fresh(c);
        assert(!send(c, em_backhaul::frame(control, other, 0x801a, 80, 0x9f, reply(station_24, target_bssid, 0))));
        assert(!c.m_backhaul_steer.response && !c.m_backhaul_steer.acknowledged);
    }
    {   /* another target: the TLV is not the request's */
        em_ctrl_t c; fresh(c);
        send(c, em_backhaul::frame(control, child, 0x801a, 80, 0x9f, reply(station_24, bssid, 0)));
        assert(!c.m_backhaul_steer.response && !c.m_backhaul_steer.acknowledged && c.m_backhaul_steer.associated.empty());
    }
    {   /* a failure naming another station: the request ends, the agent is uncertain */
        em_ctrl_t c; fresh(c);
        assert(send(c, em_backhaul::frame(control, child, 0x801a, 81, 0x9f, reply(station_24, target_bssid, 1))));
        assert(c.m_backhaul_steer.mid == 0);
        assert(c.m_backhaul_uncertain.at(child).failures == 1);
        assert(c.m_backhaul_uncertain.at(child).request.target == target_bssid);
    }
    std::cout << "PASS: a Backhaul Steering Response is the request's by its sender and target, whatever its MID, and may name another of the agent's stations\n";
}
'''.replace("STATE", state).replace("HANDLER", handler)

with tempfile.TemporaryDirectory(prefix="backhaul-steering-response-") as temporary:
    executable = Path(temporary) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-pthread",
                    "-I", str(root / "inc"), "-x", "c++", "-", "-o", str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)

verification = source[source.index("        if (m_backhaul_steer.mid != 0) {"):]
verification = verification[:verification.index("if (verified || now - m_backhaul_steer.sent >= 15000)")]
assert "current->second.sta == m_backhaul_steer.associated" in verification, \
    "the tick verifies a move by the station the response named, too"
print("controller Backhaul Steering Response for another of the agent's stations: ok")
