"""Compile native recovery methods against deterministic bus/transport doubles.

Usage: python3 operating-channel-crash-recovery-test.py AGENT_CPP CHANNEL_CPP
The input sources must have 0190 and 0191 applied. No live services are used.
"""

from pathlib import Path
import re
import subprocess
import sys
import tempfile


def method(source, signature):
    match = re.search(re.escape(signature) + r'\(.*?\n\}', source, re.S)
    if match is None:
        raise ValueError(f'missing native method: {signature}')
    return match.group()


agent_source = Path(sys.argv[1]).read_text()
channel_source = Path(sys.argv[2]).read_text()
native_methods = '\n'.join([
    method(agent_source, 'void em_agent_t::handle_autoconfig_renew'),
    method(agent_source, 'bool em_agent_t::publish_initial_operating_channels'),
    method(agent_source, 'void em_agent_t::handle_2s_tick'),
    method(channel_source, 'int em_channel_t::handle_op_channel_report'),
])

program = r'''
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#define em_printfout(...) ((void)0)
#define WIFI_WEBCONFIG_GET_ASSOC "association-snapshot"
struct test_clock {
    using time_point = std::chrono::steady_clock::time_point;
    static time_point current;
    static time_point now() { return current; }
};
test_clock::time_point test_clock::current{};
constexpr int EM_MAX_CMD = 8;
enum { em_op_class_type_current = 1, em_op_class_type_capability = 2,
       db_cfg_type_op_class_list_update = 4, db_cfg_type_radio_list_update = 8,
       em_state_ctrl_channel_selected = 16, em_state_ctrl_configured = 32,
       em_state_agent_wsc_m2_pending = 100,
       em_state_agent_topo_synchronized = 101, em_state_agent_configured = 102,
       em_service_type_agent = 1, em_service_type_ctrl = 2,
       em_bus_event_type_sta_list = 1, bus_error_success = 0,
       bus_data_type_uint8 = 1, bus_data_type_uint16, bus_data_type_uint32,
       bus_data_type_int8, bus_data_type_int16, bus_data_type_int32 };
using mac_address_t = unsigned char[6];
using mac_addr_str_t = char[18];
using bus_error_t = int;
struct raw_data_t {
    int data_type = bus_data_type_uint32;
    union {
        unsigned char u8;
        unsigned short u16;
        unsigned int u32;
        signed char i8;
        short i16;
        int i32;
        unsigned char *bytes;
    } raw_data = {};
    unsigned int raw_data_len = 0;
};
struct bus_fixture {
    unsigned int channels[3] = {6, 36, 37};
    int fail_radio = -1;
    unsigned int reads = 0;
};
struct wifi_bus_desc_t {
    static int bus_data_get_fn(bus_fixture *bus, const char *path, raw_data_t *data) {
        if (std::strcmp(path, WIFI_WEBCONFIG_GET_ASSOC) == 0) {
            data->raw_data.bytes = static_cast<unsigned char *>(std::malloc(1));
            data->raw_data_len = 1;
            return bus_error_success;
        }
        unsigned int radio_number = 0;
        assert(std::sscanf(path, "Device.WiFi.Radio.%u.Channel", &radio_number) == 1);
        assert(radio_number >= 1 && radio_number <= 3);
        bus->reads++;
        if (bus->fail_radio == static_cast<int>(radio_number - 1)) return -1;
        data->raw_data.u32 = bus->channels[radio_number - 1];
        return bus_error_success;
    }
    static void bus_data_free_fn(raw_data_t *) {}
};
namespace util {
    std::string mac_to_string(unsigned char *) { return "radio"; }
}
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
struct dm_radio_t {
    mac_address_t address = {};
    unsigned char *get_radio_interface_mac() { return address; }
};
struct dm_easy_mesh_t {
    unsigned int m_num_opclass = 0, flags = 0, num_radios = 3;
    int commands = 1;
    dm_op_class_t m_op_class[16] = {};
    dm_radio_t radios[3];
    int analyze_autoconfig_renew(em_bus_event_t *, em_cmd_t **) { return commands; }
    unsigned int get_num_op_class() { return m_num_opclass; }
    unsigned int get_num_radios() { return num_radios; }
    dm_radio_t *get_radio(unsigned int index) { return &radios[index]; }
    em_op_class_info_t *get_op_class_info(unsigned int index) {
        return &m_op_class[index].m_op_class_info;
    }
    void set_num_op_class(unsigned int count) { m_num_opclass = count; }
    void set_db_cfg_param(unsigned int flag, const char *) { flags |= flag; }
    static void macbytes_to_string(unsigned char *, char *) {}
};
struct em_mgr_t { void *m_em_map = nullptr; };
struct em_op_channel_rprt_t {
    mac_address_t ruid;
    struct { unsigned char op_class, channel; } op_classes[1];
};
struct em_channel_t {
    dm_easy_mesh_t model;
    em_mgr_t manager;
    bool reachable = true;
    dm_easy_mesh_t *get_data_model() { return &model; }
    em_mgr_t *get_mgr() { return &manager; }
    int handle_op_channel_report(unsigned char *, unsigned int);
};
struct em_t {
    bool al = false, fail_send = false, drop_report = false;
    int service = em_service_type_agent, state = em_state_agent_configured;
    unsigned int index = 0, attempts = 0;
    dm_easy_mesh_t *model = nullptr;
    em_channel_t *receiver = nullptr;
    bool is_al_interface_em() { return al; }
    int get_service_type() { return service; }
    int get_state() { return state; }
    void set_state(int value) { state = value; }
    int send_operating_channel_report_msg() {
        attempts++;
        if (fail_send) return -1;
        if (!receiver->reachable || drop_report) return 1;
        em_op_channel_rprt_t report = {};
        auto &current = model->m_op_class[index].m_op_class_info;
        std::memcpy(report.ruid, current.id.ruid, sizeof(mac_address_t));
        report.op_classes[0].op_class = current.op_class;
        report.op_classes[0].channel = current.channel;
        assert(receiver->handle_op_channel_report(
            reinterpret_cast<unsigned char *>(&report), sizeof(report)) == 0);
        return 1;
    }
};
void *hash_map_get(void *, const char *) { return nullptr; }
void *hash_map_get_first(void *map) {
    auto &nodes = *static_cast<std::vector<em_t *> *>(map);
    return nodes.empty() ? nullptr : nodes.front();
}
void *hash_map_get_next(void *map, void *current) {
    auto &nodes = *static_cast<std::vector<em_t *> *>(map);
    for (unsigned int index = 0; index + 1 < nodes.size(); index++) {
        if (nodes[index] == current) return nodes[index + 1];
    }
    return nullptr;
}
struct em_agent_t {
    dm_easy_mesh_t m_data_model;
    em_orch_t orch;
    em_orch_t *m_orch = &orch;
    bool m_initial_op_channel_report_sent = false, bus_available = true;
    test_clock::time_point m_operating_channel_refresh_due{};
    unsigned int snapshots = 0;
    bus_fixture m_bus_hdl;
    wifi_bus_desc_t bus;
    em_channel_t receiver;
    em_t radio_nodes[3], al_node;
    std::vector<em_t *> nodes;
    void *m_em_map = &nodes;
    em_agent_t() {
        m_data_model.m_num_opclass = 3;
        const unsigned int classes[] = {81, 115, 131};
        al_node.al = true;
        nodes.push_back(&al_node);
        for (unsigned int index = 0; index < 3; index++) {
            auto &current = m_data_model.m_op_class[index].m_op_class_info;
            current.id.type = em_op_class_type_current;
            current.id.ruid[5] = index + 1;
            current.id.op_class = current.op_class = classes[index];
            current.channel = m_bus_hdl.channels[index];
            m_data_model.radios[index].address[5] = index + 1;
            radio_nodes[index].index = index;
            radio_nodes[index].model = &m_data_model;
            radio_nodes[index].receiver = &receiver;
            nodes.push_back(&radio_nodes[index]);
        }
    }
    wifi_bus_desc_t *get_bus_descriptor() { return bus_available ? &bus : nullptr; }
    void io_process(int, unsigned char *, unsigned int) { snapshots++; }
    bool publish_initial_operating_channels();
    void handle_autoconfig_renew(em_bus_event_t *);
    void handle_2s_tick();
    void ticks(unsigned int count) {
        for (unsigned int index = 0; index < count; index++) {
            test_clock::current += std::chrono::seconds(2);
            handle_2s_tick();
        }
    }
    unsigned int attempts() {
        return radio_nodes[0].attempts + radio_nodes[1].attempts + radio_nodes[2].attempts;
    }
    void check_channels() {
        assert(receiver.model.get_num_op_class() == 3);
        for (unsigned int index = 0; index < 3; index++) {
            auto &current = receiver.model.m_op_class[index].m_op_class_info;
            assert(current.id.ruid[5] == index + 1);
            assert(current.channel == m_bus_hdl.channels[index]);
        }
        assert(al_node.attempts == 0);
    }
};
''' + native_methods + r'''
void check_lost_renew() {
    em_agent_t agent;
    agent.ticks(1);
    agent.check_channels();
    agent.receiver.model.m_num_opclass = 0;
    agent.m_bus_hdl.channels[0] = 1;
    agent.m_bus_hdl.channels[1] = 44;
    agent.m_bus_hdl.channels[2] = 53;
    agent.ticks(14);
    assert(agent.attempts() == 3);
    assert(agent.m_bus_hdl.reads == 3);
    agent.ticks(1);
    agent.check_channels();
    assert(agent.attempts() == 6 && agent.m_bus_hdl.reads == 6);
    for (unsigned int index = 0; index < 3; index++) {
        assert(agent.radio_nodes[index].get_state() == em_state_agent_configured);
    }
}
void check_unacknowledged_reports() {
    em_agent_t agent;
    agent.receiver.reachable = false;
    agent.ticks(1);
    assert(agent.m_initial_op_channel_report_sent);
    assert(agent.receiver.model.get_num_op_class() == 0);
    agent.ticks(60);
    assert(agent.attempts() == 15);
    agent.receiver.reachable = true;
    agent.radio_nodes[2].drop_report = true;
    agent.ticks(15);
    assert(agent.receiver.model.get_num_op_class() == 2);
    assert(agent.m_initial_op_channel_report_sent);
    agent.radio_nodes[2].drop_report = false;
    agent.ticks(15);
    agent.check_channels();
}
void check_renew_admission() {
    for (unsigned int failure = 0; failure < 3; failure++) {
        em_agent_t agent;
        em_bus_event_t event;
        agent.ticks(1);
        agent.receiver.model.m_num_opclass = 0;
        agent.orch.busy = failure == 0;
        agent.m_data_model.commands = failure == 1 ? 0 : 1;
        agent.orch.accepted = failure == 2 ? 0 : 1;
        agent.handle_autoconfig_renew(&event);
        assert(agent.m_initial_op_channel_report_sent);
        agent.ticks(15);
        agent.check_channels();
        agent.orch.busy = false;
        agent.m_data_model.commands = agent.orch.accepted = 1;
        agent.receiver.model.m_num_opclass = 0;
        agent.handle_autoconfig_renew(&event);
        assert(!agent.m_initial_op_channel_report_sent);
        agent.ticks(1);
        agent.check_channels();
        assert(agent.m_operating_channel_refresh_due == test_clock::now() + std::chrono::seconds(30));
    }
}
void check_retry_without_starving_snapshots() {
    em_agent_t agent;
    agent.ticks(1);
    agent.receiver.model.m_num_opclass = 0;
    agent.m_bus_hdl.fail_radio = 1;
    const unsigned int before_snapshots = agent.snapshots;
    agent.ticks(60);
    assert(agent.attempts() == 3);
    assert(agent.m_initial_op_channel_report_sent);
    assert(agent.snapshots == before_snapshots + 4);
    assert(agent.m_operating_channel_refresh_due <= test_clock::now());
    agent.m_bus_hdl.fail_radio = -1;
    agent.radio_nodes[2].fail_send = true;
    agent.ticks(1);
    assert(agent.receiver.model.get_num_op_class() == 2);
    agent.radio_nodes[2].fail_send = false;
    agent.ticks(1);
    agent.check_channels();
    assert(agent.m_operating_channel_refresh_due == test_clock::now() + std::chrono::seconds(30));
    assert(agent.attempts() == 9);
}
void check_readiness_and_authority() {
    for (unsigned int failure = 0; failure < 7; failure++) {
        em_agent_t agent;
        if (failure == 0) agent.bus_available = false;
        if (failure == 1) agent.m_bus_hdl.channels[2] = 0;
        if (failure == 2) agent.m_data_model.m_num_opclass = 2;
        if (failure == 3) agent.radio_nodes[2].state = em_state_agent_wsc_m2_pending;
        if (failure == 4) agent.nodes.pop_back();
        if (failure == 5) agent.radio_nodes[2].service = em_service_type_ctrl;
        if (failure == 6) {
            agent.nodes.clear();
            agent.m_data_model.num_radios = 0;
        }
        agent.ticks(20);
        assert(!agent.m_initial_op_channel_report_sent);
        assert(agent.attempts() == 0);
        assert(agent.receiver.model.get_num_op_class() == 0);
        assert(agent.snapshots == 0);
    }
    em_agent_t agent;
    agent.radio_nodes[2].state = em_state_agent_wsc_m2_pending;
    agent.ticks(20);
    agent.radio_nodes[2].state = em_state_agent_topo_synchronized;
    agent.ticks(1);
    agent.check_channels();
    assert(agent.radio_nodes[2].state == em_state_agent_topo_synchronized);
}
int main(int count, char **arguments) {
    assert(count == 2);
    const std::string scenario = arguments[1];
    if (scenario == "lost-renew") check_lost_renew();
    else if (scenario == "unacknowledged-reports") check_unacknowledged_reports();
    else if (scenario == "renew-admission") check_renew_admission();
    else if (scenario == "retry-and-association-refresh") check_retry_without_starving_snapshots();
    else if (scenario == "readiness-and-authority") check_readiness_and_authority();
    else return 2;
    std::printf("PASS: %s\n", arguments[1]);
}
'''

program = program.replace('std::chrono::steady_clock::now()', 'test_clock::now()')

with tempfile.TemporaryDirectory(prefix='operating-channel-crash-recovery-') as temporary:
    executable = Path(temporary) / 'test'
    subprocess.run([
        'g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
        '-Wno-unused-parameter', '-x', 'c++', '-', '-o', str(executable),
    ], input=program, text=True, check=True)
    for scenario in [
        'lost-renew', 'unacknowledged-reports', 'renew-admission',
        'retry-and-association-refresh', 'readiness-and-authority',
    ]:
        subprocess.run([str(executable), scenario], check=True)
