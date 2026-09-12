#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile


root = Path(sys.argv[1])
source = (root / "src/em/em.cpp").read_text()
start = source.index("        case em_cmd_type_unassoc_sta_query:", source.index("void em_t::orch_execute("))
branch = source[start:source.index("\n\tdefault:", start)]
orchestration = (root / "src/orch/em_orch.cpp").read_text()
start = orchestration.index("bool em_orch_t::orchestrate(")
assert orchestration.index("lock_commands()", start) < orchestration.index("em->orch_execute(pcmd)", start)
start = source.index("void em_t::handle_ctrl_state()")
assert source.index("lock_commands()", start) < source.index("em_metrics_t::process_ctrl_state()", start)
metrics = (root / "src/em/metrics/em_metrics.cpp").read_text()
start = metrics.index("int em_metrics_t::send_unassoc_sta_link_metrics_query_msg()")
assert metrics.index("em->get_unassoc_sta_query_msg_id() != 0", start) < metrics.index("send_frame(buff, len)", start)

program = r"""
#include <cassert>
enum { em_cmd_type_unassoc_sta_query, em_state_ctrl_unassoc_sta_link_metrics_pending };
struct state_machine {
    int state = -1;
    void set_state(int value) { state = value; }
};
struct em_metrics_t {
    state_machine m_sm;
    int dispatches = 0;
    bool sent = false;
    bool fail = false;
    void process_ctrl_state() {
        assert(m_sm.state == em_state_ctrl_unassoc_sta_link_metrics_pending);
        if (!sent) {
            dispatches++;
            sent = !fail;
        }
    }
};
struct em_t : em_metrics_t {
    void execute(int kind) {
        switch (kind) {
""" + branch + r"""
        default: break;
        }
    }
};
int main() {
    em_t radio;
    radio.execute(em_cmd_type_unassoc_sta_query);
    assert(radio.dispatches == 1 && radio.sent);
    radio.process_ctrl_state();
    assert(radio.dispatches == 1);
    em_t retry;
    retry.fail = true;
    retry.execute(em_cmd_type_unassoc_sta_query);
    assert(retry.dispatches == 1 && !retry.sent);
    retry.fail = false;
    retry.process_ctrl_state();
    assert(retry.dispatches == 2 && retry.sent);
}
"""
with tempfile.TemporaryDirectory(prefix="unassoc-dispatch-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                    "-x", "c++", "-", "-o", str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
print("PASS: immediate candidate dispatch under command ownership; timer retry and MID guard retained")
