#!/usr/bin/env python3
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


parser = argparse.ArgumentParser(description="Compile native onboarding report state guards")
parser.add_argument("source_root", type=Path)
args = parser.parse_args()
guards = []
states = []
for path, pending, completed in (
    ("config/em_configuration.cpp", "agent_onewifi_bssconfig_ind", "agent_topo_synchronized"),
    ("config/em_configuration.cpp", "ctrl_topo_sync_pending", "ctrl_topo_synchronized"),
    ("capability/em_capability.cpp", "agent_topo_synchronized", "agent_ap_cap_report"),
    ("capability/em_capability.cpp", "ctrl_ap_cap_query_pending", "ctrl_ap_cap_report_received"),
    ("channel/em_channel.cpp", "ctrl_channel_query_pending", "ctrl_channel_queried"),
):
    source = (args.source_root / "src/em" / path).read_text()
    pattern = (r"if \(em->get_state\(\) == em_state_" + pending
               + r"\) \{\s*em->set_state\(em_state_" + completed + r"\);")
    matches = list(re.finditer(pattern, source))
    assert len(matches) == 1, (path, pending)
    assert source.count("em->set_state(em_state_" + completed + ");") == 1
    if path != "config/em_configuration.cpp":
        assert "\n    set_state(em_state_" + completed + ");" not in source
        assert "\n\tset_state(em_state_" + completed + ");" not in source
    assert "lock_commands()" in source
    guards.append(matches[0].group() + "\n}")
    for state in (pending, completed):
        if state not in states:
            states.append(state)
header = (args.source_root / "inc/em_agent.h").read_text()
getter = re.search(r"em_orch_t \*get_orch\(\) override \{ return m_orch; \}", header)
assert getter, "Agent must expose its real orchestrator rather than the base null getter"
program = "#include <cassert>\n#include <cstdio>\n"
program += "struct em_orch_t {}; struct Manager { virtual em_orch_t *get_orch() { return nullptr; } };\n"
program += "struct Agent : Manager { em_orch_t *m_orch; " + getter.group() + " };\n"
program += "enum { " + ", ".join("em_state_" + state for state in states) + " };\n"
program += "struct Radio { int state; unsigned short mid = 77; int get_state() { return state; } void set_state(int next) { state = next; } };\n"
for index, guard in enumerate(guards):
    program += f"void transition_{index}(Radio *em) {{\n{guard}\n}}\n"
program += "int main() {\n"
program += "em_orch_t orchestrator; Agent agent; agent.m_orch = &orchestrator; Manager *manager = &agent; assert(manager->get_orch() == &orchestrator);\n"
for index, guard in enumerate(guards):
    pending, completed = re.findall(r"em_state_\w+", guard)
    program += f"for (int current = -1; current < 400; current++) {{ Radio radio{{current}}; transition_{index}(&radio); assert(radio.state == (current == {pending} ? {completed} : current)); assert(radio.mid == 77); }}\n"
program += 'puts("PASS onboarding advances only expected states; runtime states and MIDs are preserved"); }\n'
with tempfile.TemporaryDirectory(prefix="onboarding-report-state-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2",
                    "-x", "c++", "-", "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
