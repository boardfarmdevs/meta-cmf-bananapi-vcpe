#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys
import tempfile


source = Path(sys.argv[1]).read_text()
method = re.search(r'void em_agent_t::handle_2s_tick\(\)\n\{.*?\n\}', source, re.S).group()
harness = r'''
#include <cassert>
#include <cstdlib>
#include <cstring>
#define WIFI_WEBCONFIG_GET_ASSOC "Device.WiFi.AssociatedClients"
#define em_printfout(...) ((void)0)
enum { bus_error_success, em_bus_event_type_sta_list };
struct raw_data_t { struct { void *bytes; } raw_data; unsigned int raw_data_len; };
static unsigned int queries = 0;
static bool fail_query = false;
static int get_snapshot(int *, const char *name, raw_data_t *snapshot) {
    assert(strcmp(name, WIFI_WEBCONFIG_GET_ASSOC) == 0);
    queries++;
    if (fail_query) return 9;
    snapshot->raw_data.bytes = strdup("snapshot");
    snapshot->raw_data_len = 9;
    return bus_error_success;
}
struct wifi_bus_desc_t { decltype(&get_snapshot) bus_data_get_fn; };
class em_agent_t {
public:
    bool m_initial_op_channel_report_sent = false;
    int m_bus_hdl = 0;
    unsigned int notifications = 0;
    bool publish_initial_operating_channels() { return false; }
    wifi_bus_desc_t *get_bus_descriptor() { static wifi_bus_desc_t descriptor{get_snapshot}; return &descriptor; }
    void io_process(int event, unsigned char *bytes, unsigned int length) {
        assert(event == em_bus_event_type_sta_list && length == 9);
        assert(strcmp(reinterpret_cast<char *>(bytes), "snapshot") == 0);
        notifications++;
    }
    void handle_2s_tick();
};
'''
checks = r'''
int main() {
    em_agent_t agent;
    for (int tick = 0; tick < 30; tick++) agent.handle_2s_tick();
    assert(queries == 0);
    agent.m_initial_op_channel_report_sent = true;
    agent.handle_2s_tick();
    assert(queries == 1 && agent.notifications == 1);
    for (int tick = 0; tick < 14; tick++) agent.handle_2s_tick();
    assert(queries == 1);
    agent.handle_2s_tick();
    assert(queries == 2 && agent.notifications == 2);
    fail_query = true;
    for (int tick = 0; tick < 15; tick++) agent.handle_2s_tick();
    assert(queries == 3 && agent.notifications == 2);
}
'''
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    (root / 'test.cpp').write_text(harness + method + checks)
    subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', str(root / 'test.cpp'), '-o', str(root / 'test')], check=True)
    subprocess.run([str(root / 'test')], check=True)
print('PASS: production snapshot refresh waits for onboarding, runs every 30 seconds, and does not publish failed reads')
