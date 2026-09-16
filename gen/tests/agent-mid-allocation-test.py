"""Exercise native MID allocation through the real manager declaration."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile


def method(source, signature):
    return re.search(re.escape(signature) + r'\(.*?\n\}', source, re.S).group()


root = Path(sys.argv[1])
header = (root / 'inc/em_mgr.h').read_text()
declaration = re.search(r'(?:virtual )?unsigned short get_next_msg_id\(\);', header).group()
base = method((root / 'src/em/em_mgr.cpp').read_text(), 'unsigned short em_mgr_t::get_next_msg_id')
agent = method((root / 'src/agent/em_agent.cpp').read_text(), 'unsigned short em_agent_t::get_next_msg_id')
program = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <thread>
#include <vector>
struct em_mgr_t {
    unsigned short m_msg_id = 0;
    DECLARATION
};
struct em_agent_t : em_mgr_t {
    std::atomic<unsigned short> m_agent_msg_id{0};
    unsigned short get_next_msg_id() override;
};
BASE
AGENT
int main() {
    for (unsigned int repetition = 0; repetition < 30; repetition++) {
        em_agent_t agent;
        em_mgr_t *manager = &agent;
        std::atomic<unsigned int> ready{0};
        std::atomic<bool> start{false};
        std::vector<std::vector<unsigned short>> results(8);
        std::vector<std::thread> workers;
        for (unsigned int worker = 0; worker < results.size(); worker++) {
            workers.emplace_back([&, worker]() {
                ready++;
                while (!start.load()) std::this_thread::yield();
                for (unsigned int request = 0; request < 4000; request++) {
                    results[worker].push_back(manager->get_next_msg_id());
                }
            });
        }
        while (ready.load() != results.size()) std::this_thread::yield();
        start = true;
        for (auto &worker : workers) worker.join();
        std::vector<unsigned short> identifiers;
        for (const auto &batch : results) identifiers.insert(identifiers.end(), batch.begin(), batch.end());
        std::sort(identifiers.begin(), identifiers.end());
        assert(identifiers.front() == 1 && identifiers.back() == 32000);
        assert(std::adjacent_find(identifiers.begin(), identifiers.end()) == identifiers.end());
        assert(agent.m_msg_id == 0);
    }
    em_agent_t agent;
    em_mgr_t *manager = &agent;
    agent.m_agent_msg_id = 65533;
    for (unsigned short expected : {65534, 65535, 1, 2}) assert(manager->get_next_msg_id() == expected);
    em_mgr_t controller;
    assert(controller.get_next_msg_id() == 1 && controller.get_next_msg_id() == 2);
    std::puts("PASS: 960000 concurrent native agent allocations through manager dispatch are unique per cycle; wrap skips zero; controller allocator unchanged");
}
'''.replace('DECLARATION', declaration).replace('BASE', base).replace('AGENT', agent)
with tempfile.TemporaryDirectory(prefix='agent-mid-allocation-') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['g++', '-std=c++11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                    '-x', 'c++', '-', '-o', str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
