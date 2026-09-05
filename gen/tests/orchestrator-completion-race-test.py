#!/usr/bin/env python3
import argparse
import re
import subprocess
import tempfile
from pathlib import Path


def method(source, signature):
    start = source.index(signature)
    body = source.index("{", start)
    depth = 1
    end = body + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


parser = argparse.ArgumentParser(description="Compile real orchestrator methods and race completion against their command lifetime")
parser.add_argument("source", type=Path, help="patched unified-wifi-mesh source tree")
args = parser.parse_args()
source = (args.source / "src/orch/em_orch.cpp").read_text()
header = (args.source / "inc/em_orch.h").read_text()
locking = ""
if "lock_commands()" in header:
    locking = "std::recursive_mutex m_command_mutex;\n" + method(
        header, "std::unique_lock<std::recursive_mutex> lock_commands()")

harness = r'''
#include <cassert>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <future>
#include <functional>
#include <iostream>
#include <map>
#include <mutex>
#include <string>
#include <sys/time.h>
#include <thread>
#include <vector>

using em_cmd_type_t = int;
using em_short_string_t = char[32];
using mac_addr_str_t = char[32];
using queue_t = std::vector<void *>;
using hash_map_t = std::map<std::string, void *>;
enum em_orch_state_t {
    em_orch_state_idle, em_orch_state_pending, em_orch_state_progress,
    em_orch_state_fini, em_orch_state_cancel
};
struct em_cmd_stats_t { int type; unsigned int count; unsigned int time; };
unsigned int queue_count(queue_t *queue) { return queue->size(); }
void *queue_peek(queue_t *queue, unsigned int index) { return queue->at(index); }
void *queue_remove(queue_t *queue, unsigned int index) {
    void *entry = queue->at(index);
    queue->erase(queue->begin() + index);
    return entry;
}
void queue_push(queue_t *queue, void *entry) { queue->push_back(entry); }
void *hash_map_get(hash_map_t *table, const char *key) {
    auto found = table->find(key);
    return found == table->end() ? nullptr : found->second;
}
void hash_map_remove(hash_map_t *table, const char *key) { table->erase(key); }
void hash_map_put(hash_map_t *table, char *key, void *value) {
    (*table)[key] = value;
    free(key);
}
template <typename... Values> void em_printfout(const char *, Values...) {}
std::atomic<unsigned int> destroyed{0};
struct em_cmd_t {
    int m_type = 76;
    queue_t candidates;
    queue_t *m_em_candidates = &candidates;
    timeval m_start_time{};
    int get_type() { return m_type; }
    const char *get_cmd_name() { return "candidate"; }
    void set_start_time() { gettimeofday(&m_start_time, nullptr); }
    void deinit() {}
    ~em_cmd_t() { destroyed++; }
};
struct em_t {
    em_orch_state_t state = em_orch_state_idle;
    em_cmd_t *command = nullptr;
    unsigned char address[6]{};
    em_orch_state_t get_orch_state() { return state; }
    void set_orch_state(em_orch_state_t next) { state = next; }
    void clear_cmd() { command = nullptr; }
    unsigned char *get_radio_interface_mac() { return address; }
    void orch_execute(em_cmd_t *next) {
        command = next;
        state = em_orch_state_progress;
    }
};
struct dm_easy_mesh_t {
    static void macbytes_to_string(unsigned char *, char *) {}
};
class em_orch_t {
public:
    LOCKING
    queue_t pending, active;
    hash_map_t statistics;
    queue_t *m_pending = &pending;
    queue_t *m_active = &active;
    hash_map_t *m_cmd_map = &statistics;
    unsigned int m_pending_high_water = 0;
    std::function<void()> during_fini;
    unsigned int build_candidates(em_cmd_t *command) {
        return queue_count(command->m_em_candidates);
    }
    bool is_em_ready_for_orch_exec(em_cmd_t *, em_t *) { return true; }
    bool is_em_ready_for_orch_fini(em_cmd_t *, em_t *) {
        if (during_fini) during_fini();
        return false;
    }
    void orch_transient(em_cmd_t *command, em_t *) {
        assert(hash_map_get(m_cmd_map, std::to_string(command->m_type).c_str()));
    }
    void update_stats(em_cmd_t *);
    void pop_stats(em_cmd_t *);
    void push_stats(em_cmd_t *);
    bool submit_command(em_cmd_t *);
    void destroy_command(em_cmd_t *);
    bool complete_command(em_cmd_type_t);
    bool orchestrate(em_cmd_t *, em_t *);
    bool eligible_for_active(em_cmd_t *);
    void handle_timeout();
};
'''.replace("LOCKING", locking)
for signature in (
    "void em_orch_t::update_stats(",
    "void em_orch_t::pop_stats(",
    "void em_orch_t::push_stats(",
    "bool em_orch_t::submit_command(",
    "void em_orch_t::destroy_command(",
    "bool em_orch_t::complete_command(",
    "bool em_orch_t::orchestrate(",
    "bool em_orch_t::eligible_for_active(",
    "void em_orch_t::handle_timeout(",
):
    harness += method(source, signature)
harness += r'''
using namespace std::chrono_literals;

void race_tick_and_response() {
    em_orch_t orchestrator;
    em_t radio;
    auto *command = new em_cmd_t;
    command->candidates.push_back(&radio);
    assert(orchestrator.submit_command(command));
    orchestrator.handle_timeout();
    assert(radio.command == command);

    std::promise<void> entered_tick, release_tick, attempting_completion;
    auto released = release_tick.get_future().share();
    orchestrator.during_fini = [&]() {
        entered_tick.set_value();
        released.wait();
    };
    auto ticking = std::async(std::launch::async, [&]() { orchestrator.handle_timeout(); });
    entered_tick.get_future().wait();
    auto completing = std::async(std::launch::async, [&]() {
        attempting_completion.set_value();
        return orchestrator.complete_command(76);
    });
    attempting_completion.get_future().wait();
    assert(completing.wait_for(100ms) == std::future_status::timeout);
    assert(radio.command == command && queue_count(orchestrator.m_active) == 1);
    assert(hash_map_get(orchestrator.m_cmd_map, "76") != nullptr);
    release_tick.set_value();
    ticking.get();
    assert(completing.get());
    assert(radio.command == nullptr && radio.state == em_orch_state_idle);
    assert(queue_count(orchestrator.m_active) == 0 && orchestrator.statistics.empty());
    assert(!orchestrator.complete_command(76));
    orchestrator.during_fini = nullptr;
    auto *next_command = new em_cmd_t;
    next_command->candidates.push_back(&radio);
    assert(orchestrator.submit_command(next_command));
    orchestrator.handle_timeout();
    assert(orchestrator.complete_command(76));
}
'''
if locking:
    harness += r'''
void race_response_and_tick() {
    em_orch_t orchestrator;
    em_t radio;
    auto *command = new em_cmd_t;
    command->candidates.push_back(&radio);
    assert(orchestrator.submit_command(command));
    orchestrator.handle_timeout();
    std::future<void> ticking;
    std::promise<void> attempting_tick;
    {
        auto response_lock = orchestrator.lock_commands();
        ticking = std::async(std::launch::async, [&]() {
            attempting_tick.set_value();
            orchestrator.handle_timeout();
        });
        attempting_tick.get_future().wait();
        assert(ticking.wait_for(100ms) == std::future_status::timeout);
        assert(radio.command == command);
        assert(orchestrator.complete_command(76));
        assert(radio.command == nullptr && orchestrator.statistics.empty());
    }
    ticking.get();
}
'''
harness += "int main() {\n"
harness += "for (unsigned int iteration = 0; iteration < 20; iteration++) race_tick_and_response();\n"
if locking:
    harness += "race_response_and_tick();\nassert(destroyed == 41);\n"
harness += 'std::cout << "PASS: concurrent completion, command/stat lifetime, nested locking, duplicate response and immediate next query\\n";\n}\n'

with tempfile.TemporaryDirectory(prefix="orchestrator-completion-race-") as temporary:
    directory = Path(temporary)
    implementation = directory / "orchestrator.cpp"
    executable = directory / "orchestrator-test"
    implementation.write_text(harness)
    subprocess.run(["g++", "-std=gnu++17", "-Wall", "-Wextra", "-Werror", "-pthread",
                    str(implementation), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=20)

metrics = (args.source / "src/em/metrics/em_metrics.cpp").read_text()
for signature in ("int em_metrics_t::handle_unassoc_sta_link_metrics_rsp(",
                  "int em_metrics_t::handle_1905_ack("):
    handler = method(metrics, signature)
    assert handler.index("lock_commands()") < handler.index("get_all_em_for_al_mac")
    assert handler.index("lock_commands()") < handler.index("complete_command(")
controller = method((args.source / "src/em/em.cpp").read_text(), "void em_t::handle_ctrl_state()")
assert controller.index("lock_commands()") < controller.index("m_orch_state")
for signature in re.findall(r"^(?:void|bool) em_orch_t::(?:cancel_command|remove_em_config_cmd_for_em|reset_cmd_time|is_cmd_in_progress_by_radio|is_cmd_in_progress_by_type|get_dev_test_status|is_cmd_type_in_progress)\([^\n]+", source, re.MULTILINE):
    assert "lock_commands()" in method(source, signature), signature
print("PASS: response/ACK/timer lifetime guards and all queue/stat entry points")
