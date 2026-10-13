"""0266: a Backhaul STA Capability request for a radio still in its em_config.

Extracts the native admission and queue methods, as candidate-query-admission-test.py does for
0207. Every Topology Response that carries the Backhaul STA Radio Capabilities TLV submits a
bsta_cap request for its radio, in any state. --expect-blocked reproduces the old defect: the
request for a radio whose em_config is in flight (M2 sent) is admitted to the pending queue and
never starts (the query is never sent), so the controller cancelled it at its time limit and
renewed the agent, every minute (a physical pod after its boot, 12 October). Fixed, it is refused
at submit, the radio's em_config is untouched, another agent's configured radio still runs its
own at once, and the radio's next request, once configured, runs.
"""

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
selection = build.split('case em_cmd_type_bsta_cap:', 1)[1].split('case em_cmd_type_unassoc_sta_query:', 1)[0]
methods = '\n'.join(function(shared, signature) for signature in [
    'bool em_orch_t::submit_command', 'void em_orch_t::push_stats',
    'void em_orch_t::pop_stats', 'void em_orch_t::destroy_command',
    'bool em_orch_t::is_cmd_type_in_progress', 'bool em_orch_t::eligible_for_active',
    'bool em_orch_t::orchestrate', 'void em_orch_t::advance_commands',
])
constants = sorted((set(re.findall(r'\bem_(?:cmd_type|state_ctrl|orch_state)_\w+',
                                   readiness + selection + methods)) | {
    'em_state_ctrl_wsc_m2_sent', 'em_state_ctrl_configured', 'em_orch_state_idle',
    'em_orch_state_progress', 'em_cmd_type_em_config', 'em_cmd_type_bsta_cap',
    'em_cmd_type_unassoc_sta_query'})
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
#define em_util_dbg_print(...) ((void)0)
#define em_util_info_print(...) ((void)0)
#define em_util_error_print(...) ((void)0)
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
struct dm_easy_mesh_t {
    mac_address_t al = {};
    unsigned char *get_agent_al_interface_mac() { return al; }
    /* the request names its radio by the MAC's text: here one byte, the last */
    static void string_to_macbytes(const char *text, unsigned char *mac) {
        memset(mac, 0, 6);
        mac[5] = static_cast<unsigned char>(atoi(text));
    }
    static void macbytes_to_string(unsigned char *, char *text) { text[0] = 0; }
};
namespace util { std::string mac_to_string(unsigned char *) { return "radio"; } }
struct em_bus_event_t { int type = em_cmd_type_bsta_cap; bool has_al = false; mac_address_t al = {}; };
inline bool unassoc_query_agent(em_bus_event_t *evt, mac_address_t al_mac) {
    if (evt->has_al) memcpy(al_mac, evt->al, sizeof(mac_address_t));
    return evt->has_al;
}
struct em_cmd_t;
struct em_t {
    int state = em_state_ctrl_configured, orchestration = em_orch_state_idle;
    dm_easy_mesh_t model;
    mac_address_t mac = {};
    em_cmd_t *owner = nullptr;
    unsigned int clears = 0;
    bool is_al_interface_em() { return false; }
    int get_state() { return state; }
    void set_state(int value) { state = value; }
    int get_orch_state() { return orchestration; }
    void set_orch_state(int value) { orchestration = value; }
    unsigned char *get_radio_interface_mac() { return mac; }
    dm_easy_mesh_t *get_data_model() { return &model; }
    void orch_execute(em_cmd_t *command) { owner = command; orchestration = em_orch_state_progress; }
    void clear_cmd() { owner = nullptr; clears++; }
};
struct em_cmd_t {
    int m_type = em_cmd_type_bsta_cap;
    queue_t candidates;
    queue_t *m_em_candidates = &candidates;
    struct {
        struct {
            struct { char args[1][32]; } args;
            struct { mac_address_t al_mac = {}; } unassoc_sta_query_params;
        } u;
    } m_param;
    unsigned int starts = 0;
    em_t *fixture_radio = nullptr;
    int get_type() { return m_type; }
    const char *get_cmd_name() { return "test"; }
    void set_start_time() { starts++; }
    void deinit() {}
    static int bus_2_cmd_type(int type) { return type; }
    virtual ~em_cmd_t() = default;
};
struct em_unassoc_query_list_t { unsigned int num_opclass = 0; };
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
        mac_address_t rad_mac;
        dm_easy_mesh_t *dm = nullptr;
        for (auto em : radios) {
            switch (pcmd->m_type) {
                case em_cmd_type_bsta_cap:
SELECTION
                default: break;
            }
        }
        (void)dm;
        return count;
    }
};
READINESS
METHODS
em_cmd_t *bsta_cap_for(em_t &radio) {
    auto *request = new em_cmd_t;
    snprintf(request->m_param.u.args.args[0], sizeof(request->m_param.u.args.args[0]), "%d", radio.mac[5]);
    return request;
}
int main(int count, char **arguments) {
    const bool expect_blocked = count > 1 && std::string(arguments[1]) == "--expect-blocked";
    em_orch_ctrl_t orch;
    em_t radio_b, other;  /* a two-radio pod's radio B; another agent's configured radio */
    radio_b.mac[5] = 1;
    other.mac[5] = 2;
    orch.radios = {&radio_b, &other};
    /* radio B's em_config in flight: its M2 sent (state 258 in the controller's log) */
    auto *configuration = new em_cmd_t;
    configuration->m_type = em_cmd_type_em_config;
    configuration->fixture_radio = &radio_b;
    assert(orch.submit_command(configuration));
    orch.advance_commands(false);
    assert(radio_b.owner == configuration && radio_b.get_orch_state() == em_orch_state_progress);
    radio_b.state = em_state_ctrl_wsc_m2_sent;
    /* a Topology Response with the Backhaul STA Radio Capabilities TLV for radio B */
    auto *request = bsta_cap_for(radio_b);
    assert(!orch.is_em_ready_for_orch_exec(request, &radio_b));
    const bool admitted = orch.submit_command(request);
    if (expect_blocked) {
        assert(admitted);
        for (unsigned int second = 0; second < 70; second++) orch.advance_commands(true);
        assert(request->starts == 0);  /* never run: the query is never sent */
        assert(queue_count(orch.m_pending) == 1);
        assert(radio_b.owner == configuration);
        std::puts("REPRODUCED: a bsta_cap for a radio in its em_config admitted to pending, never started in 70 ticks");
    } else {
        assert(!admitted);
        assert(queue_count(orch.m_pending) == 0);
        assert(radio_b.owner == configuration && radio_b.clears == 0);  /* its em_config untouched */
        /* another agent's configured radio: its request runs at once */
        auto *others = bsta_cap_for(other);
        assert(orch.submit_command(others));
        orch.advance_commands(false);
        assert(other.owner == others && others->starts == 1);
        /* radio B configured, its em_config done: the next topology sync's request runs */
        radio_b.state = em_state_ctrl_configured;
        radio_b.set_orch_state(em_orch_state_idle);
        auto *next = bsta_cap_for(radio_b);
        assert(orch.submit_command(next));
        orch.advance_commands(false);
        assert(radio_b.owner == next && next->starts == 1);
        std::puts("PASS: a bsta_cap for a radio in its em_config refused at submit; it runs once the radio is configured");
    }
}
'''.replace('CONSTANTS', ', '.join(constants)).replace('SELECTION', selection).replace(
    'READINESS', readiness).replace('METHODS', methods)
with tempfile.TemporaryDirectory(prefix='bsta-cap-admission-') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['g++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread',
                    '-x', 'c++', '-', '-o', str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable), *sys.argv[2:]], check=True)
