"""Compile production unassociated-result radio ownership and empty/partial wire completion."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile


native = Path(sys.argv[1])
orchestration = (native / "src/orch/em_orch_agent.cpp").read_text()
selection = orchestration.split("            case em_cmd_type_unassoc_sta_result:", 1)[1].split(
    "            default:", 1
)[0]
selection = "            case em_cmd_type_unassoc_sta_result:" + selection
metrics = (native / "src/em/metrics/em_metrics.cpp").read_text()
declarations = (native / "inc/em_metrics.h").read_text()
ownership = re.search(r"    bool owns_native_unassoc_query\(.*?\n    \}", declarations, re.S).group()
methods = "\n\n".join(re.search(re.escape(signature) + r"\(.*?\n\}", metrics, re.S).group()
                      for signature in (
                          "unsigned short em_metrics_t::create_unassoc_sta_link_metrics_resp_tlv",
                          "void em_metrics_t::send_unassoc_sta_link_metrics_resp_msg",
                          "void em_metrics_t::send_unassoc_sta_link_metrics_response",
                      ))
header = (native / "inc/em_base.h").read_text()
limit = re.search(r"^#define EM_MAX_UNASSOC_STA .*?$", header, re.M).group()
program = r"""
#include <arpa/inet.h>
#include <cassert>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <pthread.h>
#include <string>
#include <vector>
#include <algorithm>
#include "em_unassoc_query_tracker.h"
LIMIT
using mac_address_t = unsigned char[6];
constexpr unsigned int MAX_EM_BUFF_SZ = 1024;
constexpr unsigned short ETH_P_1905 = 0x893a;
constexpr unsigned short em_msg_type_unassoc_sta_link_metrics_rsp = 0x800e;
constexpr unsigned char em_tlv_type_unassoc_sta_link_metric_rsp = 0x98;
constexpr unsigned char em_tlv_type_eom = 0;
enum { em_cmd_type_unassoc_sta_result, em_cmd_type_other, em_state_agent_configured };
struct __attribute__((packed)) em_cmdu_t {
    unsigned char version, reserved;
    unsigned short type, id;
    unsigned char fragment;
    unsigned char reserved_flags:6, relay_ind:1, last_frag_ind:1;
};
struct __attribute__((packed)) em_tlv_t {
    unsigned char type;
    unsigned short len;
    unsigned char value[0];
};
struct __attribute__((packed)) em_unassoc_sta_metric_t {
    mac_address_t sta_mac;
    unsigned char channel;
    unsigned int time_delta;
    unsigned char rcpi;
};
struct __attribute__((packed)) em_unassoc_sta_link_metrics_rsp_t {
    unsigned char op_class;
    unsigned char num_sta;
    em_unassoc_sta_metric_t sta_metrics[0];
};
struct em_unassoc_sta_metric_entry_t {
    mac_address_t sta_mac{};
    unsigned char channel = 0, op_class = 0, rcpi = 0;
    unsigned int time_delta = 0;
};
struct em_unassoc_sta_metrics_rsp_t {
    unsigned int num_entries = 0;
    em_unassoc_sta_metric_entry_t entry[EM_MAX_UNASSOC_STA];
};
static_assert(sizeof(em_cmdu_t) == 8 && sizeof(em_unassoc_sta_metric_t) == 12, "wire sizes");
struct dm_easy_mesh_t {
    em_unassoc_sta_metrics_rsp_t m_unassoc_sta_metrics_rsp;
    unsigned short m_unassoc_sta_metrics_msg_id = 0;
    uint64_t m_unassoc_sta_metrics_received_ms = 0;
    mac_address_t controller{2,0,0,0,0,1}, agent{2,0,0,0,0,2};
    unsigned char *get_ctl_mac() { return controller; }
    unsigned char *get_agent_al_interface_mac() { return agent; }
};
struct em_t;
using Queue = std::vector<em_t *>;
struct em_cmd_t {
    int m_type = em_cmd_type_unassoc_sta_result;
    dm_easy_mesh_t model;
    Queue candidates;
    Queue *m_em_candidates = &candidates;
    int get_type() const { return m_type; }
    dm_easy_mesh_t *get_data_model() { return &model; }
};
void em_printfout(const char *, ...) {}
namespace util {
std::string mac_to_string(const unsigned char *mac) { return std::to_string(mac[5]); }
}
struct em_metrics_t {
    em_unassoc_query_tracker m_unassoc_requests;
    dm_easy_mesh_t model;
    em_cmd_t *command = nullptr;
    std::vector<std::vector<unsigned char>> sent;
    int state = -1;
    dm_easy_mesh_t *get_data_model() { return &model; }
    em_cmd_t *get_current_cmd() { return command; }
    void set_state(int value) { state = value; }
    int send_frame(unsigned char *frame, unsigned int length) {
        sent.emplace_back(frame, frame + length);
        return static_cast<int>(length);
    }
    OWNERSHIP
    unsigned short create_unassoc_sta_link_metrics_resp_tlv(unsigned char *, unsigned char, em_unassoc_sta_metrics_rsp_t *);
    void send_unassoc_sta_link_metrics_resp_msg();
    void send_unassoc_sta_link_metrics_response(em_unassoc_sta_metrics_rsp_t *, unsigned short, const std::set<unsigned char> &);
};
METHODS
struct em_t : em_metrics_t {
    bool al = false;
    mac_address_t ruid{2,0,0,0,0,0};
    bool is_al_interface_em() { return al; }
    unsigned char *get_radio_interface_mac() { return ruid; }
};
void queue_push(Queue *queue, em_t *radio) { queue->push_back(radio); }
void *hash_map_get_first(Queue *map) { return map->empty() ? nullptr : map->front(); }
void *hash_map_get_next(Queue *map, void *radio) {
    auto found = std::find(map->begin(), map->end(), radio);
    return found == map->end() || ++found == map->end() ? nullptr : *found;
}
struct Manager {
    pthread_mutex_t m_mutex = PTHREAD_MUTEX_INITIALIZER;
    Queue radios;
    Queue *m_em_map = &radios;
    ~Manager() { pthread_mutex_destroy(&m_mutex); }
};
struct em_orch_agent_t {
    Manager *m_mgr;
    unsigned int build_candidates(em_cmd_t *pcmd) {
        unsigned int count = 0;
        em_t *em;
        pthread_mutex_lock(&m_mgr->m_mutex);
        em = static_cast<em_t *>(hash_map_get_first(m_mgr->m_em_map));
        while (em != nullptr) {
            switch (pcmd->m_type) {
                SELECTION
                default: break;
            }
            em = static_cast<em_t *>(hash_map_get_next(m_mgr->m_em_map, em));
        }
        pthread_mutex_unlock(&m_mgr->m_mutex);
        return count;
    }
};
int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
std::string key(unsigned char op_class, unsigned char channel, unsigned char station) {
    std::string result{static_cast<char>(op_class), static_cast<char>(channel)};
    const char mac[] = {2,0,0,0,0,static_cast<char>(station)};
    result.append(mac, 6);
    return result;
}
void add_metric(em_cmd_t &command, unsigned char op_class, unsigned char channel,
                unsigned char station, unsigned int age = 200, unsigned char rcpi = 90) {
    auto &response = command.model.m_unassoc_sta_metrics_rsp;
    assert(response.num_entries < EM_MAX_UNASSOC_STA);
    auto &sample = response.entry[response.num_entries++];
    sample.sta_mac[0] = 2;
    sample.sta_mac[5] = station;
    sample.op_class = op_class;
    sample.channel = channel;
    sample.rcpi = rcpi;
    sample.time_delta = age;
}
struct Parsed {
    unsigned char op_class;
    std::vector<em_unassoc_sta_metric_t> metrics;
};
std::vector<Parsed> decode(const std::vector<unsigned char> &frame, unsigned short mid) {
    const unsigned char controller[] = {2,0,0,0,0,1}, agent[] = {2,0,0,0,0,2};
    assert(frame.size() >= 30 && frame.size() <= MAX_EM_BUFF_SZ);
    assert(memcmp(frame.data(), controller, 6) == 0 && memcmp(frame.data() + 6, agent, 6) == 0);
    const auto *cmdu = reinterpret_cast<const em_cmdu_t *>(frame.data() + 14);
    assert(ntohs(cmdu->type) == em_msg_type_unassoc_sta_link_metrics_rsp);
    assert(ntohs(cmdu->id) == mid && cmdu->last_frag_ind == 1);
    assert(frame[12] == 0x89 && frame[13] == 0x3a);
    std::vector<Parsed> result;
    size_t offset = 22;
    bool ended = false;
    while (offset + 3 <= frame.size()) {
        const auto *tlv = reinterpret_cast<const em_tlv_t *>(frame.data() + offset);
        const size_t length = ntohs(tlv->len);
        offset += 3;
        assert(offset + length <= frame.size());
        if (tlv->type == em_tlv_type_eom) {
            assert(length == 0 && offset == frame.size());
            ended = true;
            break;
        }
        assert(tlv->type == em_tlv_type_unassoc_sta_link_metric_rsp && length >= 2);
        assert(length == 2U + static_cast<size_t>(tlv->value[1]) * sizeof(em_unassoc_sta_metric_t));
        Parsed parsed{tlv->value[0], {}};
        for (unsigned int index = 0; index < tlv->value[1]; ++index) {
            em_unassoc_sta_metric_t metric;
            memcpy(&metric, tlv->value + 2 + index * sizeof(metric), sizeof(metric));
            parsed.metrics.push_back(metric);
        }
        result.push_back(parsed);
        offset += length;
    }
    assert(ended);
    return result;
}
int main() {
    em_t al, radio_first, radio_owner;
    al.al = true;
    radio_first.ruid[5] = 1;
    radio_owner.ruid[5] = 2;
    Manager manager;
    manager.radios = {&al, &radio_first, &radio_owner};
    em_orch_agent_t orchestration{&manager};
    const int64_t now = now_ms();
    const std::set<std::string> expected{key(115, 36, 1), key(115, 36, 2)};
    assert(al.m_unassoc_requests.insert(0, expected, now - 1000));
    assert(radio_owner.m_unassoc_requests.insert(0, expected, now - 1000));
    assert(radio_first.m_unassoc_requests.insert(11, expected, now - 1000));
    em_cmd_t empty;
    empty.model.m_unassoc_sta_metrics_msg_id = 0;
    empty.model.m_unassoc_sta_metrics_received_ms = now - 400;
    assert(orchestration.build_candidates(&empty) == 1 && empty.candidates[0] == &radio_owner);
    radio_owner.command = &empty;
    radio_owner.send_unassoc_sta_link_metrics_resp_msg();
    auto result = decode(radio_owner.sent.back(), 0);
    assert(result.size() == 1 && result[0].op_class == 115 && result[0].metrics.empty());
    assert(!radio_owner.owns_native_unassoc_query(0) && radio_first.owns_native_unassoc_query(11));
    assert(radio_owner.state == em_state_agent_configured);
    empty.candidates.clear();
    assert(orchestration.build_candidates(&empty) == 0);
    radio_owner.send_unassoc_sta_link_metrics_resp_msg();
    assert(radio_owner.sent.size() == 1);
    puts("PASS: exact MID-zero owner beats map order, ignores AL interface, routes empty result, emits zero-STA TLV and completes once");

    em_cmd_t partial;
    partial.model.m_unassoc_sta_metrics_msg_id = 11;
    partial.model.m_unassoc_sta_metrics_received_ms = now - 400;
    add_metric(partial, 115, 36, 1);
    add_metric(partial, 115, 36, 9);
    assert(orchestration.build_candidates(&partial) == 1 && partial.candidates[0] == &radio_first);
    radio_first.command = &partial;
    radio_first.model.m_unassoc_sta_metrics_rsp.num_entries = 64;
    radio_first.send_unassoc_sta_link_metrics_resp_msg();
    result = decode(radio_first.sent.back(), 11);
    assert(result.size() == 1 && result[0].metrics.size() == 1);
    const auto sample = result[0].metrics[0];
    assert(sample.sta_mac[5] == 1 && sample.channel == 36 && sample.rcpi == 90);
    assert(ntohl(sample.time_delta) >= 600 && ntohl(sample.time_delta) < 6000);
    assert(partial.model.m_unassoc_sta_metrics_rsp.num_entries == 0);
    assert(radio_first.model.m_unassoc_sta_metrics_rsp.num_entries == 64);
    assert(!radio_first.owns_native_unassoc_query(11));
    puts("PASS: partial callback completes exact query, rejects unexpected STA, ignores live-DM pollution and includes command-queue age");

    assert(radio_owner.m_unassoc_requests.insert(22, {key(81, 1, 3), key(115, 36, 4)}, now - 1000));
    em_cmd_t mixed;
    mixed.model.m_unassoc_sta_metrics_msg_id = 22;
    mixed.model.m_unassoc_sta_metrics_received_ms = now - 400;
    add_metric(mixed, 115, 36, 4);
    assert(orchestration.build_candidates(&mixed) == 1 && mixed.candidates[0] == &radio_owner);
    radio_owner.command = &mixed;
    radio_owner.send_unassoc_sta_link_metrics_resp_msg();
    result = decode(radio_owner.sent.back(), 22);
    assert(result.size() == 2 && result[0].op_class == 81 && result[0].metrics.empty());
    assert(result[1].op_class == 115 && result[1].metrics.size() == 1);
    puts("PASS: partial multi-opclass completion retains requested empty class and measured class with the same MID");

    for (unsigned short identifier : {31, 32, 33, 34}) {
        assert(radio_owner.m_unassoc_requests.insert(identifier, {key(115, 36, 1)}, now - 1000));
        em_cmd_t rejected;
        rejected.model.m_unassoc_sta_metrics_msg_id = identifier;
        rejected.model.m_unassoc_sta_metrics_received_ms = now - 400;
        add_metric(rejected, identifier == 34 ? 81 : 115, 36, 1, identifier == 31 ? 1000 : 200);
        if (identifier == 32) rejected.model.m_unassoc_sta_metrics_received_ms = now - 7000;
        if (identifier == 33) rejected.model.m_unassoc_sta_metrics_received_ms = now + 3000;
        assert(orchestration.build_candidates(&rejected) == 1 && rejected.candidates[0] == &radio_owner);
        radio_owner.command = &rejected;
        radio_owner.send_unassoc_sta_link_metrics_resp_msg();
        result = decode(radio_owner.sent.back(), identifier);
        assert(result.size() == 1 && result[0].metrics.empty());
    }
    em_cmd_t unknown;
    unknown.model.m_unassoc_sta_metrics_msg_id = 999;
    assert(orchestration.build_candidates(&unknown) == 0);
    assert(radio_owner.m_unassoc_requests.insert(55, expected, now - 31000));
    unknown.model.m_unassoc_sta_metrics_msg_id = 55;
    assert(orchestration.build_candidates(&unknown) == 0);
    radio_owner.command = nullptr;
    const size_t sent_before = radio_owner.sent.size();
    radio_owner.send_unassoc_sta_link_metrics_resp_msg();
    unknown.m_type = em_cmd_type_other;
    radio_owner.command = &unknown;
    radio_owner.send_unassoc_sta_link_metrics_resp_msg();
    assert(radio_owner.sent.size() == sent_before);
    puts("PASS: predating/stale/future/wrong-key samples complete empty; unknown/expired MIDs and absent/wrong command never emit stale data");

    std::set<std::string> maximum;
    em_cmd_t bounded;
    bounded.model.m_unassoc_sta_metrics_msg_id = 65535;
    bounded.model.m_unassoc_sta_metrics_received_ms = now - 400;
    for (unsigned int index = 1; index <= EM_MAX_UNASSOC_STA; ++index) {
        maximum.insert(key(115, 36, static_cast<unsigned char>(index)));
        add_metric(bounded, 115, 36, static_cast<unsigned char>(index));
    }
    assert(radio_owner.m_unassoc_requests.insert(65535, maximum, now - 1000));
    manager.radios = {&radio_owner, &radio_first, &al};
    assert(orchestration.build_candidates(&bounded) == 1 && bounded.candidates[0] == &radio_owner);
    radio_owner.command = &bounded;
    radio_owner.send_unassoc_sta_link_metrics_resp_msg();
    result = decode(radio_owner.sent.back(), 65535);
    assert(result.size() == 1 && result[0].metrics.size() == EM_MAX_UNASSOC_STA);
    puts("PASS: maximum bounded result, MID 65535, altered radio-map order, exact CMDU/TLV lengths and EOM");
}
""".replace("LIMIT", limit).replace("OWNERSHIP", ownership).replace("METHODS", methods).replace("SELECTION", selection)

with tempfile.TemporaryDirectory(prefix="unassoc-radio-completion-") as temporary:
    executable = Path(temporary) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                    "-pthread", "-x", "c++", "-", "-I", str(native / "inc"),
                    "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
