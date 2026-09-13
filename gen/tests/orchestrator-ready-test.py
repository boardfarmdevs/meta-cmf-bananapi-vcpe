from pathlib import Path
import subprocess
import sys
import tempfile


root = Path(sys.argv[1])
source = (root / 'src/orch/em_orch.cpp').read_text()


def function(signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    position = opening + 1
    while depth:
        depth += (source[position] == '{') - (source[position] == '}')
        position += 1
    return source[start:position]


methods = '\n'.join(function(signature) for signature in (
    'bool em_orch_t::orchestrate(', 'bool em_orch_t::eligible_for_active(',
    'void em_orch_t::handle_timeout()', 'void em_orch_t::handle_ready_commands()',
    'void em_orch_t::advance_commands('))
agent = (root / 'src/agent/em_agent.cpp').read_text()
handler = agent[agent.index('void em_agent_t::handle_event('):agent.index('void em_agent_t::handle_5s_tick(')]
assert handler.index('handle_bus_event(') < handler.index('m_orch->handle_ready_commands();')
assert 'void handle_ready_commands();' in (root / 'inc/em_orch.h').read_text()
program = r'''
#include <cassert>
#include <cstring>
#include <mutex>
#include <vector>
using queue_t = std::vector<void *>;
using mac_addr_str_t = char[18];
unsigned int queue_count(queue_t *queue) { return queue->size(); }
void *queue_peek(queue_t *queue, unsigned int index) { return queue->at(index); }
void *queue_remove(queue_t *queue, unsigned int index) {
    auto value = queue->at(index);
    queue->erase(queue->begin() + index);
    return value;
}
void queue_push(queue_t *queue, void *value) { queue->insert(queue->begin(), value); }
enum em_orch_state_t { em_orch_state_idle, em_orch_state_pending,
    em_orch_state_progress, em_orch_state_fini, em_orch_state_cancel };
struct em_cmd_t;
struct em_t {
    em_orch_state_t state = em_orch_state_idle;
    bool ready = true, finished = false, finish_inline = false;
    unsigned int executions = 0;
    unsigned char mac[6] = {};
    em_orch_state_t get_orch_state() { return state; }
    void set_orch_state(em_orch_state_t next) { state = next; }
    unsigned char *get_radio_interface_mac() { return mac; }
    void orch_execute(em_cmd_t *) {
        assert(state == em_orch_state_pending);
        executions++;
        state = finish_inline ? em_orch_state_fini : em_orch_state_progress;
    }
};
struct em_cmd_t {
    queue_t candidates;
    queue_t *m_em_candidates = &candidates;
    unsigned int starts = 0;
    bool destroyed = false;
    explicit em_cmd_t(em_t *radio) { candidates.push_back(radio); }
    void set_start_time() { starts++; }
};
struct dm_easy_mesh_t {
    static void macbytes_to_string(unsigned char *, char *text) { text[0] = '\0'; }
};
struct em_orch_t {
    queue_t pending, active;
    queue_t *m_pending = &pending, *m_active = &active;
    std::recursive_mutex mutex;
    unsigned int stats = 0, timeouts = 0, retired = 0;
    auto lock_commands() { return std::unique_lock<std::recursive_mutex>(mutex); }
    bool is_em_ready_for_orch_exec(em_cmd_t *, em_t *radio) { return radio->ready; }
    bool is_em_ready_for_orch_fini(em_cmd_t *, em_t *radio) { return radio->finished; }
    void update_stats(em_cmd_t *) { stats++; }
    void orch_transient(em_cmd_t *, em_t *) { timeouts++; }
    void pop_stats(em_cmd_t *) { retired++; }
    void destroy_command(em_cmd_t *command) { command->destroyed = true; }
    bool orchestrate(em_cmd_t *, em_t *, bool);
    bool eligible_for_active(em_cmd_t *);
    void handle_timeout();
    void handle_ready_commands();
    void advance_commands(bool);
};
''' + methods + r'''
int main() {
    em_orch_t orch;
    em_t blocked, independent;
    blocked.ready = false;
    em_cmd_t first(&blocked), second(&blocked), other(&independent);
    queue_push(orch.m_pending, &first);
    queue_push(orch.m_pending, &second);
    queue_push(orch.m_pending, &other);
    orch.handle_ready_commands();
    assert(first.starts == 1 && second.starts == 0 && other.starts == 1);
    assert(blocked.executions == 0 && independent.executions == 1);
    for (unsigned int event = 0; event < 50; event++) orch.handle_ready_commands();
    assert(orch.stats == 0 && orch.timeouts == 0);
    assert(first.starts == 1 && second.starts == 0 && independent.executions == 1);
    orch.handle_timeout();
    assert(orch.timeouts == 2 && orch.stats == 2);
    blocked.ready = true;
    orch.handle_ready_commands();
    assert(blocked.executions == 1 && second.starts == 0);
    blocked.finished = true;
    blocked.finish_inline = true;
    independent.finished = true;
    orch.handle_ready_commands();
    assert(first.destroyed && other.destroyed && !second.destroyed);
    assert(second.starts == 1 && blocked.executions == 2);
    assert(blocked.state == em_orch_state_fini && orch.retired == 2);
    orch.handle_ready_commands();
    assert(second.destroyed && blocked.state == em_orch_state_idle);
    assert(orch.retired == 3 && orch.timeouts == 2 && orch.stats == 2);
    assert(orch.active.empty() && orch.pending.empty());
    em_cmd_t cancelled(&blocked);
    blocked.state = em_orch_state_cancel;
    queue_push(orch.m_active, &cancelled);
    orch.handle_ready_commands();
    assert(cancelled.destroyed && blocked.state == em_orch_state_idle);
    assert(orch.timeouts == 2 && orch.stats == 2);
}
'''
with tempfile.TemporaryDirectory(prefix='orchestrator-ready-') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['g++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread',
                    '-x', 'c++', '-', '-o', str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
print('PASS: ready commands advance on events, preserving radio ownership, queue order and timeout cadence')
