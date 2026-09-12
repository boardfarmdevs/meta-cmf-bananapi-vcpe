#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile


root = Path(sys.argv[1])
orchestration = (root / "src/orch/em_orch_agent.cpp").read_text()
start = orchestration.index("bool em_orch_agent_t::is_em_ready_for_orch_exec(")
start = orchestration.index("    } else if (pcmd->m_type == em_cmd_type_unassoc_sta_result) {", start)
guard = orchestration[start + len("    } else if (pcmd->m_type == em_cmd_type_unassoc_sta_result) {"):
                      orchestration.index("\n    }\n", start)]
source = (root / "src/em/em.cpp").read_text()
start = source.index("        case em_cmd_type_unassoc_sta_result: {", source.index("void em_t::orch_execute("))
branch = source[start:source.index("        case em_cmd_type_unassoc_sta_query:", start)]
shared = (root / "src/orch/em_orch.cpp").read_text()
start = shared.index("bool em_orch_t::orchestrate(")
assert shared.index("lock_commands()", start) < shared.index("em->orch_execute(pcmd)", start)
start = shared.index("bool em_orch_t::eligible_for_active(")
assert "em->get_orch_state() != em_orch_state_idle" in shared[start:shared.index("\n}\n", start)]
program = r"""
#include <cassert>
#include <cstdio>
using em_state_t = int;
enum { em_cmd_type_unassoc_sta_result, em_state_agent_topo_synchronized,
       em_state_agent_configured, em_state_agent_unassoc_sta_metrics_report_pending,
       em_orch_state_fini };
struct StateMachine {
    int state;
    int get_state() { return state; }
    void set_state(int value) { state = value; }
};
struct Command { int m_type; };
struct em_metrics_t {
    StateMachine m_sm;
    int replies = 0;
    unsigned short query_mid = 699;
    void process_agent_state() {
        assert(m_sm.get_state() == em_state_agent_unassoc_sta_metrics_report_pending);
        replies++;
        m_sm.set_state(em_state_agent_configured);
    }
};
struct Radio : em_metrics_t {
    int m_orch_state = -1;
    int get_state() { return m_sm.get_state(); }
    void execute(int kind) {
        switch (kind) {
""" + branch + r"""
        default: break;
        }
    }
};
bool ready(Command *pcmd, Radio *em) {
    (void)em;
    if (pcmd->m_type != em_cmd_type_unassoc_sta_result) return false;
""" + guard + r"""
    return false;
}
int main() {
    Command command{em_cmd_type_unassoc_sta_result};
    for (int state = 0; state < 400; state++) {
        Radio radio;
        radio.m_sm.set_state(state);
        assert(ready(&command, &radio));
        radio.execute(command.m_type);
        assert(radio.replies == 1 && radio.query_mid == 699);
        assert(radio.get_state() == state && radio.m_orch_state == em_orch_state_fini);
    }
    puts("PASS candidate callbacks complete once across onboarding/runtime states; MID, state and radio exclusion retained");
}
"""
with tempfile.TemporaryDirectory(prefix="unassoc-result-state-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                    "-x", "c++", "-", "-o", str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
