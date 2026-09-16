"""Exercise native policy ownership, complete value retention and association gates."""

from pathlib import Path
import subprocess
import sys
import tempfile

from native_policy_test_support import method, policy_types, received_policy_type


agent_path = Path(sys.argv[1])
root = agent_path.parents[2]
source = agent_path.read_text()
methods = '\n'.join(method(source, signature) for signature in [
    'void em_agent_t::handle_set_policy', 'void em_agent_t::apply_pending_policy',
    'void em_agent_t::handle_onewifi_private_cb', 'void em_agent_t::handle_2s_tick',
    'void em_agent_t::handle_autoconfig_renew',
])
types = policy_types((root / 'inc/em_base.h').read_text())
envelope = received_policy_type((root / 'inc/em_policy_cfg.h').read_text())
program = r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <memory>
#include <string>
#include <vector>
#define em_printfout(...) ((void)0)
using mac_address_t = unsigned char[6];
using mac_addr_t = unsigned char[6];
TYPES
ENVELOPE
constexpr int EM_MAX_CMD = 8, webconfig_subdoc_type_em_config = 1;
constexpr int em_cmd_out_status_prev_cmd_in_progress = 1, em_service_type_agent = 1;
constexpr int WIFI_WEBCONFIG_GET_ASSOC = 1, bus_error_success = 0, em_bus_event_type_sta_list = 1;
struct test_clock {
    using time_point = std::chrono::steady_clock::time_point;
    static time_point current;
    static time_point now() { return current; }
};
test_clock::time_point test_clock::current{};
struct em_bus_event_t {
    unsigned int data_len = sizeof(em_received_policy_t);
    struct { unsigned char raw_buff[sizeof(em_received_policy_t)]; } u;
};
struct em_cmd_t {};
struct bus_handle_t {};
unsigned int association_reads = 0;
struct raw_data_t { struct { char *bytes; } raw_data; unsigned int raw_data_len; };
struct wifi_bus_desc_t {
    int bus_data_get_fn(bus_handle_t *, int, raw_data_t *snapshot) {
        association_reads++;
        snapshot->raw_data.bytes = static_cast<char *>(calloc(2, 1));
        snapshot->raw_data_len = 1;
        return 0;
    }
};
struct em_orch_t {
    bool is_cmd_type_in_progress(em_bus_event_t *) { return false; }
    int submit_commands(em_cmd_t **, unsigned int) { return 1; }
};
struct em_cmd_agent_t { void send_result(int) {} };
struct dm_easy_mesh_t {
    int result = 1;
    mac_address_t controller = {2, 0, 0, 0, 0, 1}, agent = {2, 0, 0, 0, 0, 2};
    unsigned char *get_ctl_mac() { return controller; }
    unsigned char *get_agent_al_interface_mac() { return agent; }
    std::vector<em_policy_cfg_params_t> attempts;
    int refresh_onewifi_subdoc(wifi_bus_desc_t *, bus_handle_t *, const char *,
                              int, void *, em_policy_cfg_params_t *policy) {
        attempts.push_back(*policy);
        return result;
    }
    int analyze_onewifi_vap_cb(em_bus_event_t *, em_cmd_t **) { return 1; }
    int analyze_autoconfig_renew(em_bus_event_t *, em_cmd_t **) { return 1; }
};
struct em_t {
    bool is_al_interface_em() { return false; }
    int get_service_type() { return em_service_type_agent; }
    void retry_operating_channel_report() {}
};
void *hash_map_get_first(void *) { return nullptr; }
void *hash_map_get_next(void *, void *) { return nullptr; }
struct em_agent_t {
    dm_easy_mesh_t m_data_model;
    wifi_bus_desc_t bus;
    bus_handle_t m_bus_hdl;
    em_orch_t orch;
    em_orch_t *m_orch = &orch;
    em_cmd_agent_t command;
    em_cmd_agent_t *m_agent_cmd = &command;
    bool available = true;
    void *m_em_map = nullptr;
    bool m_onewifi_wsc_subdoc_active = false;
    unsigned int m_onewifi_wsc_wait_ticks = 0;
    std::string m_onewifi_wsc_ruid;
    std::deque<std::string> m_deferred_onewifi_wsc_ruids;
    bool m_initial_op_channel_report_sent = true;
    std::chrono::steady_clock::time_point m_operating_channel_refresh_due{};
    std::unique_ptr<em_received_policy_t> m_received_policy;
    bool m_policy_apply_pending = false;
    wifi_bus_desc_t *get_bus_descriptor() { return available ? &bus : nullptr; }
    void release_next_onewifi_wsc_radio(const char *) {}
    bool publish_initial_operating_channels() { return false; }
    void io_process(int, unsigned char *, unsigned int) {}
    void handle_set_policy(em_bus_event_t *);
    void apply_pending_policy();
    void handle_onewifi_private_cb(em_bus_event_t *);
    void handle_2s_tick();
    void handle_autoconfig_renew(em_bus_event_t *);
};
METHODS
int main() {
    em_agent_t agent;
    em_bus_event_t event;
    em_received_policy_t received{};
    memcpy(received.controller, agent.m_data_model.controller, 6);
    memcpy(received.agent, agent.m_data_model.agent, 6);
    memset(&received.policy, 0x25, sizeof(received.policy));
    auto &policy = received.policy;
    policy.metrics_policy.interval = 0;
    memcpy(event.u.raw_buff, &received, sizeof(received));
    agent.available = false;
    agent.handle_set_policy(&event);
    assert(agent.m_policy_apply_pending && agent.m_data_model.attempts.empty());
    memset(event.u.raw_buff, 0, sizeof(event.u.raw_buff));
    agent.available = true;
    for (int failure : {-1, 0}) {
        agent.m_data_model.result = failure;
        agent.apply_pending_policy();
        assert(agent.m_policy_apply_pending && agent.m_initial_op_channel_report_sent);
        assert(memcmp(&agent.m_data_model.attempts.back(), &policy, sizeof(policy)) == 0);
    }
    agent.m_data_model.result = 1;
    agent.apply_pending_policy();
    assert(!agent.m_policy_apply_pending && agent.m_initial_op_channel_report_sent);
    const auto count = agent.m_data_model.attempts.size();
    for (unsigned int tick = 0; tick < 100; tick++) {
        test_clock::current += std::chrono::seconds(2);
        agent.handle_2s_tick();
    }
    assert(agent.m_data_model.attempts.size() == count && association_reads >= 6);
    agent.handle_autoconfig_renew(&event);
    assert(agent.m_initial_op_channel_report_sent);
    assert(agent.m_operating_channel_refresh_due == test_clock::time_point{});
    std::puts("PASS: complete native policy retained across null bus/negative/zero failures; disabled interval preserved; 100 unready-channel ticks keep association refresh alive after policy/renew");

    agent.m_onewifi_wsc_subdoc_active = true;
    agent.m_deferred_onewifi_wsc_ruids.push_back("next-radio");
    agent.handle_onewifi_private_cb(&event);
    agent.apply_pending_policy();
    assert(agent.m_policy_apply_pending && agent.m_data_model.attempts.size() == count);
    agent.m_deferred_onewifi_wsc_ruids.clear();
    agent.apply_pending_policy();
    assert(agent.m_data_model.attempts.size() == count + 1);
    assert(memcmp(&agent.m_data_model.attempts.back(), &policy, sizeof(policy)) == 0);
    agent.m_data_model.controller[5]++;
    agent.m_onewifi_wsc_subdoc_active = true;
    agent.handle_onewifi_private_cb(&event);
    agent.apply_pending_policy();
    assert(!agent.m_received_policy && !agent.m_policy_apply_pending);
    assert(agent.m_data_model.attempts.size() == count + 1);
    memcpy(event.u.raw_buff, &received, sizeof(received));
    agent.handle_set_policy(&event);
    assert(!agent.m_received_policy);
    memcpy(received.controller, agent.m_data_model.controller, 6);
    policy.metrics_policy.interval = 7;
    memcpy(event.u.raw_buff, &received, sizeof(received));
    agent.handle_set_policy(&event);
    assert(agent.m_data_model.attempts.back().metrics_policy.interval == 7);
    agent.m_data_model.agent[5]++;
    agent.m_policy_apply_pending = true;
    agent.apply_pending_policy();
    assert(!agent.m_received_policy && !agent.m_policy_apply_pending);
    std::puts("PASS: same-peer WSC replays only after drain; controller/local-AL changes invalidate cache and reject queued old-peer events");

    em_agent_t empty;
    empty.handle_set_policy(nullptr);
    event.data_len = 1;
    empty.handle_set_policy(&event);
    empty.m_onewifi_wsc_subdoc_active = true;
    empty.handle_onewifi_private_cb(&event);
    empty.apply_pending_policy();
    assert(empty.m_data_model.attempts.empty() && !empty.m_received_policy);
    std::puts("PASS: no received policy means no invented policy; malformed events ignored");
}
'''.replace('TYPES', types).replace('ENVELOPE', envelope).replace(
    'METHODS', methods.replace('std::chrono::steady_clock::now()', 'test_clock::now()'))
with tempfile.TemporaryDirectory(prefix='agent-policy-recovery-') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                    '-x', 'c++', '-', '-o', str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
