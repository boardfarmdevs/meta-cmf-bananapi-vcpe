#!/usr/bin/env python3
import argparse
from pathlib import Path
import subprocess
import tempfile


parser = argparse.ArgumentParser(description="Compile native client-report state gates and association radio admission")
parser.add_argument("source_root", type=Path)
args = parser.parse_args()
transitions = []
for path, name, pending, completed in (
    ("src/em/metrics/em_metrics.cpp", "handle_associated_sta_link_metrics_resp",
     "em_state_ctrl_sta_link_metrics_pending", "em_state_ctrl_configured"),
    ("src/em/capability/em_capability.cpp", "handle_client_cap_report",
     "em_state_ctrl_sta_cap_pending", "em_state_ctrl_sta_cap_confirmed"),
):
    source = (args.source_root / path).read_text()
    start = source.index("::" + name + "(")
    body = source[start:source.index("\n}\n", start)]
    guard_start = body.index("    if (get_state() == " + pending + ") {")
    guard = body[guard_start:body.index("\n    }", guard_start) + 6]
    assert body.index("auto command_lock = orch->lock_commands();") < guard_start
    assert body.count("set_state(") == 1
    assert "set_state(" + completed + ")" in guard
    transitions.append("void " + name + "() {\n" + guard + "\n}")

orchestrator = (args.source_root / "src/orch/em_orch_ctrl.cpp").read_text()
start = orchestrator.index("            case em_cmd_type_sta_assoc:", orchestrator.index("unsigned int em_orch_ctrl_t::build_candidates"))
admission = orchestrator[start:orchestrator.index("            case em_cmd_type_sta_link_metrics:", start)]
program = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
using mac_address_t = unsigned char[6];
constexpr int em_state_ctrl_configured = 1, em_state_ctrl_sta_link_metrics_pending = 2;
constexpr int em_state_ctrl_sta_cap_pending = 3, em_state_ctrl_sta_cap_confirmed = 4;
constexpr int em_cmd_type_sta_assoc = 1;
struct State {
    int current = 0;
    unsigned short candidate_mid = 42;
    int get_state() { return current; }
    void set_state(int value) { current = value; }
''' + "\n".join(transitions) + r'''
};
struct Mac { mac_address_t mac; };
struct Bss { struct { Mac bssid, ruid; } m_bss_info; };
struct dm_easy_mesh_t {
    unsigned int m_num_bss = 1;
    Bss m_bss[1] = {{{{{2,0,0,0,8,1}}, {{2,0,0,0,8,0}}}}};
    mac_address_t agent = {2,0,0,0,8,0x20};
    unsigned char *get_agent_al_interface_mac() { return agent; }
    static void string_to_macbytes(const char *value, unsigned char *output) {
        unsigned int bytes[6];
        assert(sscanf(value, "%x:%x:%x:%x:%x:%x", &bytes[0], &bytes[1], &bytes[2], &bytes[3], &bytes[4], &bytes[5]) == 6);
        for (unsigned int index = 0; index < 6; index++) output[index] = bytes[index];
    }
};
struct em_t {
    dm_easy_mesh_t *model;
    mac_address_t ruid = {2,0,0,0,8,0};
    bool al = false;
    dm_easy_mesh_t *get_data_model() { return model; }
    unsigned char *get_radio_interface_mac() { return ruid; }
    bool is_al_interface_em() { return al; }
};
void queue_push(std::vector<em_t *> *queue, em_t *radio) { queue->push_back(radio); }
struct em_cmd_t {
    struct { struct { struct { const char *args[3]; } args; } u; } m_param = {{{{"02:00:00:00:08:20", "02:00:00:00:08:01", "02:00:00:00:03:00"}}}};
    std::vector<em_t *> candidates;
    std::vector<em_t *> *m_em_candidates = &candidates;
};
unsigned int admit(em_cmd_t *pcmd, const std::vector<em_t *> &radios) {
    unsigned int count = 0;
    std::vector<em_t *> sta_assoc_fallback_ems;
    dm_easy_mesh_t *dm;
    mac_address_t dev_mac, bss_mac;
    unsigned int i;
    for (auto *em : radios) {
        switch (em_cmd_type_sta_assoc) {
''' + admission + r'''
        }
    }
    return count;
}
int main() {
    for (int pending = 0; pending < 20; pending++) {
        State radio;
        radio.current = pending;
        radio.handle_associated_sta_link_metrics_resp();
        assert(radio.current == (pending == em_state_ctrl_sta_link_metrics_pending ? em_state_ctrl_configured : pending));
        assert(radio.candidate_mid == 42);
        radio.current = pending;
        radio.handle_client_cap_report();
        assert(radio.current == (pending == em_state_ctrl_sta_cap_pending ? em_state_ctrl_sta_cap_confirmed : pending));
        assert(radio.candidate_mid == 42);
    }
    dm_easy_mesh_t agent, foreign_agent;
    foreign_agent.agent[4] = 9;
    em_t owner{&agent}, sibling{&agent}, foreign{&foreign_agent}, al{&agent};
    sibling.ruid[5] = 2;
    al.al = true;
    em_cmd_t command;
    assert(admit(&command, {&sibling, &foreign, &al, &owner}) == 1);
    assert(command.candidates.size() == 1 && command.candidates.front() == &owner);
    command.candidates.clear();
    assert(admit(&command, {&sibling, &foreign, &al}) == 0);
    puts("PASS late client reports preserve unrelated states/MIDs; association admits exact AL/BSSID/RUID only");
}
'''
with tempfile.TemporaryDirectory(prefix="client-report-state-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2",
                    "-x", "c++", "-", "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
