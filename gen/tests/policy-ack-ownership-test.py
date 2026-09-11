#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile


source = Path(sys.argv[1]).read_text()
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
        policy.manager.radios = {&sibling, &other_policy, &owner};
        assert(policy.handle_1905_ack(frame, sizeof(frame)) == 0);
        assert(owner.state == em_state_ctrl_configured && owner.m_policy_req_msg_id == 0);
        assert(sibling.state == pending && sibling.candidate_mid == 123 && sibling.steering_mid == 456);
        assert(other_policy.state == em_state_ctrl_set_policy_pending && other_policy.m_policy_req_msg_id == 99);
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
