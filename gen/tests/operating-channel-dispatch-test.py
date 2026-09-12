from pathlib import Path
import subprocess
import sys
import tempfile


source = (Path(sys.argv[1]) / 'src/orch/em_orch_agent.cpp').read_text()
start = source.index('            case em_cmd_type_op_channel_report:', source.index('build_candidates'))
branch = source[start:source.index('\n            case em_cmd_type_btm_report:', start)]
program = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
enum { em_cmd_type_op_channel_report, em_state_agent_unconfigured,
       em_state_agent_topo_synchronized, em_state_agent_ap_cap_report,
       em_state_agent_channel_select_configuration_pending, em_state_agent_configured,
       em_state_agent_sta_link_metrics_pending };
using mac_address_t = unsigned char[6];
struct dm_radio_t {
    mac_address_t address{};
    dm_radio_t(unsigned char identity = 0) { address[0] = identity; }
    unsigned char *get_radio_interface_mac() { return address; }
};
struct dm_easy_mesh_t {
    std::vector<dm_radio_t> radios;
    dm_radio_t *get_radio(unsigned int index) { return index < radios.size() ? &radios[index] : nullptr; }
    dm_radio_t *get_radio(unsigned char *address) {
        for (auto &radio : radios) {
            if (memcmp(radio.address, address, sizeof(mac_address_t)) == 0) return &radio;
        }
        return nullptr;
    }
    static void macbytes_to_string(unsigned char *, char *) {}
};
struct radio_node : dm_radio_t {
    bool al = false;
    int state = em_state_agent_configured;
    bool is_al_interface_em() { return al; }
    int get_state() { return state; }
};
struct command {
    dm_easy_mesh_t m_data_model;
    std::vector<radio_node *> candidates;
    std::vector<radio_node *> *m_em_candidates = &candidates;
};
void queue_push(std::vector<radio_node *> *queue, radio_node *node) { queue->push_back(node); }
int admit(command *pcmd, radio_node *em) {
    dm_radio_t *radio;
    char dst_mac_str[18]{};
    int count = 0;
    switch (em_cmd_type_op_channel_report) {
''' + branch + r'''
        default: break;
    }
    return count;
}
int main() {
    for (int state : {em_state_agent_unconfigured, em_state_agent_topo_synchronized,
                      em_state_agent_ap_cap_report, em_state_agent_channel_select_configuration_pending,
                      em_state_agent_configured, em_state_agent_sta_link_metrics_pending}) {
        for (unsigned char identity : {1, 2, 3, 4}) {
            command report;
            report.m_data_model.radios = {dm_radio_t{1}, dm_radio_t{2}, dm_radio_t{3}};
            radio_node node;
            node.address[0] = identity;
            node.state = state;
            int expected = state != em_state_agent_unconfigured && identity <= 3 ? 1 : 0;
            assert(admit(&report, &node) == expected);
            assert(report.candidates.size() == static_cast<unsigned int>(expected));
            node.al = true;
            assert(admit(&report, &node) == 0);
        }
    }
    command empty;
    radio_node node;
    assert(admit(&empty, &node) == 0);
}
'''
with tempfile.TemporaryDirectory(prefix='operating-channel-dispatch-') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', '-x', 'c++', '-', '-o', str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
print('PASS: local and selected channel reports match all included radios, never unrelated or onboarding nodes')
