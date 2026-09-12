#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile


root = Path(sys.argv[1])
source = (root / "src/orch/em_orch_agent.cpp").read_text()
start = source.index("bool em_orch_agent_t::is_em_ready_for_orch_exec(")
start = source.index("    } else if (pcmd->m_type == em_cmd_type_btm_report) {", start)
admission = source[start + len("    } else if (pcmd->m_type == em_cmd_type_btm_report) {"):
                   source.index("    } else if", start + 1)]
start = source.index("        case em_cmd_type_btm_report:", source.index("bool em_orch_agent_t::is_em_ready_for_orch_fini("))
completion = source[start + len("        case em_cmd_type_btm_report:"):
                    source.index("            break;", start)]
source = (root / "src/em/steering/em_steering.cpp").read_text()
start = source.index("int em_steering_t::handle_ack_msg(")
acknowledgement = source[start:source.index("\n}\n", start) + 3]
program = r"""
#include <arpa/inet.h>
#include <cassert>
#include <cstdio>
#include <cstring>
using em_state_t = int;
enum { em_state_agent_unconfigured, em_state_agent_topo_synchronized,
       em_state_agent_ap_cap_report, em_state_agent_configured,
       em_state_agent_steer_btm_res_pending, em_state_ctrl_steer_btm_req_ack_rcvd };
struct em_raw_hdr_t { unsigned char ethernet[14]; };
struct __attribute__((packed)) em_cmdu_t { unsigned short id; };
struct em_steering_t {
    int state = em_state_agent_ap_cap_report;
    int m_btm_report_prev_state = em_state_agent_unconfigured;
    unsigned short m_btm_report_msg_id = 0, m_client_steering_req_msg_id = 555;
    int get_state() { return state; }
    void set_state(int value) { state = value; }
    unsigned short get_btm_report_msg_id() { return m_btm_report_msg_id; }
    int handle_ack_msg(unsigned char *, unsigned int);
};
bool ready(em_steering_t *em) {
""" + admission + r"""
    return false;
}
bool finished(em_steering_t *em) {
""" + completion + r"""
    return false;
}
""" + acknowledgement + r"""
int main() {
    const int original_states[] = {em_state_agent_topo_synchronized,
                                  em_state_agent_ap_cap_report, em_state_agent_configured};
    for (int original: original_states) {
        em_steering_t radio;
        radio.state = original;
        assert(ready(&radio));
        radio.m_btm_report_prev_state = original;
        radio.state = em_state_agent_steer_btm_res_pending;
        assert(!ready(&radio) && !finished(&radio));
        radio.m_btm_report_msg_id = 717;
        unsigned char frame[sizeof(em_raw_hdr_t) + sizeof(em_cmdu_t)] = {};
        auto *cmdu = reinterpret_cast<em_cmdu_t *>(frame + sizeof(em_raw_hdr_t));
        cmdu->id = htons(710);
        assert(radio.handle_ack_msg(frame, sizeof(frame)) == -1);
        assert(radio.m_btm_report_msg_id == 717 && !finished(&radio));
        radio.state = original;
        assert(!finished(&radio));
        radio.state = em_state_agent_steer_btm_res_pending;
        cmdu->id = htons(717);
        assert(radio.handle_ack_msg(frame, sizeof(frame)) == 0);
        assert(radio.state == original && finished(&radio));
        assert(radio.m_btm_report_msg_id == 0 && radio.m_client_steering_req_msg_id == 555);
    }
    em_steering_t onboarding;
    onboarding.state = em_state_agent_unconfigured;
    assert(!ready(&onboarding));
    puts("PASS BTM report admission during AP capabilities; completion requires matching ACK and restores prior state");
}
"""
with tempfile.TemporaryDirectory(prefix="btm-report-state-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-parameter", "-x", "c++", "-", "-o", str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
