"""Compile the native channel serializer, ACK matching, retry and agent dispatch."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile


def method(source, signature):
    return re.search(re.escape(signature) + r'\(.*?\n\}', source, re.S).group()


root = Path(sys.argv[1])
channel = (root / 'src/em/channel/em_channel.cpp').read_text()
agent_path = Path(sys.argv[2]) if len(sys.argv) > 2 else root / 'src/agent/em_agent.cpp'
agent = agent_path.read_text()
methods = '\n'.join(method(channel, signature) for signature in [
    'short em_channel_t::create_operating_channel_report_tlv',
    'int em_channel_t::send_operating_channel_report_msg',
    'bool em_channel_t::operating_channel_report_peer_matches',
    'bool em_channel_t::acknowledge_operating_channel_report',
    'void em_channel_t::retry_operating_channel_report',
])
allocator = method((root / 'src/em/em_mgr.cpp').read_text(), 'unsigned short em_mgr_t::get_next_msg_id')
allocator += '\n' + method((root / 'src/agent/em_agent.cpp').read_text(), 'unsigned short em_agent_t::get_next_msg_id')
dispatch = method(agent, 'em_t *em_agent_t::find_em_for_msg_type').split(
    'case em_msg_type_1905_ack:', 1)[1].split('\n\t\tcase em_msg_type_channel_scan_rprt:', 1)[0]
program = r'''
#include <algorithm>
#include <atomic>
#include <arpa/inet.h>
#include <cassert>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <net/ethernet.h>
#include <vector>
#include <thread>
#define em_printfout(...) ((void)0)
constexpr unsigned int MAX_EM_BUFF_SZ = 1024, EM_MAX_TLV_MEMBERS = 16;
constexpr unsigned short ETH_P_1905 = 0x893a;
enum { em_msg_type_op_channel_rprt = 0x8008, em_msg_type_1905_ack = 0x8000,
       em_tlv_type_op_channel_report = 0x8f, em_tlv_type_eom = 0,
       em_profile_type_3 = 3, em_op_class_type_current = 1,
       em_state_agent_configured = 1, em_state_agent_steer_btm_res_pending = 2,
       em_state_agent_wsc_m2_pending = 3 };
using mac_address_t = unsigned char[6];
using mac_addr_str_t = char[18];
struct test_clock {
    using time_point = std::chrono::steady_clock::time_point;
    static time_point current;
    static time_point now() { return current; }
};
test_clock::time_point test_clock::current{};
struct em_raw_hdr_t { mac_address_t dst, src; unsigned short type; } __attribute__((packed));
struct em_cmdu_t {
    unsigned short type, id;
    unsigned char last_frag_ind, relay_ind;
} __attribute__((packed));
struct em_tlv_t { unsigned char type; unsigned short len; unsigned char value[0]; } __attribute__((packed));
struct em_op_class_ch_rprt_t { unsigned char op_class, channel; };
struct em_op_channel_rprt_t {
    mac_address_t ruid;
    unsigned char op_classes_num;
    em_op_class_ch_rprt_t op_classes[0];
} __attribute__((packed));
struct em_msg_t {
    em_msg_t(int, int, unsigned char *, unsigned int) {}
    int validate(char **) { return 1; }
};
struct dm_op_class_t {
    struct {
        struct { mac_address_t ruid = {}; unsigned int type = em_op_class_type_current; } id;
        unsigned int op_class = 81, channel = 6, tx_power = 10;
    } m_op_class_info;
};
struct dm_easy_mesh_t {
    unsigned int m_num_opclass = 3;
    dm_op_class_t m_op_class[3];
    mac_address_t controller = {2, 0, 0, 0, 0, 1};
    mac_address_t agent = {2, 0, 0, 0, 0, 2};
    unsigned char *get_ctl_mac() { return controller; }
    unsigned char *get_agent_al_interface_mac() { return agent; }
    static void macbytes_to_string(unsigned char *, char *text) { text[0] = 0; }
};
struct em_mgr_t {
    unsigned short m_msg_id = 0;
    virtual unsigned short get_next_msg_id();
};
struct em_channel_t {
    std::mutex m_operating_channel_report_mutex;
    std::vector<unsigned char> m_pending_operating_channel_report;
    test_clock::time_point m_operating_channel_retry_due{};
    unsigned int m_operating_channel_retry_interval = 2;
    bool operating_channel_report_peer_matches();
    dm_easy_mesh_t model;
    em_mgr_t *manager;
    unsigned int radio_index = 0;
    bool fail_send = false;
    std::vector<std::vector<unsigned char>> sent;
    em_channel_t(em_mgr_t *owner) : manager(owner) {
        for (unsigned int index = 0; index < 3; index++) {
            model.m_op_class[index].m_op_class_info.id.ruid[5] = index + 1;
        }
    }
    dm_easy_mesh_t *get_data_model() { return &model; }
    em_mgr_t *get_mgr() { return manager; }
    unsigned char *get_radio_interface_mac() {
        return model.m_op_class[radio_index].m_op_class_info.id.ruid;
    }
    int send_frame(unsigned char *buffer, unsigned int size) {
        sent.emplace_back(buffer, buffer + size);
        return fail_send ? -1 : static_cast<int>(size);
    }
    short create_operating_channel_report_tlv(unsigned char *);
    int send_operating_channel_report_msg();
    bool acknowledge_operating_channel_report(unsigned char *, unsigned int);
    void retry_operating_channel_report();
};
struct em_t : em_channel_t {
    int state = em_state_agent_configured;
    unsigned short btm_mid = 0;
    em_t(em_mgr_t *owner) : em_channel_t(owner) {}
    int get_state() { return state; }
    unsigned short get_btm_report_msg_id() { return btm_mid; }
};
struct em_agent_t : em_mgr_t {
    std::atomic<unsigned short> m_agent_msg_id{0};
    unsigned short get_next_msg_id() override;
    std::vector<em_t *> radios;
    void get_all_em_for_al_mac(unsigned char *address, std::vector<em_t *> &result) {
        for (auto radio : radios) {
            if (memcmp(address, radio->model.agent, sizeof(mac_address_t)) == 0) result.push_back(radio);
        }
    }
    em_t *dispatch(unsigned char *data, unsigned int len) {
        em_t *em = nullptr;
        em_raw_hdr_t *hdr = reinterpret_cast<em_raw_hdr_t *>(data);
        em_cmdu_t *cmdu = reinterpret_cast<em_cmdu_t *>(data + sizeof(em_raw_hdr_t));
        switch (ntohs(cmdu->type)) {
            case em_msg_type_1905_ack:
''' + dispatch + r'''
            default: break;
        }
        return em;
    }
};
''' + allocator + methods.replace('std::chrono::steady_clock::now()', 'test_clock::now()') + r'''
std::vector<unsigned char> ack_for(const std::vector<unsigned char> &report) {
    std::vector<unsigned char> ack(sizeof(em_raw_hdr_t) + sizeof(em_cmdu_t), 0);
    auto *original = reinterpret_cast<const em_raw_hdr_t *>(report.data());
    auto *header = reinterpret_cast<em_raw_hdr_t *>(ack.data());
    auto *cmdu = reinterpret_cast<em_cmdu_t *>(ack.data() + sizeof(em_raw_hdr_t));
    auto *original_cmdu = reinterpret_cast<const em_cmdu_t *>(report.data() + sizeof(em_raw_hdr_t));
    memcpy(header->src, original->dst, sizeof(mac_address_t));
    memcpy(header->dst, original->src, sizeof(mac_address_t));
    cmdu->type = htons(em_msg_type_1905_ack);
    cmdu->id = original_cmdu->id;
    return ack;
}
int main() {
    em_agent_t agent;
    em_mgr_t &manager = agent;
    em_t first(&manager), second(&manager), third(&manager);
    second.radio_index = 1;
    third.radio_index = 2;
    agent.radios = {&first, &second, &third};
    std::vector<std::thread> workers;
    for (auto radio : agent.radios) workers.emplace_back([radio]() {
        assert(radio->send_operating_channel_report_msg() > 0);
    });
    workers.emplace_back([&]() { first.btm_mid = manager.get_next_msg_id(); });
    for (auto &worker : workers) worker.join();
    auto first_ack = ack_for(first.sent[0]);
    first.state = em_state_agent_steer_btm_res_pending;
    const auto btm_mid = first.btm_mid;
    auto pending_btm_ack = first_ack;
    reinterpret_cast<em_cmdu_t *>(pending_btm_ack.data() + sizeof(em_raw_hdr_t))->id = htons(btm_mid);
    assert(agent.dispatch(pending_btm_ack.data(), pending_btm_ack.size()) == &first);
    for (auto radio : agent.radios) assert(!radio->m_pending_operating_channel_report.empty());
    assert(agent.dispatch(first_ack.data(), first_ack.size()) == nullptr);
    assert(first.state == em_state_agent_steer_btm_res_pending && first.btm_mid == btm_mid);
    assert(first.m_pending_operating_channel_report.empty());
    assert(!second.m_pending_operating_channel_report.empty());
    assert(!third.m_pending_operating_channel_report.empty());
    for (unsigned int tick = 0; tick < 100; tick++) first.retry_operating_channel_report();
    assert(first.sent.size() == 1);
    assert(!first.acknowledge_operating_channel_report(first_ack.data(), first_ack.size()));
    std::puts("PASS: ACK consumes only its source/MID owner; acknowledged radios are idle; BTM state preserved");

    auto second_ack = ack_for(second.sent[0]);
    for (unsigned int corruption = 0; corruption < 4; corruption++) {
        auto invalid = second_ack;
        auto *header = reinterpret_cast<em_raw_hdr_t *>(invalid.data());
        auto *cmdu = reinterpret_cast<em_cmdu_t *>(invalid.data() + sizeof(em_raw_hdr_t));
        if (corruption == 0) header->src[5]++;
        if (corruption == 1) header->dst[5]++;
        if (corruption == 2) cmdu->id++;
        if (corruption == 3) cmdu->type++;
        assert(!second.acknowledge_operating_channel_report(invalid.data(), invalid.size()));
    }
    assert(!second.acknowledge_operating_channel_report(second_ack.data(), 1));
    second.state = em_state_agent_wsc_m2_pending;
    for (unsigned int tick = 0; tick < 45; tick++) {
        test_clock::current += std::chrono::seconds(2);
        second.retry_operating_channel_report();
    }
    assert(second.sent.size() == 7);
    for (const auto &packet : second.sent) assert(packet == second.sent.front());
    assert(second.m_operating_channel_retry_interval == 30);
    assert(second.state == em_state_agent_wsc_m2_pending);
    agent.dispatch(second_ack.data(), second_ack.size());
    assert(second.m_pending_operating_channel_report.empty());
    std::puts("PASS: lost report/ACK retries identical native bytes and MID with 2/4/8/16/30-second backoff");

    auto obsolete_ack = ack_for(third.sent[0]);
    third.model.m_op_class[2].m_op_class_info.channel = 37;
    third.fail_send = true;
    assert(third.send_operating_channel_report_msg() < 0);
    assert(!third.acknowledge_operating_channel_report(obsolete_ack.data(), obsolete_ack.size()));
    third.fail_send = false;
    test_clock::current += std::chrono::seconds(2);
    third.retry_operating_channel_report();
    assert(third.sent.size() == 3 && third.sent[1] == third.sent[2]);
    auto latest_ack = ack_for(third.sent.back());
    agent.dispatch(latest_ack.data(), latest_ack.size());
    assert(third.m_pending_operating_channel_report.empty());
    auto btm_ack = first_ack;
    auto *btm_cmdu = reinterpret_cast<em_cmdu_t *>(btm_ack.data() + sizeof(em_raw_hdr_t));
    btm_cmdu->id = htons(first.btm_mid);
    assert(agent.dispatch(btm_ack.data(), btm_ack.size()) == &first);
    std::puts("PASS: newer channel report replaces pending bytes; failed local sends retry; unrelated BTM ACK still routes");

    for (unsigned int identity = 0; identity < 2; identity++) {
        first.send_operating_channel_report_msg();
        auto old_ack = ack_for(first.sent.back());
        const auto sent_before = first.sent.size();
        first.state = em_state_agent_wsc_m2_pending;
        if (identity == 0) first.model.controller[5]++;
        else first.model.agent[5]++;
        assert(!first.acknowledge_operating_channel_report(old_ack.data(), old_ack.size()));
        test_clock::current += std::chrono::seconds(60);
        first.retry_operating_channel_report();
        assert(first.sent.size() == sent_before && first.m_pending_operating_channel_report.empty());
        first.send_operating_channel_report_msg();
        const auto retry_before = first.sent.size();
        if (identity == 0) first.model.controller[5]++;
        else first.model.agent[5]++;
        test_clock::current += std::chrono::seconds(60);
        first.retry_operating_channel_report();
        assert(first.sent.size() == retry_before && first.m_pending_operating_channel_report.empty());
    }
    std::puts("PASS: controller/local-AL changes invalidate serialized reports before ACK or retry even while WSC blocks new publication");
}
'''
with tempfile.TemporaryDirectory(prefix='operating-channel-ack-recovery-') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-x', 'c++', '-', '-o', str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
