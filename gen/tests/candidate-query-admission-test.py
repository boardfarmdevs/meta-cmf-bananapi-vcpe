"""Extract native admission/queue methods; --expect-blocked reproduces the old defect."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile


def function(source, signature):
    return re.search(re.escape(signature) + r'\(.*?\n\}', source, re.S).group()


root = Path(sys.argv[1])
shared = (root / 'src/orch/em_orch.cpp').read_text()
controller = (root / 'src/orch/em_orch_ctrl.cpp').read_text()
readiness = function(controller, 'bool em_orch_ctrl_t::is_em_ready_for_orch_exec')
build = function(controller, 'unsigned int em_orch_ctrl_t::build_candidates')
selection = build.split('case em_cmd_type_unassoc_sta_query:', 1)[1].split('\n\t    default:', 1)[0]
methods = '\n'.join(function(shared, signature) for signature in [
    'bool em_orch_t::submit_command', 'void em_orch_t::push_stats',
    'void em_orch_t::pop_stats', 'void em_orch_t::destroy_command',
    'bool em_orch_t::is_cmd_type_in_progress', 'bool em_orch_t::eligible_for_active',
    'bool em_orch_t::orchestrate', 'void em_orch_t::advance_commands',
])
constants = sorted((set(re.findall(r'\bem_(?:cmd_type|state_ctrl|orch_state)_\w+',
                                   readiness + selection + methods)) | {
    'em_state_ctrl_channel_query_pending', 'em_orch_state_idle', 'em_cmd_type_em_config'})
    - {'em_cmd_type_t', 'em_orch_state_t'})
program = r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <mutex>
#include <string>
#include <vector>
#define em_printfout(...) ((void)0)
enum { CONSTANTS };
using em_cmd_type_t = int;
using em_orch_state_t = int;
using mac_address_t = unsigned char[6];
using mac_addr_str_t = char[18];
using em_short_string_t = char[32];
using queue_t = std::vector<void *>;
using hash_map_t = std::map<std::string, void *>;
unsigned int queue_count(queue_t *queue) { return queue->size(); }
void *queue_peek(queue_t *queue, unsigned int index) { return queue->at(index); }
void *queue_remove(queue_t *queue, unsigned int index) {
    auto value = queue->at(index);
    queue->erase(queue->begin() + index);
    return value;
}
void queue_push(queue_t *queue, void *value) { queue->insert(queue->begin(), value); }
void *hash_map_get(hash_map_t *map, const char *key) {
    auto found = map->find(key);
    return found == map->end() ? nullptr : found->second;
}
void hash_map_put(hash_map_t *map, char *key, void *value) { (*map)[key] = value; free(key); }
void hash_map_remove(hash_map_t *map, const char *key) { map->erase(key); }
struct em_cmd_stats_t { int type; unsigned int count, time; };
struct em_op_class_info_t { unsigned int op_class = 115; struct { mac_address_t ruid = {}; } id; };
struct dm_easy_mesh_t {
    mac_address_t al = {};
    em_op_class_info_t operating;
    unsigned char *get_agent_al_interface_mac() { return al; }
    unsigned int get_num_op_class() { return 1; }
    em_op_class_info_t *get_op_class_info(unsigned int) { return &operating; }
    static void macbytes_to_string(unsigned char *, char *text) { text[0] = 0; }
};
namespace util { std::string mac_to_string(unsigned char *) { return "radio"; } }
struct em_bus_event_t { int type = em_cmd_type_unassoc_sta_query; };
struct em_cmd_t;
struct em_t {
    int state = em_state_ctrl_configured, orchestration = em_orch_state_idle;
    dm_easy_mesh_t model;
    mac_address_t mac = {};
    em_cmd_t *owner = nullptr;
    unsigned int clears = 0;
    bool is_al_interface_em() { return false; }
    int get_state() { return state; }
    int get_orch_state() { return orchestration; }
    void set_orch_state(int value) { orchestration = value; }
    unsigned char *get_radio_interface_mac() { return mac; }
    dm_easy_mesh_t *get_data_model() { return &model; }
    void orch_execute(em_cmd_t *command) { owner = command; orchestration = em_orch_state_progress; }
    void clear_cmd() { owner = nullptr; clears++; }
};
struct em_cmd_t {
    int m_type = em_cmd_type_unassoc_sta_query;
    queue_t candidates;
    queue_t *m_em_candidates = &candidates;
    struct { struct { struct { mac_address_t al_mac = {}; } unassoc_sta_query_params; } u; } m_param;
    unsigned int starts = 0;
    em_t *fixture_radio = nullptr;
    int get_type() { return m_type; }
    const char *get_cmd_name() { return "test"; }
    void set_start_time() { starts++; }
    void deinit() {}
    static int bus_2_cmd_type(int type) { return type; }
    virtual ~em_cmd_t() = default;
};
struct em_unassoc_query_list_t {
    unsigned int num_opclass = 1;
    struct { unsigned int op_class = 115; } opclass_list[1];
};
struct em_cmd_unassoc_sta_query_t : em_cmd_t {
    em_unassoc_query_list_t query;
    em_unassoc_query_list_t *get_query() { return &query; }
};
struct em_orch_t {
    queue_t pending, active;
    queue_t *m_pending = &pending, *m_active = &active;
    hash_map_t statistics;
    hash_map_t *m_cmd_map = &statistics;
    unsigned int m_pending_high_water = 0, query_timeout_visits = 0;
    std::recursive_mutex mutex;
    auto lock_commands() { return std::unique_lock<std::recursive_mutex>(mutex); }
    virtual unsigned int build_candidates(em_cmd_t *) = 0;
    virtual bool is_em_ready_for_orch_exec(em_cmd_t *, em_t *) = 0;
    bool is_em_ready_for_orch_fini(em_cmd_t *, em_t *) { return false; }
    bool is_cmd_in_progress_by_radio(em_bus_event_t *) { return false; }
    bool is_cmd_in_progress_by_type(em_bus_event_t *) { return false; }
    void update_stats(em_cmd_t *command) {
        auto *stats = static_cast<em_cmd_stats_t *>(hash_map_get(m_cmd_map, std::to_string(command->m_type).c_str()));
        stats->time++;
    }
    void orch_transient(em_cmd_t *command, em_t *) {
        if (command->m_type == em_cmd_type_unassoc_sta_query) query_timeout_visits++;
    }
    bool submit_command(em_cmd_t *);
    void push_stats(em_cmd_t *);
    void pop_stats(em_cmd_t *);
    void destroy_command(em_cmd_t *);
    bool is_cmd_type_in_progress(em_bus_event_t *);
    bool eligible_for_active(em_cmd_t *);
    bool orchestrate(em_cmd_t *, em_t *, bool);
    void advance_commands(bool);
    virtual ~em_orch_t() {
        for (auto command : pending) delete static_cast<em_cmd_t *>(command);
        for (auto command : active) delete static_cast<em_cmd_t *>(command);
        for (const auto &entry : statistics) free(entry.second);
    }
};
struct em_orch_ctrl_t : em_orch_t {
    std::vector<em_t *> radios;
    bool is_em_ready_for_orch_exec(em_cmd_t *, em_t *) override;
    unsigned int build_candidates(em_cmd_t *pcmd) override {
        if (pcmd->m_type == em_cmd_type_em_config) {
            queue_push(pcmd->m_em_candidates, pcmd->fixture_radio);
            return 1;
        }
        unsigned int count = 0;
        for (auto em : radios) {
            switch (pcmd->m_type) {
                case em_cmd_type_unassoc_sta_query:
SELECTION
                default: break;
            }
        }
        return count;
    }
};
READINESS
METHODS
em_cmd_unassoc_sta_query_t *query_for(em_t &radio) {
    auto *query = new em_cmd_unassoc_sta_query_t;
    memcpy(query->m_param.u.unassoc_sta_query_params.al_mac, radio.model.al, sizeof(mac_address_t));
    return query;
}
int main(int count, char **arguments) {
    const bool expect_blocked = count > 1 && std::string(arguments[1]) == "--expect-blocked";
    em_orch_ctrl_t orch;
    em_t startup, healthy;
    startup.model.al[5] = startup.mac[5] = startup.model.operating.id.ruid[5] = 1;
    healthy.model.al[5] = healthy.mac[5] = healthy.model.operating.id.ruid[5] = 2;
    orch.radios = {&startup, &healthy};
    auto *configuration = new em_cmd_t;
    configuration->m_type = em_cmd_type_em_config;
    configuration->fixture_radio = &startup;
    assert(orch.submit_command(configuration));
    orch.advance_commands(false);
    assert(startup.owner == configuration && startup.get_orch_state() == em_orch_state_progress);
    startup.state = em_state_ctrl_channel_query_pending;
    auto *query = query_for(startup);
    assert(!orch.is_em_ready_for_orch_exec(query, &startup));
    const bool admitted = orch.submit_command(query);
    em_bus_event_t next_query;
    if (expect_blocked) {
        assert(admitted);
        assert(orch.is_cmd_type_in_progress(&next_query));
        for (unsigned int second = 0; second < 70; second++) orch.advance_commands(true);
        assert(query->starts == 0 && orch.query_timeout_visits == 0);
        auto *query_stats = static_cast<em_cmd_stats_t *>(hash_map_get(
            orch.m_cmd_map, std::to_string(em_cmd_type_unassoc_sta_query).c_str()));
        assert(query_stats != nullptr && query_stats->time == 0);
        assert(orch.is_cmd_type_in_progress(&next_query));
        assert(healthy.owner == nullptr && healthy.get_orch_state() == em_orch_state_idle);
        std::puts("REPRODUCED: startup query admitted despite failed readiness; pending type blocks unrelated queries for 70 ticks without starting its timeout");
    } else {
        assert(!admitted);
        assert(startup.owner == configuration && startup.clears == 0);
        assert(!orch.is_cmd_type_in_progress(&next_query));
        startup.state = em_state_ctrl_configured;
        assert(!orch.submit_command(query_for(startup)));
        assert(startup.owner == configuration && startup.clears == 0);
        assert(!orch.is_cmd_type_in_progress(&next_query));
        healthy.state = em_state_ctrl_channel_query_pending;
        assert(!orch.submit_command(query_for(healthy)));
        assert(healthy.owner == nullptr && healthy.clears == 0);
        assert(!orch.is_cmd_type_in_progress(&next_query));
        healthy.state = em_state_ctrl_configured;
        auto *healthy_query = query_for(healthy);
        assert(orch.submit_command(healthy_query));
        orch.advance_commands(false);
        assert(healthy.owner == healthy_query && healthy_query->starts == 1);
        std::puts("PASS: startup query rejected before global type registration; healthy agent can immediately collect");
    }
}
'''.replace('CONSTANTS', ', '.join(constants)).replace('SELECTION', selection).replace(
    'READINESS', readiness).replace('METHODS', methods)
with tempfile.TemporaryDirectory(prefix='candidate-query-admission-') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['g++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread',
                    '-x', 'c++', '-', '-o', str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable), *sys.argv[2:]], check=True)
