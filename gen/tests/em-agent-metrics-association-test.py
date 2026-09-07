#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile


source = Path(sys.argv[1]).read_text()
start = source.index("void em_orch_agent_t::update_sta_link_metrics(")
end = source.index("\n}\n", start) + 3
implementation = source[start:end]
metrics_branch = source[source.index("case dm_orch_type_sta_link_metrics:"):]
assert "update_sta_link_metrics(*em_sta, sta->m_sta_info);" in metrics_branch

program = r"""
#include <cassert>
#include <cstdint>
struct em_sta_info_t {
    bool associated;
    unsigned int last_conn_time;
    uint64_t assoc_start_boottime_sec;
    unsigned int rcpi;
    unsigned int est_dl_rate;
};
class em_orch_agent_t {
public:
    static void update_sta_link_metrics(em_sta_info_t &, const em_sta_info_t &);
};
""" + implementation + r"""
int main() {
    em_sta_info_t current{true, 42, 1000, 100, 100};
    em_sta_info_t sample{false, 0, 0, 132, 7200};
    for (unsigned int repeat = 0; repeat < 10; repeat++) {
        em_orch_agent_t::update_sta_link_metrics(current, sample);
        assert(current.associated);
        assert(current.last_conn_time == 42);
        assert(current.assoc_start_boottime_sec == 1000);
        assert(current.rcpi == 132 && current.est_dl_rate == 7200);
    }
    current = {true, 1, 1041, 0, 0};
    sample = {true, 42, 1000, 132, 7200};
    em_orch_agent_t::update_sta_link_metrics(current, sample);
    assert(current.last_conn_time == 1);
    assert(current.assoc_start_boottime_sec == 1041);
    current = {false, 0, 0, 0, 0};
    em_orch_agent_t::update_sta_link_metrics(current, sample);
    assert(!current.associated);
    assert(current.last_conn_time == 0);
    assert(current.assoc_start_boottime_sec == 0);
}
"""
with tempfile.TemporaryDirectory(prefix="agent-metrics-test-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                    "-x", "c++", "-", "-o", str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
print("PASS: production metrics merge preserves association ownership, clock and reconnect epoch")
