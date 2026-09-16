"""Extract policy receive/cache/queue boundaries; substitute only TLV decoding."""

from pathlib import Path
import subprocess
import sys
import tempfile

from native_policy_test_support import method, policy_types, received_policy_type


root = Path(sys.argv[1])
receive = method((root / 'src/em/policy_cfg/em_policy_cfg.cpp').read_text(),
                 'int em_policy_cfg_t::handle_policy_cfg_req')
prefix = receive.split('    em_policy_cfg_params_t policy;', 1)[0]
cache = receive.split('    static em_received_policy_t last_policy', 1)[1].split('    em_cmdu_t *cmdu', 1)[0]
suffix = receive.split('    received.policy = policy;', 1)[1]
implementation = prefix + '    em_policy_cfg_params_t policy;\n    static em_received_policy_t last_policy' + cache + r'''
    auto *cmdu = reinterpret_cast<em_cmdu_t *>(buff + sizeof(em_raw_hdr_t));
    if (interval >= 0) policy.metrics_policy.interval = interval;
    if (alarm >= 0) policy.vendor_policy.link_stats_alarm_policy_cfg.reporting_interval = alarm;
    received.policy = policy;
''' + suffix
program = r'''
#include <arpa/inet.h>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
#include <vector>
using mac_address_t = unsigned char[6];
using mac_addr_t = unsigned char[6];
TYPES
ENVELOPE
struct em_raw_hdr_t { mac_address_t dst, src; };
struct em_cmdu_t { unsigned short id; };
struct em_tlv_t { unsigned char type; };
constexpr int em_bus_event_type_set_policy = 1;
struct dm_easy_mesh_t {
    mac_address_t controller = {2,0,0,0,0,1}, agent = {2,0,0,0,0,2};
    unsigned char *get_ctl_mac() { return controller; }
    unsigned char *get_agent_al_interface_mac() { return agent; }
};
struct Manager {
    std::vector<em_received_policy_t> queued;
    void io_process(int, unsigned char *bytes, unsigned int size) {
        assert(size == sizeof(em_received_policy_t));
        em_received_policy_t received;
        memcpy(&received, bytes, size);
        queued.push_back(received);
    }
};
struct em_policy_cfg_t {
    dm_easy_mesh_t model;
    Manager *manager;
    int interval = -1, alarm = -1;
    unsigned int acks = 0;
    Manager *get_mgr() { return manager; }
    dm_easy_mesh_t *get_data_model() { return &model; }
    void send_1905_ack_message(unsigned short) { acks++; }
    int handle_policy_cfg_req(unsigned char *, unsigned int);
};
IMPLEMENTATION
int main() {
    Manager manager;
    em_policy_cfg_t first, second;
    first.manager = second.manager = &manager;
    unsigned char frame[sizeof(em_raw_hdr_t) + sizeof(em_cmdu_t) + sizeof(em_tlv_t)]{};
    auto *header = reinterpret_cast<em_raw_hdr_t *>(frame);
    memcpy(header->src, first.model.controller, 6);
    memcpy(header->dst, first.model.agent, 6);
    first.interval = 7;
    second.alarm = 9;
    std::thread worker([&]() {
        for (unsigned int request = 0; request < 100; request++) first.handle_policy_cfg_req(frame, sizeof(frame));
    });
    for (unsigned int request = 0; request < 100; request++) second.handle_policy_cfg_req(frame, sizeof(frame));
    worker.join();
    assert(manager.queued.size() == 200 && first.acks == 100 && second.acks == 100);
    assert(manager.queued.back().policy.metrics_policy.interval == 7);
    assert(manager.queued.back().policy.vendor_policy.link_stats_alarm_policy_cfg.reporting_interval == 9);
    first.model.controller[5]++;
    assert(first.handle_policy_cfg_req(frame, sizeof(frame)) == -1);
    memcpy(header->src, first.model.controller, 6);
    first.interval = -1;
    assert(first.handle_policy_cfg_req(frame, sizeof(frame)) == 0);
    assert(manager.queued.back().policy.metrics_policy.interval == 0);
    assert(manager.queued.back().policy.vendor_policy.link_stats_alarm_policy_cfg.reporting_interval == 0);
    assert(manager.queued.back().matches(first.model.controller, first.model.agent));
    first.model.agent[5]++;
    assert(first.handle_policy_cfg_req(frame, sizeof(frame)) == -1);
    assert(first.handle_policy_cfg_req(frame, 1) == -1);
    assert(first.handle_policy_cfg_req(nullptr, sizeof(frame)) == -1);
    std::puts("PASS: concurrent same-peer partial cache preserves both updates; changed peers reject old frames and reset baseline; queued policy retains source/destination identity");
}
'''.replace('TYPES', policy_types((root / 'inc/em_base.h').read_text())).replace(
    'ENVELOPE', received_policy_type((root / 'inc/em_policy_cfg.h').read_text())).replace('IMPLEMENTATION', implementation)
with tempfile.TemporaryDirectory(prefix='agent-policy-peer-envelope-') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', '-pthread',
                    '-x', 'c++', '-', '-o', str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
