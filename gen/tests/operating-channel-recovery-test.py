from pathlib import Path
import re
import subprocess
import sys
import tempfile


agent = Path(sys.argv[1]).read_text()
channel = Path(sys.argv[2]).read_text()
renew = re.search(r'void em_agent_t::handle_autoconfig_renew\(.*?\n\}', agent, re.S).group()
tick = agent.split('void em_agent_t::handle_2s_tick()\n{', 1)[1].split(
    '    static unsigned int association_refresh_ticks', 1)[0]
merge = re.search(r'int em_channel_t::handle_op_channel_report\(.*?\n\}', channel, re.S).group()
program = r'''
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstring>
#define em_printfout(...) ((void)0)
struct test_clock {
    using time_point = std::chrono::steady_clock::time_point;
    static time_point current;
    static time_point now() { return current; }
};
test_clock::time_point test_clock::current{};
constexpr bool sticky_renew = STICKY_RENEW;
constexpr int EM_MAX_CMD = 8;
enum { em_op_class_type_current = 1, em_op_class_type_capability = 2,
       db_cfg_type_op_class_list_update = 4, db_cfg_type_radio_list_update = 8,
       em_state_ctrl_channel_selected = 16, em_state_ctrl_configured = 32 };
using mac_address_t = unsigned char[6];
using mac_addr_str_t = char[18];
struct em_bus_event_t {};
struct em_cmd_t {};
struct em_orch_t {
    bool busy = false;
    int accepted = 1;
    bool is_cmd_type_in_progress(em_bus_event_t *) { return busy; }
    int submit_commands(em_cmd_t **, unsigned int) { return accepted; }
};
struct em_op_class_info_t {
    struct { mac_address_t ruid = {}; unsigned int type = 0, op_class = 0; } id;
    unsigned int op_class = 0, channel = 0;
};
struct dm_op_class_t { em_op_class_info_t m_op_class_info; };
struct dm_easy_mesh_t {
    unsigned int m_num_opclass = 0, flags = 0;
    int commands = 1;
    dm_op_class_t m_op_class[16] = {};
    int analyze_autoconfig_renew(em_bus_event_t *, em_cmd_t **) { return commands; }
    unsigned int get_num_op_class() { return m_num_opclass; }
    void set_num_op_class(unsigned int count) { m_num_opclass = count; }
    void set_db_cfg_param(unsigned int flag, const char *) { flags |= flag; }
    static void macbytes_to_string(unsigned char *, char *) {}
};
struct em_t {
    bool is_al_interface_em() { return false; }
    int get_service_type() { return 1; }
    void retry_operating_channel_report() {}
    int get_state() { return em_state_ctrl_configured; }
    void set_state(int) {}
};
struct em_mgr_t { void *m_em_map = nullptr; };
void *hash_map_get(void *, const char *) { return nullptr; }
void *hash_map_get_first(void *) { return nullptr; }
void *hash_map_get_next(void *, void *) { return nullptr; }
constexpr int em_service_type_agent = 1;
struct em_op_channel_rprt_t {
    mac_address_t ruid;
    struct { unsigned char op_class, channel; } op_classes[1];
};
struct em_channel_t {
    dm_easy_mesh_t model;
    em_mgr_t manager;
    dm_easy_mesh_t *get_data_model() { return &model; }
    em_mgr_t *get_mgr() { return &manager; }
    int handle_op_channel_report(unsigned char *, unsigned int);
};
struct em_agent_t {
    dm_easy_mesh_t m_data_model;
    em_orch_t orch;
    em_orch_t *m_orch = &orch;
    bool m_initial_op_channel_report_sent = true, ready = false;
    unsigned int m_operating_channel_refresh_ticks = 0;
    test_clock::time_point m_operating_channel_refresh_due = test_clock::now() + std::chrono::seconds(30);
    void *m_em_map = nullptr;
    void apply_pending_policy() {}
    unsigned int attempts = 0, reports = 0;
    bool publish_initial_operating_channels() {
        attempts++;
        if (!ready) return false;
        reports += 3;
        return true;
    }
    void handle_autoconfig_renew(em_bus_event_t *);
    void handle_2s_tick();
};
''' + renew + '\nvoid em_agent_t::handle_2s_tick() {\n' + tick + '\n}\n' + merge + r'''
void check_merge() {
    em_channel_t receiver;
    const unsigned int channels[] = {6, 36, 37};
    const unsigned int classes[] = {81, 115, 131};
    receiver.model.m_num_opclass = 3;
    for (unsigned int index = 0; index < 3; index++) {
        auto &row = receiver.model.m_op_class[index].m_op_class_info;
        row.id.ruid[5] = static_cast<unsigned char>(index + 1);
        row.id.type = em_op_class_type_current;
        row.id.op_class = row.op_class = classes[index];
        row.channel = channels[index];
    }
    const auto original_five = receiver.model.m_op_class[1];
    const auto original_six = receiver.model.m_op_class[2];
    for (unsigned char channel_number : {1, 6}) {
        em_op_channel_rprt_t report = {};
        report.ruid[5] = 1;
        report.op_classes[0].op_class = 81;
        report.op_classes[0].channel = channel_number;
        receiver.model.flags = 0;
        assert(receiver.handle_op_channel_report(reinterpret_cast<unsigned char *>(&report), sizeof(report)) == 0);
        assert(receiver.model.get_num_op_class() == 3);
        assert(receiver.model.m_op_class[0].m_op_class_info.channel == channel_number);
        assert(std::memcmp(&receiver.model.m_op_class[1], &original_five, sizeof(original_five)) == 0);
        assert(std::memcmp(&receiver.model.m_op_class[2], &original_six, sizeof(original_six)) == 0);
        assert(receiver.model.flags & db_cfg_type_op_class_list_update);
    }
}
void check_renew() {
    em_agent_t agent;
    em_bus_event_t event;
    agent.handle_2s_tick();
    assert(agent.attempts == 0);
    agent.handle_autoconfig_renew(&event);
    assert(agent.m_initial_op_channel_report_sent == sticky_renew);
    agent.handle_2s_tick();
    assert(agent.attempts == 1 && agent.reports == 0);
    assert(agent.m_initial_op_channel_report_sent == sticky_renew);
    agent.ready = true;
    agent.handle_2s_tick();
    assert(agent.m_initial_op_channel_report_sent && agent.reports == 3);
    agent.handle_2s_tick();
    assert(agent.reports == 3);
    agent.orch.busy = true;
    agent.handle_autoconfig_renew(&event);
    assert(agent.m_initial_op_channel_report_sent);
    agent.orch.busy = false;
    agent.m_data_model.commands = 0;
    agent.handle_autoconfig_renew(&event);
    assert(agent.m_initial_op_channel_report_sent);
    agent.m_data_model.commands = 1;
    agent.orch.accepted = 0;
    agent.handle_autoconfig_renew(&event);
    assert(agent.m_initial_op_channel_report_sent);
    agent.orch.accepted = 1;
    agent.handle_autoconfig_renew(&event);
    agent.handle_2s_tick();
    assert(agent.reports == 6);
}
void check_periodic() {
    em_agent_t agent;
    agent.ready = true;
    for (unsigned int tick = 0; tick < 14; tick++) {
        test_clock::current += std::chrono::seconds(2);
        agent.handle_2s_tick();
    }
    assert(agent.attempts == 0);
    test_clock::current += std::chrono::seconds(2);
    agent.handle_2s_tick();
    assert(agent.reports == 3);
    agent.ready = false;
    for (unsigned int tick = 0; tick < 45; tick++) {
        test_clock::current += std::chrono::seconds(2);
        agent.handle_2s_tick();
    }
    assert(agent.m_initial_op_channel_report_sent && agent.reports == 3);
    agent.ready = true;
    agent.handle_2s_tick();
    assert(agent.reports == 6);
}
int main(int count, char **) {
    check_merge();
    std::puts("PASS: single-radio channel reports preserve both unrelated bands");
    std::fflush(stdout);
    if (count == 1) {
        check_renew();
        std::puts("PASS: accepted renew rearms reports; unready radios retry; busy/failed renews preserve the latch");
        check_periodic();
        std::puts("PASS: periodic fallback repairs missing renew; failed refresh preserves association gate and retries without counter overflow");
    }
}
'''
program = program.replace('STICKY_RENEW', str('m_operating_channel_refresh_due = {}' in renew).lower())
program = program.replace('std::chrono::steady_clock::now()', 'test_clock::now()')
with tempfile.TemporaryDirectory(prefix='operating-channel-recovery-') as temporary:
    executable = Path(temporary) / 'test'
    subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                    '-include', 'initializer_list', '-x', 'c++', '-', '-o', str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable), *sys.argv[3:]], check=True)
