#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys
import tempfile


orchestrator = Path(sys.argv[1]).read_text().split('void em_orch_ctrl_t::pre_process_cancel(', 1)[1].split('\n}\n', 1)[0]
cancel_branch = re.search(r'        case em_cmd_type_bsta_cap:.*?            break;', orchestrator, re.S)
assert cancel_branch, 'Capability cancellation must release its pending radio state'
capability = Path(sys.argv[2]).read_text()
report_method = re.search(r'int em_capability_t::handle_bsta_cap_report\(.*?\n\}', capability, re.S).group()
program = r'''
#include <cassert>
#include <mutex>
#define em_printfout(...) ((void)0)
enum {
    em_cmd_type_bsta_cap,
    em_state_ctrl_bsta_cap_pending,
    em_state_ctrl_configured,
    em_state_ctrl_unassoc_sta_link_metrics_pending,
    em_state_ctrl_topo_sync_pending,
    em_tlv_type_bh_sta_radio_cap,
    em_tlv_type_client_info
};
struct em_t {
    int state;
    int get_state() { return state; }
    void set_state(int value) { state = value; }
};
struct em_orch_t {
    std::recursive_mutex mutex;
    std::unique_lock<std::recursive_mutex> lock_commands() {
        return std::unique_lock<std::recursive_mutex>(mutex);
    }
};
struct em_mgr_t {
    em_orch_t *orch;
    em_orch_t *get_orch() { return orch; }
};
struct em_capability_t : em_t {
    em_mgr_t manager;
    int client_result = 0;
    unsigned int decoded = 0;
    em_mgr_t *get_mgr() { return &manager; }
    int handle_bsta_radio_cap(unsigned char *, unsigned int) { return 0; }
    int handle_client_info(unsigned char *, unsigned int) { return 0; }
    int process_single_tlv_in_1905_message(unsigned char *, unsigned int, int kind,
                                          int (em_capability_t::*)(unsigned char *, unsigned int)) {
        decoded++;
        return kind == em_tlv_type_client_info ? client_result : 0;
    }
    int handle_bsta_cap_report(unsigned char *, unsigned int);
};
void cancel_capability(em_t *em) {
    switch (em_cmd_type_bsta_cap) {
''' + cancel_branch.group() + r'''
        default: break;
    }
}
''' + report_method + r'''
int main() {
    em_orch_t orch;
    em_capability_t radio;
    radio.manager.orch = &orch;
    radio.state = em_state_ctrl_bsta_cap_pending;
    cancel_capability(&radio);
    assert(radio.state == em_state_ctrl_configured);
    radio.state = em_state_ctrl_bsta_cap_pending;
    assert(radio.handle_bsta_cap_report(nullptr, 0) == 0);
    assert(radio.state == em_state_ctrl_configured && radio.decoded == 2);
    for (int state : {em_state_ctrl_configured, em_state_ctrl_unassoc_sta_link_metrics_pending,
                      em_state_ctrl_topo_sync_pending}) {
        radio.state = state;
        cancel_capability(&radio);
        assert(radio.state == state);
        assert(radio.handle_bsta_cap_report(nullptr, 0) == 0);
        assert(radio.state == state);
    }
    radio.state = em_state_ctrl_bsta_cap_pending;
    radio.client_result = -1;
    assert(radio.handle_bsta_cap_report(nullptr, 0) == -1);
    assert(radio.state == em_state_ctrl_bsta_cap_pending);
    cancel_capability(&radio);
    assert(radio.state == em_state_ctrl_configured);
    radio.manager.orch = nullptr;
    assert(radio.handle_bsta_cap_report(nullptr, 0) == -1);
}
'''
with tempfile.TemporaryDirectory(prefix='capability-recovery-test-') as temporary:
    executable = Path(temporary) / 'test'
    subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', '-pthread',
                    '-x', 'c++', '-', '-o', str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
print('PASS: capability timeouts release radios; delayed replies preserve candidate/configuration state')
