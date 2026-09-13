#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start:offset + 1]
    raise ValueError(signature)


source_root = Path(sys.argv[1])
orchestration = (source_root / "src/orch/em_orch_ctrl.cpp").read_text()
policy = (source_root / "src/em/policy_cfg/em_policy_cfg.cpp").read_text()
cli = (source_root / "src/rdkb-cli/main.go").read_text()
readiness = function(orchestration, "bool em_orch_ctrl_t::is_em_ready_for_orch_exec(")
candidates = function(orchestration, "unsigned int em_orch_ctrl_t::build_candidates(")
candidates = function(candidates, "if (pcmd->m_type == em_cmd_type_set_policy)")
dispatch = function(policy, "void em_policy_cfg_t::process_ctrl_state(")
constants = sorted(set(re.findall(r"\bem_(?:cmd_type|state_ctrl|orch_state)_\w+", readiness + candidates + dispatch)))
constants.append("em_orch_state_idle")
program = r'''
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
#define em_printfout(...) ((void)0)
using mac_address_t = unsigned char[6];
enum { CONSTANTS };
struct dm_easy_mesh_t {
    mac_address_t mac{};
    unsigned char *get_agent_al_interface_mac() { return mac; }
};
struct em_t {
    int state = em_state_ctrl_configured;
    int orch = em_orch_state_idle;
    mac_address_t mac{};
    int get_state() { return state; }
    int get_orch_state() { return orch; }
    unsigned char *get_radio_interface_mac() { return mac; }
};
void queue_push(std::vector<em_t *> *queue, em_t *radio) { queue->push_back(radio); }
struct em_cmd_t {
    int m_type = em_cmd_type_set_policy;
    dm_easy_mesh_t model;
    std::vector<em_t *> candidates;
    std::vector<em_t *> *m_em_candidates = &candidates;
    dm_easy_mesh_t *get_data_model() { return &model; }
    int get_type() { return m_type; }
};
struct Manager {
    std::vector<em_t *> radios;
    void get_all_em_for_al_mac(unsigned char *, std::vector<em_t *> &result) { result = radios; }
};
struct em_orch_ctrl_t {
    Manager *m_mgr;
    bool is_em_ready_for_orch_exec(em_cmd_t *, em_t *);
    unsigned int build_candidates(em_cmd_t *);
};
struct em_policy_cfg_t : em_t {
    Manager *manager;
    em_cmd_t *command;
    unsigned sent = 0;
    unsigned short m_policy_req_msg_id = 0;
    Manager *get_mgr() { return manager; }
    em_cmd_t *get_current_cmd() { return command; }
    dm_easy_mesh_t *get_data_model() { return command->get_data_model(); }
    int send_policy_cfg_request_msg() { sent++; return 1; }
    void process_ctrl_state();
};
READINESS
unsigned int em_orch_ctrl_t::build_candidates(em_cmd_t *pcmd) {
    dm_easy_mesh_t *dm;
    unsigned int count = 0;
    CANDIDATES
    return 0;
}
DISPATCH
int main() {
    Manager manager;
    em_orch_ctrl_t orchestrator{&manager};
    em_cmd_t command;
    em_policy_cfg_t first, selected, sibling;
    for (auto radio : {&first, &selected, &sibling}) {
        radio->manager = &manager;
        radio->command = &command;
    }
    manager.radios = {&first, &selected, &sibling};
    first.state = em_state_ctrl_wsc_m2_sent;
    assert(orchestrator.build_candidates(&command) == 1);
    assert(command.candidates.front() == &selected);
    selected.state = em_state_ctrl_set_policy_pending;
    selected.process_ctrl_state();
    assert(selected.sent == 1 && first.sent == 0 && sibling.sent == 0);
    assert(first.state == em_state_ctrl_wsc_m2_sent);
    command.candidates.clear();
    selected.orch = em_orch_state_progress;
    assert(orchestrator.build_candidates(&command) == 1);
    assert(command.candidates.front() == &sibling);
    command.candidates.clear();
    first.state = em_state_ctrl_misconfigured;
    assert(orchestrator.is_em_ready_for_orch_exec(&command, &first));
    assert(orchestrator.build_candidates(&command) == 1);
    assert(command.candidates.front() == &first);
    command.candidates.clear();
    for (auto radio : manager.radios) radio->orch = em_orch_state_progress;
    assert(orchestrator.build_candidates(&command) == 1);
    assert(command.candidates.front() == &first);
    command.candidates.clear();
    manager.radios.clear();
    assert(orchestrator.build_candidates(&command) == 0);
    assert(command.candidates.empty());
    manager.radios = {&first, &selected, &sibling};
    command.m_type = em_cmd_type_em_config;
    for (auto radio : manager.radios) radio->state = em_state_ctrl_set_policy_pending;
    first.process_ctrl_state();
    selected.process_ctrl_state();
    sibling.process_ctrl_state();
    assert(first.sent == 1 && selected.sent == 1 && sibling.sent == 0);
}
'''.replace("CONSTANTS", ",".join(constants)).replace("READINESS", readiness).replace("CANDIDATES", candidates).replace("DISPATCH", dispatch)

submission = function(cli, "func submitWifiPolicyCommand(")
go_program = '''package main
import ("log"; "time")
''' + submission + r'''
func main() {
    for _, status := range []string{"", "Error_Not_Ready", "Error_Invalid_Input", "NoChange"} {
        calls := 0
        result := submitWifiPolicyCommand(func() string { calls++; return status }, time.Second)
        if result || calls != 1 { panic("non-admission accepted or retried") }
    }
    calls := 0
    result := submitWifiPolicyCommand(func() string {
        calls++
        if calls == 1 { return "Error_Prev_Cmd_In_Progress" }
        return "Success"
    }, time.Second)
    if !result || calls != 2 { panic("busy policy not retried to admission") }
    calls = 0
    result = submitWifiPolicyCommand(func() string {
        calls++
        return "Error_Prev_Cmd_In_Progress"
    }, 0)
    if result || calls != 1 { panic("busy retry exceeded budget") }
}
'''
with tempfile.TemporaryDirectory(prefix="policy-submission-") as temporary:
    directory = Path(temporary)
    executable = directory / "native"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-x", "c++", "-", "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
    (directory / "main.go").write_text(go_program)
    (directory / "go.mod").write_text("module policy_test\n\ngo 1.19\n")
    subprocess.run(["go", "run", "."], cwd=directory, check=True)
print("PASS selected policy owner, cold-state admission, unchanged onboarding and bounded truthful CLI submission")
