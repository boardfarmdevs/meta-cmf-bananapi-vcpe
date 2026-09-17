"""Compile isolated production agent methods against fake native bus/model endpoints."""

from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import tempfile


parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
native = args.source
snapshots = {relative: (native / relative).read_bytes() for relative in (
    "src/agent/em_agent.cpp", "inc/em_native_backhaul_agent.h", "inc/em_rooted_admission_probe.h")}
source = snapshots["src/agent/em_agent.cpp"].decode()
signatures = [
    "bool em_agent_t::handle_native_backhaul_frame",
    "bool em_agent_t::read_native_root_context",
    "void em_agent_t::poll_native_root_admission",
    "void em_agent_t::process_native_root_reply",
    "bool em_agent_t::send_native_backhaul_reply",
    "bool em_agent_t::native_backhaul_station_matches",
    "bool em_agent_t::read_native_backhaul_link",
    "void em_agent_t::complete_native_backhaul_request",
    "void em_agent_t::process_native_backhaul_request",
    "void em_agent_t::poll_native_backhaul_request",
    "void em_agent_t::observe_native_backhaul_callback",
]
methods = "\n\n".join(re.search(re.escape(signature) + r"\(.*?\n\}", source, re.S).group()
                       for signature in signatures)
program = r"""
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstdarg>
#include <strings.h>
#include <string>
#include <functional>
#include <net/if.h>
#include <sys/random.h>
#include "em_native_backhaul_agent.h"
#include "em_rooted_admission_probe.h"
static uint64_t fixture_now_ms = 100000;
namespace std { namespace chrono {
steady_clock::time_point steady_clock::now() noexcept {
    return steady_clock::time_point(milliseconds(fixture_now_ms));
}
} }
using mac_address_t = unsigned char[6];
using namespace em_native_backhaul;
constexpr int em_msg_type_bh_steering_req = 0x8019;
constexpr int em_msg_type_bh_steering_rsp = 0x801a;
constexpr int em_tlv_type_bh_steering_req = 0x9e;
constexpr int em_tlv_type_bh_steering_rsp = 0x9f;
constexpr int em_tlv_type_error_code = 0xa3;
struct em_bh_steering_req_t { unsigned char bytes[14]; };
struct em_bh_steering_resp_t { unsigned char bytes[13]; };
enum { em_event_type_frame, em_vap_mode_ap, em_vap_mode_sta, em_haul_type_backhaul,
       em_op_class_type_current, bus_error_success, bus_data_type_string, bus_data_type_bytes };
enum wifi_connection_status_t { wifi_connection_status_disconnected, wifi_connection_status_connected };
constexpr size_t EM_MAX_EVENT_DATA_LEN = 409600;
void em_printfout(const char *, ...) {}
namespace util {
std::string mac_to_string(const unsigned char *address) {
    char result[18];
    snprintf(result, sizeof(result), "%02x:%02x:%02x:%02x:%02x:%02x", address[0], address[1],
        address[2], address[3], address[4], address[5]);
    return result;
}
}
struct raw_data_t { int data_type; union { void *bytes; } raw_data; unsigned int raw_data_len; };
struct wifi_bus_desc_t {
    std::function<int(void *, const char *, raw_data_t *)> bus_data_get_fn;
    std::function<int(void *, const char *, raw_data_t *)> bus_set_fn;
};
struct em_frame_event_t { unsigned char *frame; unsigned int frame_len; };
struct em_event_t { int type; union { em_frame_event_t fevt; } u; };
struct em_bus_event_t { unsigned int data_len; union { unsigned char raw_buff[2048]; } u; };
struct Interface { unsigned char mac[6]{}; };
struct em_bss_info_t {
    int vap_mode = em_vap_mode_sta;
    struct { int haul_type = em_haul_type_backhaul; } id;
    Interface bssid;
    Interface ruid;
    unsigned char sta_mac[6]{};
};
struct em_op_class_info_t {
    struct { int type = em_op_class_type_current; unsigned char ruid[6]{}; } id;
    unsigned int op_class = 115;
    unsigned int channel = 36;
};
const mac_address station_mac{{2, 0, 0, 0, 1, 1}};
const mac_address old_parent{{2, 0, 0, 0, 2, 1}};
const mac_address target_mac{{2, 0, 0, 0, 3, 1}};
const mac_address local_ap{{2, 0, 0, 0, 4, 1}};
struct dm_easy_mesh_t {
    bool colocated = false;
    mac_address controller{{2, 0, 0, 0, 0, 1}};
    mac_address agent{{2, 0, 0, 0, 0, 2}};
    std::vector<em_bss_info_t> bsses;
    std::vector<em_op_class_info_t> operating;
    dm_easy_mesh_t() {
        em_bss_info_t sta{};
        std::copy(station_mac.begin(), station_mac.end(), sta.sta_mac);
        sta.ruid.mac[5] = 9;
        bsses.push_back(sta);
        sta.vap_mode = em_vap_mode_ap;
        std::copy(local_ap.begin(), local_ap.end(), sta.bssid.mac);
        bsses.push_back(sta);
        em_op_class_info_t channel{};
        channel.id.ruid[5] = 9;
        operating.push_back(channel);
    }
    static int mac_address_from_name(const char *name, unsigned char *address) {
        const mac_address actual = std::string(name) == "wlan-sta1" ? station_mac : local_ap;
        std::copy(actual.begin(), actual.end(), address);
        return 0;
    }
    unsigned char *get_ctrl_al_interface_mac() { return controller.data(); }
    unsigned char *get_agent_al_interface_mac() { return agent.data(); }
    bool get_colocated() { return colocated; }
    unsigned int get_num_radios() { return 2; }
    unsigned int get_num_bss() { return bsses.size(); }
    unsigned int get_num_op_class() { return operating.size(); }
    em_bss_info_t *get_bss_info(unsigned int index) { return &bsses.at(index); }
    em_op_class_info_t *get_op_class_info(unsigned int index) { return &operating.at(index); }
};
struct em_t {
    std::vector<std::vector<unsigned char>> sent;
    bool fail = false;
    int send_native_backhaul_frame(unsigned char *frame, unsigned int length) {
        if (fail) return -1;
        sent.emplace_back(frame, frame + length);
        return 0;
    }
};
struct cJSON {
    cJSON *child = nullptr;
    cJSON *next = nullptr;
    int type = 0;
    double valuedouble = 0;
    const char *valuestring = nullptr;
    const char *name = nullptr;
};
cJSON *test_document = nullptr;
cJSON *cJSON_Parse(const char *) { return test_document; }
void cJSON_Delete(cJSON *) {}
cJSON *cJSON_GetObjectItemCaseSensitive(cJSON *object, const char *name) {
    if (object == nullptr) return nullptr;
    for (auto *item = object->child; item != nullptr; item = item->next) {
        if (item->name != nullptr && strcmp(item->name, name) == 0) return item;
    }
    return nullptr;
}
bool cJSON_IsNumber(cJSON *item) { return item != nullptr && item->type == 1; }
bool cJSON_IsString(cJSON *item) { return item != nullptr && item->type == 2; }
bool cJSON_IsTrue(cJSON *item) { return item != nullptr && item->type == 3; }
#define cJSON_ArrayForEach(element, array) for (element = array ? array->child : nullptr; element; element = element->next)
struct em_agent_t {
    transactions m_native_backhaul_transactions;
    em_rooted_admission::transaction_matcher m_root_admission;
    em_rooted_admission::link_context m_root_context{};
    uint64_t m_root_context_since = 0;
    uint64_t m_root_next_probe = 0;
    bool root_enabled = false;
    bool root_admitted = false;
    bool root_ambiguous = false;
    bool root_short = false;
    uint64_t root_generation = 1;
    unsigned int root_writes = 0;
    unsigned short next_mid = 200;
    std::array<unsigned char, 22> root_written{};
    dm_easy_mesh_t m_data_model;
    int m_bus_hdl = 0;
    wifi_bus_desc_t descriptor;
    em_t node;
    std::vector<em_event_t *> queued;
    mac_address actual_parent = old_parent;
    bool connected = true;
    bool get_failure = false;
    bool set_failure = false;
    bool invalid_status_length = false;
    unsigned int interface_encoding = 0;
    unsigned int writes = 0;
    mac_address written{};
    em_agent_t() {
        descriptor.bus_data_get_fn = [this](void *, const char *path, raw_data_t *value) {
            if (get_failure) return -1;
            const std::string property(path);
            if (property.find("X_RDK_BackhaulRoot") != std::string::npos) {
                if (!root_enabled || (!root_ambiguous && property.find("STA.2.") == std::string::npos)) return -1;
                value->data_type = bus_data_type_bytes;
                value->raw_data_len = root_short ? 21 : 22;
                auto *bytes = static_cast<unsigned char *>(calloc(22, 1));
                value->raw_data.bytes = bytes;
                for (unsigned int index = 0; index < 8; ++index)
                    bytes[index] = root_generation >> (56 - 8 * index);
                memcpy(bytes + 8, station_mac.data(), 6);
                memcpy(bytes + 14, actual_parent.data(), 6);
                bytes[20] = connected;
                bytes[21] = root_admitted;
            } else if (property.find("InterfaceName") != std::string::npos) {
                const char *name = property.find("STA.2.") != std::string::npos ? "wlan-sta1" : "wlan0";
                value->data_type = bus_data_type_string;
                std::string encoded = name;
                if (interface_encoding == 1) encoded.push_back('\0');
                if (interface_encoding == 2) encoded.clear();
                if (interface_encoding == 3) encoded.assign(IFNAMSIZ, 'x');
                if (interface_encoding == 4) encoded.insert(2, 1, '\0');
                value->raw_data_len = encoded.size();
                value->raw_data.bytes = malloc(encoded.size() ? encoded.size() : 1);
                memcpy(value->raw_data.bytes, encoded.data(), encoded.size());
            } else {
                assert(property == "Device.WiFi.STA.2.Connection.Status");
                value->data_type = bus_data_type_bytes;
                value->raw_data_len = sizeof(wifi_connection_status_t) + 6;
                value->raw_data.bytes = malloc(value->raw_data_len);
                const auto status = connected ? wifi_connection_status_connected : wifi_connection_status_disconnected;
                memcpy(value->raw_data.bytes, &status, sizeof(status));
                memcpy(static_cast<unsigned char *>(value->raw_data.bytes) + sizeof(status), actual_parent.data(), 6);
                if (invalid_status_length) --value->raw_data_len;
            }
            return static_cast<int>(bus_error_success);
        };
        descriptor.bus_set_fn = [this](void *, const char *path, raw_data_t *value) {
            if (std::string(path) == "Device.WiFi.STA.2.X_RDK_BackhaulRoot") {
                assert(value->data_type == bus_data_type_bytes && value->raw_data_len == 22);
                memcpy(root_written.data(), value->raw_data.bytes, 22);
                ++root_writes;
                return set_failure ? -1 : static_cast<int>(bus_error_success);
            }
            assert(std::string(path) == "Device.WiFi.STA.2.Bssid");
            assert(value->data_type == bus_data_type_bytes && value->raw_data_len == 6);
            ++writes;
            memcpy(written.data(), value->raw_data.bytes, 6);
            return set_failure ? -1 : static_cast<int>(bus_error_success);
        };
    }
    ~em_agent_t() { for (auto *event : queued) { free(event->u.fevt.frame); free(event); } }
    wifi_bus_desc_t *get_bus_descriptor() { return &descriptor; }
    bool is_data_model_initialized() { return true; }
    unsigned short get_next_msg_id() { return ++next_mid; }
    bool read_native_root_context(em_rooted_admission::link_context &, unsigned int &,
        std::array<unsigned char, 22> &);
    void poll_native_root_admission();
    void process_native_root_reply(const unsigned char *, size_t);
    em_t *get_al_node() { return &node; }
    void push_to_queue(em_event_t *event) { queued.push_back(event); }
    bool handle_native_backhaul_frame(unsigned char *, unsigned int, em_t *);
    bool send_native_backhaul_reply(const request &, bool, unsigned char = 0);
    bool native_backhaul_station_matches(unsigned int, const mac_address &);
    bool read_native_backhaul_link(unsigned int, mac_address &, bool &);
    void complete_native_backhaul_request(transaction &, unsigned char);
    void process_native_backhaul_request(const unsigned char *, size_t);
    void poll_native_backhaul_request();
    void observe_native_backhaul_callback(em_bus_event_t *);
};
METHODS

void root_case(const std::string &name) {
    em_agent_t agent;
    agent.root_enabled = true;
    if (name == "admitted-renews") agent.root_admitted = true;
    if (name == "send-failure-retry") agent.node.fail = true;
    const uint64_t initial = fixture_now_ms;
    agent.poll_native_root_admission();
    if (name == "send-failure-retry") {
        assert(agent.node.sent.empty() && agent.m_root_admission.pending());
        agent.node.fail = false;
        fixture_now_ms += 250;
        agent.poll_native_root_admission();
        assert(agent.node.sent.size() == 1 && agent.root_writes == 0);
        return;
    }
    assert(agent.node.sent.size() == 1 && agent.root_writes == 0);
    if (name == "initial-grace") {
        for (unsigned int elapsed = 250; elapsed < 10000; elapsed += 250) {
            fixture_now_ms = initial + elapsed;
            agent.poll_native_root_admission();
            assert(agent.root_writes == 0);
        }
        for (unsigned int elapsed = 10000; elapsed <= 12250 && !agent.root_writes; elapsed += 250) {
            fixture_now_ms = initial + elapsed;
            agent.poll_native_root_admission();
        }
        assert(agent.root_writes == 1 && agent.root_written[21] == 2 && agent.writes == 0);
        return;
    }
    if (name == "retry-250") {
        fixture_now_ms = initial + 249;
        agent.poll_native_root_admission();
        assert(agent.node.sent.size() == 1);
        fixture_now_ms = initial + 250;
        agent.poll_native_root_admission();
        assert(agent.node.sent.size() == 2 && agent.node.sent[0] == agent.node.sent[1]);
        return;
    }
    em_rooted_admission::wire_frame response{};
    assert(em_rooted_admission::controller_reply(agent.node.sent[0].data(),
        agent.node.sent[0].size(), agent.m_data_model.controller, response));
    if (name == "stale-generation-reply") ++agent.root_generation;
    if (name == "stale-parent-reply") agent.actual_parent = target_mac;
    if (name == "disconnected-reply") agent.connected = false;
    if (name == "late-reply") fixture_now_ms = initial + 2001;
    if (name == "admit-queue-failure") agent.set_failure = true;
    agent.process_native_root_reply(response.data(), response.size());
    if (name == "late-reply") {
        em_rooted_admission::link_context context{};
        unsigned int radio_instance = 0;
        std::array<unsigned char, 22> state{};
        assert(agent.read_native_root_context(context, radio_instance, state));
        assert(agent.root_writes == 0 && agent.m_root_admission.pending() &&
            agent.m_root_admission.expired(context, fixture_now_ms));
        agent.poll_native_root_admission();
        assert(agent.root_writes == 0 && agent.writes == 0 && agent.node.sent.size() == 2 &&
            agent.node.sent[0] != agent.node.sent[1] && agent.m_root_admission.pending() &&
            !agent.m_root_admission.expired(context, fixture_now_ms));
        em_rooted_admission::message previous{}, renewed{};
        assert(em_rooted_admission::decode(agent.node.sent[0].data(), agent.node.sent[0].size(), previous));
        assert(em_rooted_admission::decode(agent.node.sent[1].data(), agent.node.sent[1].size(), renewed));
        assert(previous.nonce != renewed.nonce);
        return;
    }
    if (name == "stale-generation-reply" || name == "stale-parent-reply" ||
        name == "disconnected-reply") {
        assert(agent.root_writes == 0 && !agent.m_root_admission.pending());
        return;
    }
    assert(agent.root_writes == (agent.root_admitted ? 0U : 1U));
    agent.process_native_root_reply(response.data(), response.size());
    assert(agent.root_writes == (agent.root_admitted ? 0U : 1U));
    const auto first_query = agent.node.sent[0];
    if (name != "admit-queue-failure") agent.root_admitted = true;
    fixture_now_ms = initial + 499;
    agent.poll_native_root_admission();
    assert(agent.node.sent.size() == 1);
    fixture_now_ms = initial + 500;
    agent.poll_native_root_admission();
    assert(agent.node.sent.size() == 2 && agent.node.sent.back() != first_query);
    if (name == "renewal-500" || name == "admitted-renews") return;
    if (name == "admit-queue-failure") {
        agent.set_failure = false;
        assert(em_rooted_admission::controller_reply(agent.node.sent.back().data(),
            agent.node.sent.back().size(), agent.m_data_model.controller, response));
        agent.process_native_root_reply(response.data(), response.size());
        assert(agent.root_writes == 2 && agent.root_written[21] == 0);
        return;
    }
    if (name == "changed-context-not-revoked") {
        ++agent.root_generation;
        agent.actual_parent = target_mac;
        fixture_now_ms = initial + 2750;
        agent.poll_native_root_admission();
        assert(agent.root_writes == 1 && agent.m_root_admission.pending());
        return;
    }
    if (name == "renewal-replay") {
        agent.process_native_root_reply(response.data(), response.size());
        assert(agent.root_writes == 1 && agent.m_root_admission.pending());
        return;
    }
    if (name == "late-renewal-reply-cannot-suppress-revoke") {
        assert(em_rooted_admission::controller_reply(agent.node.sent.back().data(),
            agent.node.sent.back().size(), agent.m_data_model.controller, response));
        fixture_now_ms = initial + 2501;
        agent.process_native_root_reply(response.data(), response.size());
        fixture_now_ms = initial + 2750;
        agent.poll_native_root_admission();
        assert(agent.root_writes == 2 && agent.root_written[21] == 2 && agent.writes == 0);
        return;
    }
    fixture_now_ms = initial + 2500;
    agent.poll_native_root_admission();
    assert(agent.root_writes == 1);
    if (name == "revoke-queue-failure") agent.set_failure = true;
    fixture_now_ms = initial + 2750;
    agent.poll_native_root_admission();
    assert(agent.root_writes == 2 && agent.root_written[21] == 2 && agent.writes == 0);
    assert(agent.root_written[7] == 1 &&
        memcmp(agent.root_written.data() + 14, old_parent.data(), 6) == 0);
    if (name == "revoke-queue-failure") {
        assert(agent.m_root_admission.pending());
        agent.set_failure = false;
        fixture_now_ms += 250;
        agent.poll_native_root_admission();
        assert(agent.root_writes == 3 && agent.root_written[21] == 2 && !agent.m_root_admission.pending());
    }
}
std::vector<unsigned char> request_bytes(const request &command) {
    auto frame = reply(command, true);
    frame.resize(22);
    std::copy(command.agent.begin(), command.agent.end(), frame.begin());
    std::copy(command.controller.begin(), command.controller.end(), frame.begin() + 6);
    frame[17] = 0x19;
    frame.insert(frame.end(), {0x9e, 0, 14});
    frame.insert(frame.end(), command.station.begin(), command.station.end());
    frame.insert(frame.end(), command.target.begin(), command.target.end());
    frame.insert(frame.end(), {command.operating_class, command.channel, 0, 0, 0});
    return frame;
}
request make_command() {
    request command{};
    command.agent = {{2, 0, 0, 0, 0, 2}};
    command.controller = {{2, 0, 0, 0, 0, 1}};
    command.station = station_mac;
    command.target = target_mac;
    command.message_id = 0x1234;
    command.operating_class = 115;
    command.channel = 36;
    return command;
}
void issue(em_agent_t &agent, const request &command) {
    const auto frame = request_bytes(command);
    agent.process_native_backhaul_request(frame.data(), frame.size());
}
void check_response(const std::vector<unsigned char> &frame, const request &command, unsigned char error) {
    assert(frame == reply(command, false, error));
    assert(frame[22] == 0x9f && frame[24] == 13 && frame[37] == (error ? 1 : 0));
    assert(frame.size() == (error ? 51 : 41));
    if (error) assert(frame[38] == 0xa3 && frame[40] == 7 && frame[41] == error);
}
int main(int argc, char **argv) {
    if (argc == 2) {
        root_case(argv[1]);
        printf("PASS: root renewal %s\n", argv[1]);
        return 0;
    }
    const auto command = make_command();
    const auto frame = request_bytes(command);
    request decoded{};
    assert(decode_request(frame.data(), frame.size(), decoded) && decoded == command);
    for (size_t length = 0; length < frame.size(); ++length)
        assert(!decode_request(frame.data(), length, decoded));
    for (size_t index : {12, 13, 14, 15, 16, 17, 20, 21, 23, 24}) {
        auto malformed = frame;
        malformed[index] ^= 1;
        assert(!decode_request(malformed.data(), malformed.size(), decoded));
    }
    auto duplicate = frame;
    duplicate.insert(duplicate.end() - 3, frame.begin() + 22, frame.end() - 3);
    assert(!decode_request(duplicate.data(), duplicate.size(), decoded));
    auto padded = frame;
    padded.resize(60);
    assert(decode_request(padded.data(), padded.size(), decoded));
    padded.back() = 1;
    assert(!decode_request(padded.data(), padded.size(), decoded));
    auto invalid = command;
    invalid.target.fill(0);
    auto malformed = request_bytes(invalid);
    assert(!decode_request(malformed.data(), malformed.size(), decoded));
    invalid = command;
    invalid.target[0] = 1;
    malformed = request_bytes(invalid);
    assert(!decode_request(malformed.data(), malformed.size(), decoded));
    auto zero_mid = command;
    zero_mid.message_id = 0;
    const auto zero_frame = request_bytes(zero_mid);
    assert(decode_request(zero_frame.data(), zero_frame.size(), decoded) && decoded.message_id == 0);
    assert(reply(command, true).size() == 25);

    em_agent_t queued;
    auto incoming = frame;
    assert(queued.handle_native_backhaul_frame(incoming.data(), incoming.size(), nullptr));
    assert(queued.queued.size() == 1 && queued.writes == 0);
    incoming[25] ^= 1;
    assert(queued.queued[0]->u.fevt.frame[25] == frame[25]);
    auto foreign_type = frame;
    foreign_type[17] = 0x0f;
    assert(!queued.handle_native_backhaul_frame(foreign_type.data(), foreign_type.size(), nullptr));

    em_agent_t agent;
    {
        em_agent_t rooted;
        rooted.root_enabled = true;
        rooted.poll_native_root_admission();
        assert(rooted.node.sent.size() == 1 && rooted.writes == 0);
        rooted.poll_native_root_admission();
        assert(rooted.node.sent.size() == 1);
        em_rooted_admission::wire_frame root_reply{};
        assert(em_rooted_admission::controller_reply(rooted.node.sent[0].data(),
            rooted.node.sent[0].size(), rooted.m_data_model.controller, root_reply));
        assert(rooted.handle_native_backhaul_frame(root_reply.data(), root_reply.size(), nullptr));
        assert(rooted.queued.size() == 1 && rooted.root_writes == 0);
        rooted.process_native_root_reply(root_reply.data(), root_reply.size());
        assert(rooted.root_writes == 1 && rooted.root_written[7] == 1 && rooted.writes == 0);
        rooted.process_native_root_reply(root_reply.data(), root_reply.size());
        assert(rooted.root_writes == 1);
        fixture_now_ms += 500;
        rooted.poll_native_root_admission();
        assert(em_rooted_admission::controller_reply(rooted.node.sent.back().data(),
            rooted.node.sent.back().size(), rooted.m_data_model.controller, root_reply));
        ++rooted.root_generation;
        rooted.process_native_root_reply(root_reply.data(), root_reply.size());
        assert(rooted.root_writes == 1 && !rooted.m_root_admission.pending());
        for (unsigned int failure = 0; failure < 5; ++failure) {
            em_agent_t unavailable;
            unavailable.root_enabled = true;
            if (failure == 0) unavailable.connected = false;
            if (failure == 1) unavailable.get_failure = true;
            if (failure == 2) unavailable.root_ambiguous = true;
            if (failure == 3) unavailable.root_short = true;
            if (failure == 4) unavailable.m_data_model.colocated = true;
            unavailable.poll_native_root_admission();
            assert(unavailable.node.sent.empty() && !unavailable.m_root_admission.pending());
        }
        puts("PASS: native root probe uses fresh association identity, queue isolation, replay rejection and fail-closed bus state");
    }
    issue(agent, command);
    assert(agent.writes == 1 && agent.written == command.target);
    assert(agent.node.sent.size() == 1 && agent.node.sent.back() == reply(command, true));
    issue(agent, command);
    assert(agent.writes == 1 && agent.node.sent.size() == 2);
    agent.poll_native_backhaul_request();
    assert(agent.node.sent.size() == 2);
    agent.connected = false;
    agent.actual_parent = target_mac;
    agent.poll_native_backhaul_request();
    assert(agent.node.sent.size() == 2);
    agent.connected = true;
    agent.invalid_status_length = true;
    agent.poll_native_backhaul_request();
    assert(agent.node.sent.size() == 2);
    agent.invalid_status_length = false;
    agent.poll_native_backhaul_request();
    assert(agent.node.sent.size() == 3 && agent.m_native_backhaul_transactions.pending() == nullptr);
    check_response(agent.node.sent.back(), command, 0);
    issue(agent, command);
    assert(agent.writes == 1 && agent.node.sent.size() == 5);
    check_response(agent.node.sent.back(), command, 0);
    auto conflict = command;
    conflict.target[5] += 1;
    issue(agent, conflict);
    assert(agent.writes == 1 && agent.node.sent.size() == 5);

    for (unsigned int encoding = 0; encoding < 5; ++encoding) {
        em_agent_t encoded;
        encoded.interface_encoding = encoding;
        issue(encoded, command);
        if (encoding <= 1) {
            assert(encoded.writes == 1 && encoded.m_native_backhaul_transactions.pending() != nullptr);
        } else {
            assert(encoded.writes == 0 && encoded.m_native_backhaul_transactions.pending() == nullptr);
            check_response(encoded.node.sent.back(), command, association_failed);
        }
    }
    for (unsigned int case_index = 0; case_index < 8; ++case_index) {
        em_agent_t rejected;
        auto bad = command;
        unsigned char error = target_not_suitable;
        if (case_index == 0) bad.target = local_ap;
        if (case_index == 1) bad.station[5] += 10;
        if (case_index == 2) { bad.channel = 40; error = cannot_operate_on_channel; }
        if (case_index == 3) { bad.operating_class = 81; error = cannot_operate_on_channel; }
        if (case_index == 4) { rejected.connected = false; error = association_failed; }
        if (case_index == 5) { rejected.get_failure = true; error = association_failed; }
        if (case_index == 6) { rejected.invalid_status_length = true; error = association_failed; }
        if (case_index == 7) bad.target = bad.station;
        issue(rejected, bad);
        assert(rejected.writes == 0 && rejected.node.sent.size() == 2);
        check_response(rejected.node.sent.back(), bad, error);
    }
    for (unsigned int case_index = 0; case_index < 3; ++case_index) {
        em_agent_t rejected;
        auto foreign = command;
        if (case_index == 0) foreign.controller[5] += 1;
        if (case_index == 1) foreign.agent[5] += 1;
        if (case_index == 2) rejected.m_data_model.colocated = true;
        issue(rejected, foreign);
        assert(rejected.writes == 0 && rejected.node.sent.empty());
    }
    em_agent_t failed_set;
    failed_set.set_failure = true;
    issue(failed_set, command);
    check_response(failed_set.node.sent.back(), command, association_failed);
    em_agent_t failed_ack;
    failed_ack.node.fail = true;
    issue(failed_ack, command);
    assert(failed_ack.writes == 0 && failed_ack.m_native_backhaul_transactions.pending() == nullptr);
    em_agent_t already;
    already.actual_parent = target_mac;
    issue(already, command);
    assert(already.writes == 0);
    check_response(already.node.sent.back(), command, 0);
    em_agent_t pending;
    issue(pending, command);
    auto second = command;
    second.message_id += 1;
    issue(pending, second);
    assert(pending.writes == 1 && pending.m_native_backhaul_transactions.pending()->command == command);
    check_response(pending.node.sent.back(), second, association_failed);
    pending.m_native_backhaul_transactions.pending()->deadline = clock::now();
    pending.poll_native_backhaul_request();
    check_response(pending.node.sent.back(), command, target_not_suitable);
    pending.connected = true;
    pending.actual_parent = target_mac;
    const auto responses_before = pending.node.sent.size();
    pending.poll_native_backhaul_request();
    assert(pending.node.sent.size() == responses_before);
    issue(pending, second);
    assert(pending.writes == 1);
    check_response(pending.node.sent.back(), second, association_failed);

    em_agent_t callback;
    issue(callback, command);
    const auto station_text = util::mac_to_string(station_mac.data());
    const auto parent_text = util::mac_to_string(target_mac.data());
    cJSON status{nullptr, nullptr, 3, 0, nullptr, "ConnectStatus"};
    cJSON parent{nullptr, &status, 2, 0, parent_text.c_str(), "BSSID"};
    cJSON station{nullptr, &parent, 2, 0, station_text.c_str(), "MAC"};
    cJSON radio{nullptr, &station, 1, 1, nullptr, "RadioIndex"};
    cJSON vap{&radio, nullptr, 0, 0, nullptr, nullptr};
    cJSON vaps{&vap, nullptr, 0, 0, nullptr, "WifiVapConfig"};
    cJSON root{&vaps, nullptr, 0, 0, nullptr, nullptr};
    test_document = &root;
    em_bus_event_t event{};
    event.data_len = 2;
    memcpy(event.u.raw_buff, "{}", 2);
    callback.observe_native_backhaul_callback(&event);
    assert(callback.node.sent.size() == 1);
    callback.actual_parent = target_mac;
    radio.valuedouble = 0;
    callback.observe_native_backhaul_callback(&event);
    assert(callback.node.sent.size() == 1);
    radio.valuedouble = 1;
    status.type = 0;
    callback.observe_native_backhaul_callback(&event);
    assert(callback.node.sent.size() == 1);
    status.type = 3;
    callback.observe_native_backhaul_callback(&event);
    check_response(callback.node.sent.back(), command, 0);

    transactions history;
    const auto now = clock::now();
    for (unsigned short counter = 0; counter < 40; ++counter) {
        auto historical = command;
        historical.message_id = counter;
        auto *entry = history.insert(historical, 2, now);
        assert(entry != nullptr);
        history.complete(*entry, 0, now);
        assert(history.size() <= replay_limit);
    }
    assert(history.size() == replay_limit);
    history.prune(now + std::chrono::seconds(61));
    assert(history.size() == 0);
    auto *active = history.insert(command, 2, now);
    assert(active != nullptr);
    assert(history.insert(second, 2, now) == nullptr);
    history.prune(now + std::chrono::seconds(61));
    assert(history.pending() != nullptr);
    for (unsigned short counter = 100; counter < 140; ++counter) {
        auto rejected = command;
        rejected.message_id = counter;
        history.remember_rejection(rejected, association_failed, now);
        assert(history.size() <= replay_limit);
        assert(history.pending() != nullptr && history.pending()->command == command);
    }
    puts("PASS: production BH request/ACK/response, queue isolation, exact native STA actuation/readback, callback, timeout, replay, malformed and unsafe targets");
}
""".replace("METHODS", methods)

with tempfile.TemporaryDirectory(prefix="native-backhaul-agent-") as temporary:
    executable = Path(temporary) / "test"
    compiled = subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-x", "c++", "-",
                               "-I", str(native / "inc"), "-o", str(executable)],
                              input=program, text=True, capture_output=True, timeout=60)
    result = {"source": str(native.resolve()), "source_sha256": {
        relative: hashlib.sha256(content).hexdigest() for relative, content in snapshots.items()},
        "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "functions": signatures, "scope": "actual agent methods; deterministic monotonic clock, stub bus/model/transport",
        "compile_exit": compiled.returncode, "compile_stderr": compiled.stderr, "cases": []}
    if compiled.returncode == 0:
        for case in ("existing-backhaul", "initial-grace", "retry-250", "renewal-500", "admitted-renews",
                     "stale-generation-reply", "stale-parent-reply", "disconnected-reply", "late-reply",
                     "admit-queue-failure", "changed-context-not-revoked", "renewal-replay",
                     "revoke-queue-failure", "expiry-revokes", "send-failure-retry",
                     "late-renewal-reply-cannot-suppress-revoke"):
            executed = subprocess.run([str(executable)] + ([] if case == "existing-backhaul" else [case]),
                                      text=True, capture_output=True, timeout=15)
            result["cases"].append({"name": case, "exit_code": executed.returncode,
                                    "passed": executed.returncode == 0, "stdout": executed.stdout,
                                    "stderr": executed.stderr})
            print(executed.stdout or executed.stderr, end="")
    else:
        print(compiled.stderr, end="")
    mesh_callback = re.search(r"void em_agent_t::handle_onewifi_mesh_sta_cb\(.*?\n\}", source, re.S).group()
    tick = re.search(r"void em_agent_t::handle_1s_tick\(.*?\n\}", source, re.S).group()
    root_tick = re.search(r"void em_agent_t::handle_250ms_tick\(.*?\n\}", source, re.S).group()
    result["static_checks"] = {
        "callback-before-orchestration": mesh_callback.index("observe_native_backhaul_callback(evt)") <
            mesh_callback.index("is_cmd_type_in_progress"),
        "backhaul-tick": "poll_native_backhaul_request();" in tick,
        "root-250ms-tick": "poll_native_root_admission();" in root_tick,
        "no-external-forcing": all(forbidden not in methods for forbidden in (
            "set_msg_id", "get_msg_id", "system(", "popen(", "iw ", "wpa_cli", "commit_config")),
    }
    result["sources_unchanged"] = all((native / path).read_bytes() == content for path, content in snapshots.items())
    result["passed"] = (compiled.returncode == 0 and all(case["passed"] for case in result["cases"])
                        and all(result["static_checks"].values()) and result["sources_unchanged"])
    if args.output:
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    if not result["passed"]:
        raise SystemExit(1)

print("PASS: callback precedes orchestration; independent MID state; no external reparent/topology forcing")
