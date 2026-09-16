"""Run native manager demultiplexing and channel refresh against a controlled clock."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile

from native_policy_test_support import method


root = Path(sys.argv[1])
base = (root / 'inc/em_base.h').read_text()
constants = '\n'.join(re.findall(r'^#define EM_(?:MGR_TOUT|[125]_TOUT_MULT)\s+[^\n]+', base, re.M))
manager = method((root / 'src/em/em_mgr.cpp').read_text(), 'void em_mgr_t::handle_timeout')
agent = (root / 'src/agent/em_agent.cpp').read_text()
tick = method(agent, 'void em_agent_t::handle_2s_tick').split('    static unsigned int association_refresh_ticks', 1)[0] + '}\n'
channel = (root / 'src/em/channel/em_channel.cpp').read_text()
retry = method(channel, 'void em_channel_t::retry_operating_channel_report') if 'void em_channel_t::retry_operating_channel_report' in channel else 'void em_channel_t::retry_operating_channel_report() {}'
program = r'''
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <mutex>
#include <vector>
CONSTANTS
constexpr int em_service_type_agent = 1;
struct test_clock {
    using time_point = std::chrono::steady_clock::time_point;
    static time_point current;
    static time_point now() { return current; }
};
test_clock::time_point test_clock::current{};
long long millis() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(test_clock::now().time_since_epoch()).count();
}
struct em_channel_t {
    std::mutex m_operating_channel_report_mutex;
    std::vector<unsigned char> m_pending_operating_channel_report{1};
    test_clock::time_point m_operating_channel_retry_due = test_clock::now() + std::chrono::seconds(2);
    unsigned int m_operating_channel_retry_interval = 2;
    std::vector<long long> sends;
    bool operating_channel_report_peer_matches() { return !m_pending_operating_channel_report.empty(); }
    void send_frame(unsigned char *, unsigned int) { sends.push_back(millis()); }
    void retry_operating_channel_report();
};
struct em_t : em_channel_t {
    bool is_al_interface_em() { return false; }
    int get_service_type() { return em_service_type_agent; }
};
void *hash_map_get_first(void *map) { return map; }
void *hash_map_get_next(void *, void *) { return nullptr; }
struct em_mgr_t {
    unsigned int m_tick_demultiplex = 0;
    void handle_250ms_tick() {}
    void handle_1s_tick() {}
    void handle_5s_tick() {}
    virtual void handle_2s_tick() = 0;
    void handle_timeout();
};
struct em_agent_t : em_mgr_t {
    bool m_initial_op_channel_report_sent = false, ready = true;
    unsigned int m_operating_channel_refresh_ticks = 0;
    test_clock::time_point m_operating_channel_refresh_due{};
    em_t radio;
    void *m_em_map = &radio;
    std::vector<long long> publications;
    unsigned int attempts = 0;
    bool publish_initial_operating_channels() {
        attempts++;
        if (!ready) return false;
        publications.push_back(millis());
        return true;
    }
    void apply_pending_policy() {}
    void handle_2s_tick() override;
};
MANAGER
RETRY
TICK
void advance(em_agent_t &agent, unsigned int milliseconds) {
    for (unsigned int elapsed = 0; elapsed < milliseconds; elapsed += EM_MGR_TOUT) {
        test_clock::current += std::chrono::milliseconds(EM_MGR_TOUT);
        agent.handle_timeout();
    }
}
int main() {
    em_agent_t agent;
    advance(agent, 64000);
    assert((agent.publications == std::vector<long long>{2000, 32000, 62000}));
    std::puts("PASS: actual 250ms/5s-reset manager scheduler refreshes at 2/32/62s, not fifteen nominal-2s ticks");
    if (!agent.radio.sends.empty()) {
        assert((agent.radio.sends == std::vector<long long>{2000, 7000, 17000, 34000, 64000}));
        const auto sends = agent.radio.sends.size();
        for (unsigned int tick = 0; tick < 100; tick++) agent.handle_timeout();
        assert(agent.radio.sends.size() == sends);
        std::puts("PASS: retry deadlines use elapsed 2/4/8/16/30s; actual scheduler rounds to next opportunity; catch-up calls cannot accelerate retries");
    }
    agent.ready = false;
    advance(agent, 100000);
    assert(agent.m_initial_op_channel_report_sent && agent.publications.size() == 3);
    agent.ready = true;
    advance(agent, 3000);
    assert(agent.publications.size() == 4);
    const auto publications = agent.publications.size();
    for (unsigned int tick = 0; tick < 100; tick++) agent.handle_timeout();
    assert(agent.publications.size() == publications);
    test_clock::current += std::chrono::hours(1);
    for (unsigned int tick = 0; tick < 20; tick++) agent.handle_timeout();
    assert(agent.publications.size() == publications + 1);
    std::puts("PASS: failed refresh retries without resetting initial success; delayed handlers rebase deadlines without burst catch-up");
}
'''.replace('CONSTANTS', constants).replace('MANAGER', manager).replace(
    'RETRY', retry.replace('std::chrono::steady_clock::now()', 'test_clock::now()')).replace(
    'TICK', tick.replace('std::chrono::steady_clock::now()', 'test_clock::now()'))
with tempfile.TemporaryDirectory(prefix='agent-recovery-scheduler-') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', '-pthread',
                    '-x', 'c++', '-', '-o', str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
