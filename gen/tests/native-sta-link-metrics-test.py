#!/usr/bin/env python3
"""Compile complete production gates, dispatcher, scheduler and metrics continuations."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


FUNCTIONS = {
    "src/em/em.cpp": ["void em_t::orch_execute", "void em_t::set_orch_state"],
    "src/orch/em_orch_agent.cpp": ["bool em_orch_agent_t::is_em_ready_for_orch_exec",
                                  "bool em_orch_agent_t::is_em_ready_for_orch_fini"],
    "src/orch/em_orch.cpp": ["bool em_orch_t::submit_command", "bool em_orch_t::eligible_for_active",
                            "bool em_orch_t::orchestrate", "void em_orch_t::advance_commands"],
    "src/em/metrics/em_metrics.cpp": ["void em_metrics_t::send_associated_sta_link_metrics_resp_msg",
                                      "void em_metrics_t::send_unassoc_sta_link_metrics_resp_msg",
                                      "void em_metrics_t::process_agent_state"],
}
CASES = [
    "gate-configured", "gate-topology", "gate-capability", "gate-transitional",
    "send-configured", "send-topology", "send-capability",
    "empty-configured", "empty-topology", "empty-capability",
    "failure-configured", "failure-topology", "failure-capability",
    "controller-configured", "controller-topology", "controller-pending",
    "three-radio-callback-pipeline", "stable-transitional-mixed-gate",
    "unassoc-old-sample", "unassoc-future-sample", "unassoc-unknown-mid", "unassoc-expired-mid",
]


def extract(text, signature):
    found = re.search(re.escape(signature) + r"\([^;]*?\)\s*\n\{.*?\n\}", text, re.S)
    if found is None:
        raise ValueError(f"missing production function: {signature}")
    return found.group()


HEADER = r"""
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>
#include "em_unassoc_query_tracker.h"
ENUMS
using mac_address_t = unsigned char[6];
using mac_addr_str_t = char[18];
constexpr int DPP_MAX_EN_CHANNELS = 2;
constexpr int MAX_EM_BUFF_SZ = 1024;
constexpr unsigned int EM_MAX_UNASSOC_STA = 8;
using queue_t = std::vector<void *>;
unsigned int queue_count(queue_t *queue) { return static_cast<unsigned int>(queue->size()); }
void queue_push(queue_t *queue, void *value) { queue->push_back(value); }
void *queue_peek(queue_t *queue, unsigned int index) { return queue->at(index); }
void *queue_remove(queue_t *queue, unsigned int index) {
    void *value = queue->at(index);
    queue->erase(queue->begin() + index);
    return value;
}
void *hash_map_get_first(queue_t *queue) { return queue->empty() ? nullptr : queue->front(); }
void *hash_map_get_next(queue_t *queue, void *value) {
    auto found = std::find(queue->begin(), queue->end(), value);
    return found == queue->end() || ++found == queue->end() ? nullptr : *found;
}
void em_printfout(const char *, ...) {}
namespace util {
std::string mac_to_string(const unsigned char *address) { return std::to_string(address[5]); }
}
struct ec_data_t { mac_address_t mac_addr{}; unsigned int ec_freqs[DPP_MAX_EN_CHANNELS]{}; int version = 0; };
struct Dpp { ec_data_t value; ec_data_t *get_dpp_info() { return &value; } };
struct Ec { bool cfg_onboard_enrollee(ec_data_t *) { return false; } };
struct dm_sta_t { struct { mac_address_t id{}; } m_sta_info; };
struct em_unassoc_sta_metric_entry_t {
    mac_address_t sta_mac{};
    unsigned char channel = 0, op_class = 0, rcpi = 0;
    unsigned int time_delta = 0;
};
struct em_unassoc_sta_metrics_rsp_t {
    unsigned int num_entries = 0;
    em_unassoc_sta_metric_entry_t entry[EM_MAX_UNASSOC_STA];
};
struct dm_easy_mesh_t {
    queue_t stations;
    queue_t *m_sta_assoc_map = &stations;
    em_unassoc_sta_metrics_rsp_t m_unassoc_sta_metrics_rsp;
    unsigned short m_unassoc_sta_metrics_msg_id = 0;
    uint64_t m_unassoc_sta_metrics_received_ms = 0;
    unsigned short message_id = 0;
    Dpp dpp;
    Dpp *get_dpp() { return &dpp; }
    unsigned short get_msg_id() { return message_id; }
    static void macbytes_to_string(const unsigned char *, char *text) { strcpy(text, "02:00:00:00:00:01"); }
};
struct em_cmd_t {
    em_cmd_type_t m_type = em_cmd_type_sta_link_metrics;
    dm_easy_mesh_t m_data_model;
    queue_t candidates;
    queue_t *m_em_candidates = &candidates;
    unsigned int starts = 0;
    em_cmd_type_t get_type() { return m_type; }
    dm_easy_mesh_t *get_data_model() { return &m_data_model; }
    dm_orch_type_t get_orch_op() { return dm_orch_type_sta_link_metrics; }
    const char *get_cmd_name() { return "fixture"; }
    void set_start_time() { starts++; }
    static const char *get_orch_op_str(dm_orch_type_t) { return "fixture"; }
    static const char *get_cmd_type_str(em_cmd_type_t) { return "fixture"; }
};
struct State {
    em_state_t value = em_state_agent_configured;
    em_state_t get_state() { return value; }
    void set_state(em_state_t next) { value = next; }
};
struct em_t;
struct em_metrics_t {
    em_unassoc_query_tracker m_unassoc_requests;
    unsigned int attempts = 0;
    int send_result = 1;
    struct Sent { unsigned char station; unsigned short mid; };
    std::vector<Sent> sent;
    struct Unassoc { unsigned short mid; em_unassoc_sta_metrics_rsp_t rows; std::set<unsigned char> classes; };
    std::vector<Unassoc> unassoc;
    em_cmd_t *get_current_cmd();
    dm_easy_mesh_t *get_data_model();
    em_state_t get_state();
    void set_state(em_state_t state);
private:
    void send_associated_sta_link_metrics_resp_msg();
public:
    void send_unassoc_sta_link_metrics_resp_msg();
    void process_agent_state();
    void process_ctrl_state() {}
    void send_beacon_metrics_response() { assert(false); }
    void send_link_quality_report() { assert(false); }
    int send_associated_link_metrics_response(unsigned char *station, unsigned short mid) {
        attempts++;
        if (send_result >= 0) sent.push_back({station[5], mid});
        return send_result;
    }
    void send_unassoc_sta_link_metrics_response(em_unassoc_sta_metrics_rsp_t *rows, unsigned short mid,
                                              const std::set<unsigned char> &classes) {
        unassoc.push_back({mid, *rows, classes});
    }
};
struct em_configuration_t { void process_agent_state() { assert(false); } void process_ctrl_state() {} };
struct em_capability_t { void process_ctrl_state() {} };
struct em_t : em_metrics_t, em_configuration_t, em_capability_t {
    em_cmd_t *m_cmd = nullptr;
    em_orch_state_t m_orch_state = em_orch_state_idle;
    em_service_type_t m_service_type = em_service_type_agent;
    State m_sm;
    dm_easy_mesh_t live;
    Ec ec;
    Ec *m_ec_manager = &ec;
    mac_address_t mac{2,0,0,0,0,1};
    em_state_t get_state() { return m_sm.get_state(); }
    void set_state(em_state_t value) { m_sm.set_state(value); }
    em_orch_state_t get_orch_state() { return m_orch_state; }
    void set_orch_state(em_orch_state_t);
    unsigned char *get_radio_interface_mac() { return mac; }
    static const char *state_2_str(em_state_t) { return "fixture"; }
    void set_renew_tx_count(int) {}
    int create_cce_ind_msg(unsigned char *, bool) { return 0; }
    int send_frame(unsigned char *, unsigned int) { return 0; }
    void set_client_steering_prev_state(em_state_t) {}
    void set_btm_report_prev_state(em_state_t) {}
    unsigned short get_btm_report_msg_id() { return 0; }
    void orch_execute(em_cmd_t *);
};
em_cmd_t *em_metrics_t::get_current_cmd() { return static_cast<em_t *>(this)->m_cmd; }
dm_easy_mesh_t *em_metrics_t::get_data_model() { return &static_cast<em_t *>(this)->live; }
em_state_t em_metrics_t::get_state() { return static_cast<em_t *>(this)->get_state(); }
void em_metrics_t::set_state(em_state_t state) { static_cast<em_t *>(this)->set_state(state); }
struct em_orch_t {
    queue_t pending, active;
    queue_t *m_pending = &pending, *m_active = &active;
    unsigned int m_pending_high_water = 0, destroyed = 0, timeout_calls = 0;
    std::recursive_mutex mutex;
    auto lock_commands() { return std::unique_lock<std::recursive_mutex>(mutex); }
    unsigned int build_candidates(em_cmd_t *command) { return queue_count(command->m_em_candidates); }
    void push_stats(em_cmd_t *) {}
    void pop_stats(em_cmd_t *) {}
    void update_stats(em_cmd_t *) { timeout_calls++; }
    void orch_transient(em_cmd_t *, em_t *) { timeout_calls++; }
    void destroy_command(em_cmd_t *command) {
        for (auto pointer : *command->m_em_candidates) static_cast<em_t *>(pointer)->m_cmd = nullptr;
        command->m_em_candidates->clear();
        destroyed++;
    }
    virtual bool is_em_ready_for_orch_exec(em_cmd_t *, em_t *) = 0;
    virtual bool is_em_ready_for_orch_fini(em_cmd_t *, em_t *) = 0;
    bool submit_command(em_cmd_t *);
    bool eligible_for_active(em_cmd_t *);
    bool orchestrate(em_cmd_t *, em_t *, bool);
    void advance_commands(bool);
    virtual ~em_orch_t() = default;
};
struct em_orch_agent_t : em_orch_t {
    bool is_em_ready_for_orch_exec(em_cmd_t *, em_t *) override;
    bool is_em_ready_for_orch_fini(em_cmd_t *, em_t *) override;
};
METHODS
int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
std::string key(unsigned char station) {
    const char bytes[] = {115,36,2,0,0,0,0,static_cast<char>(station)};
    return std::string(bytes, 8);
}
void prepare_unassoc(em_t &radio, em_cmd_t &command, unsigned short mid, unsigned char station,
                     int64_t observed, int64_t sent) {
    assert(radio.m_unassoc_requests.insert(mid, {key(station)}, sent));
    command.m_type = em_cmd_type_unassoc_sta_result;
    command.m_data_model.m_unassoc_sta_metrics_msg_id = mid;
    command.m_data_model.m_unassoc_sta_metrics_received_ms = observed;
    auto &response = command.m_data_model.m_unassoc_sta_metrics_rsp;
    response.num_entries = 1;
    auto &metric = response.entry[0];
    metric.sta_mac[0] = 2;
    metric.sta_mac[5] = station;
    metric.channel = 36;
    metric.op_class = 115;
    metric.rcpi = 82;
    command.candidates = {&radio};
}
void check(bool value, const char *message) { if (!value) throw std::string(message); }
void run(const std::string &name) {
    em_orch_agent_t orchestrator;
    em_t radio;
    em_cmd_t command;
    dm_sta_t station;
    station.m_sta_info.id[0] = 2;
    station.m_sta_info.id[5] = 77;
    command.m_data_model.message_id = 1234;
    command.m_data_model.stations = {&station};
    command.candidates = {&radio};
    em_state_t stable = name.find("topology") != std::string::npos ? em_state_agent_topo_synchronized :
        name.find("capability") != std::string::npos ? em_state_agent_ap_cap_report : em_state_agent_configured;
    radio.set_state(stable);
    if (name == "gate-transitional") {
        for (int state = em_state_agent_unconfigured; state <= em_state_agent_link_quality_report_pending; state++) {
            if (state == em_state_agent_configured || state == em_state_agent_topo_synchronized || state == em_state_agent_ap_cap_report) continue;
            radio.set_state(static_cast<em_state_t>(state));
            check(!orchestrator.is_em_ready_for_orch_exec(&command, &radio), "transitional state became executable");
        }
    } else if (name.rfind("gate-", 0) == 0) {
        check(orchestrator.is_em_ready_for_orch_exec(&command, &radio), "stable agent callback blocked");
    } else if (name.rfind("controller-", 0) == 0) {
        radio.m_service_type = em_service_type_ctrl;
        radio.set_state(name == "controller-pending" ? em_state_ctrl_sta_link_metrics_pending :
            name == "controller-topology" ? em_state_ctrl_topo_synchronized : em_state_ctrl_configured);
        radio.orch_execute(&command);
        check(radio.get_state() == em_state_ctrl_sta_link_metrics_pending && radio.m_orch_state == em_orch_state_progress,
              "controller query lifecycle changed");
        check(radio.m_cmd == &command && radio.attempts == 0 && radio.unassoc.empty(), "controller sends agent callback");
    } else if (name.rfind("send-", 0) == 0 || name.rfind("empty-", 0) == 0 || name.rfind("failure-", 0) == 0) {
        const bool empty = name.rfind("empty-", 0) == 0, failure = name.rfind("failure-", 0) == 0;
        if (empty) command.m_data_model.stations.clear();
        if (failure) radio.send_result = -1;
        orchestrator.submit_command(&command);
        orchestrator.advance_commands(false);
        check(radio.get_state() == stable, "agent stable state not preserved");
        check(radio.m_orch_state == em_orch_state_fini, "callback waits for protocol timer instead of completing");
        check(radio.attempts == (empty ? 0U : 1U), "real command rows not attempted once");
        check(radio.sent.size() == (empty || failure ? 0U : 1U), "fabricated success or missing actual send");
        if (!radio.sent.empty()) check(radio.sent[0].station == 77 && radio.sent[0].mid == 1234, "command MID or station changed");
        orchestrator.advance_commands(false);
        check(radio.m_orch_state == em_orch_state_idle && radio.m_cmd == nullptr && orchestrator.active.empty(), "completed command retains radio ownership");
        orchestrator.advance_commands(false);
        check(radio.attempts == (empty ? 0U : 1U) && orchestrator.timeout_calls == 0, "retry or timer dependency added");
    } else if (name == "three-radio-callback-pipeline") {
        em_t other, third;
        radio.set_state(em_state_agent_ap_cap_report);
        other.set_state(em_state_agent_topo_synchronized);
        third.set_state(em_state_agent_configured);
        command.candidates = {&radio, &other, &third};
        orchestrator.submit_command(&command);
        orchestrator.advance_commands(false);
        em_cmd_t first, second, third_query;
        const int64_t now = now_ms();
        prepare_unassoc(radio, first, 5648, 7, now, now - 20);
        prepare_unassoc(radio, second, 5665, 8, now, now - 20);
        prepare_unassoc(other, third_query, 0, 9, now, now - 20);
        orchestrator.submit_command(&first);
        orchestrator.submit_command(&second);
        orchestrator.submit_command(&third_query);
        for (int step = 0; step < 5; step++) orchestrator.advance_commands(false);
        check(radio.unassoc.size() == 2 && other.unassoc.size() == 1, "fresh native continuations blocked by unrelated STA callback");
        std::set<unsigned short> mids;
        for (const auto &reply : radio.unassoc) {
            mids.insert(reply.mid);
            check(reply.rows.num_entries == 1 && reply.rows.entry[0].rcpi == 82 && reply.rows.entry[0].time_delta < 6000,
                  "correlated fresh reply aged out or changed");
        }
        check(mids == std::set<unsigned short>{5648,5665} && other.unassoc[0].mid == 0, "MID ownership mixed");
        check(radio.get_state() == em_state_agent_ap_cap_report && other.get_state() == em_state_agent_topo_synchronized &&
              third.get_state() == em_state_agent_configured, "multi-radio topology state changed");
        check(orchestrator.pending.empty() && orchestrator.active.empty() && orchestrator.destroyed == 4 && orchestrator.timeout_calls == 0,
              "callbacks require cancellation or leave pending ownership");
    } else if (name == "stable-transitional-mixed-gate") {
        em_t transition;
        transition.set_state(em_state_agent_wsc_m2_pending);
        command.candidates = {&radio, &transition};
        orchestrator.submit_command(&command);
        orchestrator.advance_commands(false);
        check(transition.attempts == 0 && transition.get_state() == em_state_agent_wsc_m2_pending,
              "mixed command forced onboarding state");
    } else {
        const int64_t now = now_ms();
        prepare_unassoc(radio, command, 123, 7,
            name == "unassoc-old-sample" ? now - 7000 : name == "unassoc-future-sample" ? now + 3000 : now,
            name == "unassoc-expired-mid" ? now - 31000 : now - 8000);
        if (name == "unassoc-unknown-mid") command.m_data_model.m_unassoc_sta_metrics_msg_id = 124;
        radio.orch_execute(&command);
        if (name == "unassoc-old-sample" || name == "unassoc-future-sample") {
            check(radio.unassoc.size() == 1 && radio.unassoc[0].mid == 123 && radio.unassoc[0].rows.num_entries == 0,
                  "stale or future sample accepted");
        } else check(radio.unassoc.empty(), "unknown or expired MID emitted reply");
        check(radio.get_state() == stable, "unassoc state preservation changed");
    }
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    try { run(argv[1]); }
    catch (const std::string &error) { fprintf(stderr, "%s: %s\n", argv[1], error.c_str()); return 1; }
    printf("PASS %s\n", argv[1]);
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    report = {"source": str(source), "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "sources": [], "cases": [], "passed": False,
              "scope": "Complete production functions; in-memory queue/model adapters and recorded-send/failure transport stubs; no runtime qualification"}
    methods = []
    for relative, signatures in FUNCTIONS.items():
        path = source / relative
        text = path.read_text()
        methods.extend(extract(text, signature) for signature in signatures)
        report["sources"].append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "functions": signatures})
    header_path = source / "inc/em_base.h"
    header = header_path.read_text()
    enums = []
    for name in ("em_state_t", "em_cmd_type_t", "em_orch_state_t", "em_service_type_t", "dm_orch_type_t"):
        enums.append(re.search(r"typedef enum\s*\{[^}]*\}\s*" + name + ";", header, re.S).group())
    for relative in ("inc/em_base.h", "inc/em_unassoc_query_tracker.h"):
        path = source / relative
        report["sources"].append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    program = HEADER.replace("ENUMS", "\n".join(enums)).replace("METHODS", "\n\n".join(methods))
    with tempfile.TemporaryDirectory(prefix="native-sta-oneshot-") as temporary:
        binary = Path(temporary) / "test"
        command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", "-pthread",
                   "-x", "c++", "-", "-I", str(source / "inc"), "-o", str(binary)]
        compiled = subprocess.run(command, input=program, text=True, capture_output=True, timeout=60)
        report["compile"] = {"command": command, "exit_code": compiled.returncode, "stdout": compiled.stdout, "stderr": compiled.stderr,
                             "extracted_program_sha256": hashlib.sha256(program.encode()).hexdigest()}
        if compiled.returncode == 0:
            for case in CASES:
                result = subprocess.run([str(binary), case], text=True, capture_output=True, timeout=5)
                report["cases"].append({"name": case, "passed": result.returncode == 0, "exit_code": result.returncode,
                                        "stdout": result.stdout, "stderr": result.stderr})
                print(("PASS " if result.returncode == 0 else "FAIL ") + case)
        else:
            print(compiled.stderr)
    report["passed"] = len(report["cases"]) == len(CASES) and all(case["passed"] for case in report["cases"])
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(f"{sum(case['passed'] for case in report['cases'])}/{len(CASES)} passed")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
