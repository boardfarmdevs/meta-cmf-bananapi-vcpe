#!/usr/bin/env python3
"""A policy ACK configures the radio whose request it answers and the agent's radios that sent
none (0226), not one with a request of its own outstanding (0252). With em.cpp as a second
argument: a radio entering set_policy_pending starts with no request outstanding (0252)."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile


source = Path(sys.argv[1]).read_text()
if len(sys.argv) > 2:
    em_source = Path(sys.argv[2]).read_text()
    entries = re.findall(r"(.*\n.*\n)\s*m_sm\.set_state\(em_state_ctrl_set_policy_pending\);", em_source)
    assert len(entries) == 2, entries
    for before in entries:
        assert "m_policy_req_msg_id = 0;" in before, before
start = source.index("int em_policy_cfg_t::handle_1905_ack(")
implementation = source[start:source.index("\n}\n", start) + 3]
program = r'''
#include <arpa/inet.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <vector>
using mac_address_t = unsigned char[6];
constexpr int em_state_ctrl_configured = 1, em_state_ctrl_set_policy_pending = 2;
struct __attribute__((packed)) em_raw_hdr_t { mac_address_t dst, src; unsigned short ether_type; };
struct __attribute__((packed)) em_cmdu_t { unsigned char version, reserved; unsigned short type, id; unsigned char fragment, flags; };
void em_printfout(const char *, ...) {}
enum { EM_CONF };
void em_debug(int, const char *, ...) {}
#define em_util_dbg_print(module, ...) em_debug(module, __VA_ARGS__)
struct em_orch_t {
    std::recursive_mutex mutex;
    std::unique_lock<std::recursive_mutex> lock_commands() {
        return std::unique_lock<std::recursive_mutex>(mutex);
    }
};
struct em_t {
    int state;
    unsigned short m_policy_req_msg_id, candidate_mid, steering_mid;
    int get_state() { return state; }
    void set_state(int value) { state = value; }
};
struct Manager {
    em_orch_t orchestrator;
    em_orch_t *available = &orchestrator;
    std::vector<em_t *> radios;
    mac_address_t agent = {2,0,0,0,1,0x20};
    em_orch_t *get_orch() { return available; }
    void get_all_em_for_al_mac(unsigned char *source, std::vector<em_t *> &result) {
        if (memcmp(source, agent, 6) == 0) result = radios;
    }
};
struct em_policy_cfg_t {
    Manager manager;
    Manager *get_mgr() { return &manager; }
    int handle_1905_ack(unsigned char *, unsigned int);
};
''' + implementation + r'''
int main() {
    em_policy_cfg_t policy;
    unsigned char frame[sizeof(em_raw_hdr_t) + sizeof(em_cmdu_t)]{};
    auto *header = reinterpret_cast<em_raw_hdr_t *>(frame);
    auto *cmdu = reinterpret_cast<em_cmdu_t *>(frame + sizeof(em_raw_hdr_t));
    memcpy(header->src, policy.manager.agent, 6);
    cmdu->id = htons(42);
    for (int pending = 3; pending < 20; pending++) {
        em_t owner{em_state_ctrl_set_policy_pending, 42, 0, 0};
        em_t sibling{pending, 0, 123, 456};
        em_t other_policy{em_state_ctrl_set_policy_pending, 99, 0, 0};
        em_t waiting{em_state_ctrl_set_policy_pending, 0, 0, 0};    // sent nothing (0226)
        policy.manager.radios = {&sibling, &other_policy, &waiting, &owner};
        assert(policy.handle_1905_ack(frame, sizeof(frame)) == 0);
        assert(owner.state == em_state_ctrl_configured && owner.m_policy_req_msg_id == 0);
        assert(sibling.state == pending && sibling.candidate_mid == 123 && sibling.steering_mid == 456);
        // its own request outstanding: only that request's ACK configures it (0252)
        assert(other_policy.state == em_state_ctrl_set_policy_pending && other_policy.m_policy_req_msg_id == 99);
        assert(waiting.state == em_state_ctrl_configured && waiting.m_policy_req_msg_id == 0);
        assert(policy.handle_1905_ack(frame, sizeof(frame)) == 0);
        assert(sibling.state == pending && other_policy.state == em_state_ctrl_set_policy_pending);
        owner = {em_state_ctrl_set_policy_pending, 42, 0, 0};
        header->src[4] = 9;
        assert(policy.handle_1905_ack(frame, sizeof(frame)) == 0);
        assert(owner.state == em_state_ctrl_set_policy_pending && owner.m_policy_req_msg_id == 42);
        memcpy(header->src, policy.manager.agent, 6);
        cmdu->id = htons(77);
        assert(policy.handle_1905_ack(frame, sizeof(frame)) == 0);
        assert(owner.state == em_state_ctrl_set_policy_pending && owner.m_policy_req_msg_id == 42);
        cmdu->id = htons(42);
    }
    policy.manager.available = nullptr;
    assert(policy.handle_1905_ack(frame, sizeof(frame)) == -1);
    puts("PASS policy ACK source/MID isolation preserves sibling candidate, steering and policy commands");
}
'''
with tempfile.TemporaryDirectory(prefix="policy-ack-ownership-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2", "-pthread",
                    "-x", "c++", "-", "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
