#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile


source = (Path(sys.argv[1]) / "src/em/em.cpp").read_text()
start = source.index("        case em_cmd_type_sta_assoc:", source.index("void em_t::orch_execute("))
branch = source[start:source.index("\n        case em_cmd_type_channel_pref_query:", start)]
program = r"""
#include <cassert>
enum {
    em_cmd_type_sta_assoc, dm_orch_type_topo_sync, dm_orch_type_sta_cap,
    dm_orch_type_topo_publish, em_state_ctrl_configured,
    em_state_ctrl_topo_sync_pending, em_state_ctrl_sta_cap_pending,
    em_state_ctrl_topo_publish_pending
};
struct state_machine {
    int state = em_state_ctrl_configured;
    int get_state() { return state; }
    void set_state(int value) { state = value; }
};
struct em_capability_t {
    state_machine m_sm;
    int capability_queries = 0;
    void process_ctrl_state() {
        if (m_sm.state == em_state_ctrl_sta_cap_pending) capability_queries++;
    }
};
struct em_configuration_t {
    int configuration_dispatches = 0;
    void process_ctrl_state() { configuration_dispatches++; }
};
struct em_cmd_t {
    int operation;
    int get_orch_op() { return operation; }
};
struct em_t : em_capability_t, em_configuration_t {
    void execute(em_cmd_t *pcmd) {
        switch (em_cmd_type_sta_assoc) {
""" + branch + r"""
        default: break;
        }
    }
};
int main() {
    for (int operation : {dm_orch_type_topo_sync, dm_orch_type_sta_cap, dm_orch_type_topo_publish}) {
        em_t radio;
        em_cmd_t command{operation};
        radio.execute(&command);
        assert(radio.configuration_dispatches == 1);
        assert(radio.capability_queries == (operation == dm_orch_type_sta_cap ? 1 : 0));
        assert(radio.m_sm.state == (operation == dm_orch_type_topo_sync ? em_state_ctrl_topo_sync_pending :
            operation == dm_orch_type_sta_cap ? em_state_ctrl_sta_cap_pending : em_state_ctrl_topo_publish_pending));
    }
}
"""
program = "#include <initializer_list>\n" + program
with tempfile.TemporaryDirectory(prefix="association-dispatch-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-x", "c++", "-", "-o", str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
print("PASS: admitted association phases dispatch immediately without waiting for a protocol tick")
