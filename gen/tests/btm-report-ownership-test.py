#!/usr/bin/env python3
import argparse
from pathlib import Path
import subprocess
import tempfile


parser = argparse.ArgumentParser(description="Compile native BTM routing, decoding and command-isolation checks")
parser.add_argument("source_root", type=Path)
args = parser.parse_args()


def method(path, signature):
    source = (args.source_root / path).read_text()
    start = source.index(signature)
    return source[start:source.index("\n}\n", start) + 3]


decoder = method("src/em/em_msg.cpp", "bool em_msg_t::get_bss_id(")
handler = method("src/em/steering/em_steering.cpp", "int em_steering_t::handle_client_steering_report(")
controller = (args.source_root / "src/ctrl/em_ctrl.cpp").read_text()
start = controller.index("        case em_msg_type_client_cap_rprt:", controller.index("em_t *em_ctrl_t::find_em_for_msg_type"))
routing = controller[start:controller.index("        case em_msg_type_autoconf_resp:", start)]
assert "case em_msg_type_client_steering_btm_rprt:" in routing
assert controller.count("case em_msg_type_client_steering_btm_rprt:") == 1

program = r'''
#include <arpa/inet.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#define em_printfout(...) ((void)0)
using mac_address_t = unsigned char[6];
using mac_addr_str_t = char[18];
constexpr int EM_MAX_TLV_MEMBERS = 16, em_profile_type_2 = 2;
constexpr int em_msg_type_topo_notif = 1, em_msg_type_client_cap_rprt = 2;
constexpr int em_msg_type_ap_metrics_rsp = 3, em_msg_type_failed_conn = 4;
constexpr int em_msg_type_client_steering_btm_rprt = 0x8015;
constexpr int em_tlv_type_eom = 0, em_tlv_type_client_info = 0x90;
constexpr int em_tlv_type_client_assoc_event = 0x92, em_tlv_type_ap_metrics = 0x94;
constexpr int em_tlv_type_bssid = 0x83, em_tlv_type_steering_btm_rprt = 0x9c;
constexpr int em_state_ctrl_configured = 1;
const char *GLOBAL_NET_ID = "network";
struct __attribute__((packed)) em_tlv_t { unsigned char type; unsigned short len; unsigned char value[0]; };
struct __attribute__((packed)) em_raw_hdr_t { mac_address_t dst, src; unsigned short ether_type; };
struct __attribute__((packed)) em_cmdu_t { unsigned char version, reserved; unsigned short type, id; unsigned char fragment, flags; };
struct __attribute__((packed)) em_steering_btm_rprt_t { mac_address_t bssid, sta_mac_addr; unsigned char btm_status_code; mac_address_t target_bssid; };
struct em_msg_t {
    unsigned char *m_buff;
    unsigned int m_len;
    em_msg_t(unsigned char *buffer, unsigned int length): m_buff(buffer), m_len(length) {}
    em_msg_t(int, int, unsigned char *buffer, unsigned int length): em_msg_t(buffer, length) {}
    int validate(char **) { return 1; }
    bool get_bss_id(mac_address_t *);
};
struct radio_info { struct { mac_address_t ruid = {2,0,0,0,8,0}; } id; };
struct bss_info { struct { struct { mac_address_t mac = {2,0,0,0,8,0}; } ruid; } m_bss_info; };
struct dm_easy_mesh_t {
    mac_address_t source_bssid = {2,0,0,0,8,1};
    radio_info radio;
    bss_info bss;
    bool is_ap_mld_mac(unsigned char *) { return false; }
    unsigned int get_num_radios() { return 1; }
    radio_info *get_radio_info(unsigned int) { return &radio; }
    bss_info *get_bss(unsigned char *ruid, unsigned char *bssid) {
        return memcmp(ruid, radio.id.ruid, 6) == 0 && memcmp(bssid, source_bssid, 6) == 0 ? &bss : nullptr;
    }
    bool resolve_ap_mld_to_fallback_ruid(unsigned char *, unsigned char *) { return false; }
    static void macbytes_to_string(const unsigned char *address, char *output) {
        snprintf(output, 18, "%02x:%02x:%02x:%02x:%02x:%02x", address[0], address[1], address[2], address[3], address[4], address[5]);
    }
};
struct em_t {};
em_t owner;
void *hash_map_get(void *, const char *key) { return strcmp(key, "02:00:00:00:08:00") == 0 ? &owner : nullptr; }
struct em_ctrl_t {
    dm_easy_mesh_t model;
    void *m_em_map = nullptr;
    mac_address_t agent = {2,0,0,0,8,0x20};
    dm_easy_mesh_t *get_data_model(const char *, const unsigned char *source) {
        return memcmp(source, agent, 6) == 0 ? &model : nullptr;
    }
    em_t *route(unsigned char *data, unsigned int len);
};
struct em_steering_t {
    int state = 5, acks = 0;
    unsigned short candidate_mid = 123, steering_mid = 456, ack_mid = 0;
    mac_address_t ack_sta{}, ack_dst{}, ack_src{};
    void set_state(int value) { state = value; }
    void send_1905_ack_message(unsigned char *station, unsigned short message_id, int,
                                unsigned char *destination, unsigned char *source) {
        acks++;
        ack_mid = message_id;
        memcpy(ack_sta, station, 6);
        memcpy(ack_dst, destination, 6);
        memcpy(ack_src, source, 6);
    }
    int handle_client_steering_report(unsigned char *, unsigned int);
};
''' + decoder + handler + r'''
em_t *em_ctrl_t::route(unsigned char *data, unsigned int len) {
    auto *hdr = reinterpret_cast<em_raw_hdr_t *>(data);
    auto *cmdu = reinterpret_cast<em_cmdu_t *>(data + sizeof(em_raw_hdr_t));
    mac_address_t bssid{}, fallback_ruid{};
    mac_addr_str_t mac_str1{};
    em_t *em = nullptr;
    dm_easy_mesh_t *dm = nullptr;
    bss_info *bss = nullptr;
    unsigned int i;
    switch (ntohs(cmdu->type)) {
''' + routing + r'''
        default: break;
    }
    return em;
}
std::vector<unsigned char> report(bool prefix = false, unsigned int body_length = 13) {
    std::vector<unsigned char> bytes(sizeof(em_raw_hdr_t) + sizeof(em_cmdu_t), 0);
    auto *header = reinterpret_cast<em_raw_hdr_t *>(bytes.data());
    em_ctrl_t controller;
    memcpy(header->src, controller.agent, 6);
    header->dst[0] = 4;
    auto *cmdu = reinterpret_cast<em_cmdu_t *>(bytes.data() + sizeof(em_raw_hdr_t));
    cmdu->type = htons(em_msg_type_client_steering_btm_rprt);
    cmdu->id = htons(789);
    if (prefix) bytes.insert(bytes.end(), {0xdd, 0, 2, 7, 8});
    bytes.insert(bytes.end(), {0x9c, 0, static_cast<unsigned char>(body_length)});
    std::vector<unsigned char> body = {2,0,0,0,8,1, 2,0,0,0,3,0, 0, 2,0,0,0,9,1};
    bytes.insert(bytes.end(), body.begin(), body.begin() + body_length);
    bytes.insert(bytes.end(), {0,0,0});
    return bytes;
}
int main() {
    em_ctrl_t controller;
    em_steering_t radio;
    for (bool prefix : {false, true}) {
        for (unsigned int length : {13U, 19U}) {
            auto bytes = report(prefix, length);
            assert(controller.route(bytes.data(), bytes.size()) == &owner);
            for (int pending_state : {2, 3, 4, 5, 6}) {
                radio.state = pending_state;
                assert(radio.handle_client_steering_report(bytes.data(), bytes.size()) == 0);
                assert(radio.state == pending_state);
                assert(radio.candidate_mid == 123 && radio.steering_mid == 456);
                assert(radio.ack_mid == 789 && radio.ack_sta[4] == 3);
                assert(memcmp(radio.ack_dst, controller.agent, 6) == 0);
                assert(radio.ack_src[0] == 4);
            }
            bytes[sizeof(mac_address_t) + 4] = 9;
            assert(controller.route(bytes.data(), bytes.size()) == nullptr);
        }
    }
    auto wrong_bssid = report();
    wrong_bssid[sizeof(em_raw_hdr_t) + sizeof(em_cmdu_t) + sizeof(em_tlv_t) + 4] = 9;
    assert(controller.route(wrong_bssid.data(), wrong_bssid.size()) == nullptr);
    auto good = report(true);
    int previous_acks = radio.acks;
    for (unsigned int length = 0; length < good.size(); length++) {
        assert(radio.handle_client_steering_report(good.data(), length) == -1);
    }
    for (unsigned int length = 0; length < 13; length++) {
        auto short_body = report(false, length);
        assert(controller.route(short_body.data(), short_body.size()) == nullptr);
        assert(radio.handle_client_steering_report(short_body.data(), short_body.size()) == -1);
    }
    auto duplicate = report();
    auto duplicate_tlv = std::vector<unsigned char>(duplicate.begin() + 22, duplicate.begin() + 38);
    duplicate.insert(duplicate.end() - 3, duplicate_tlv.begin(), duplicate_tlv.end());
    assert(radio.handle_client_steering_report(duplicate.data(), duplicate.size()) == -1);
    assert(radio.acks == previous_acks);
    mac_address_t decoded{};
    unsigned char malformed[] = {0xdd, 0xff, 0xff};
    assert(!em_msg_t(malformed, sizeof(malformed)).get_bss_id(&decoded));
    assert(!em_msg_t(nullptr, 0).get_bss_id(&decoded));
    for (unsigned char tag : {em_tlv_type_client_info, em_tlv_type_ap_metrics, em_tlv_type_bssid}) {
        unsigned char tlvs[] = {tag, 0, 6, 2,0,0,0,8,1, 0,0,0};
        assert(em_msg_t(tlvs, sizeof(tlvs)).get_bss_id(&decoded));
        assert(memcmp(decoded, controller.model.source_bssid, 6) == 0);
    }
    unsigned char association[] = {0x92, 0, 12, 2,0,0,0,3,0, 2,0,0,0,8,1, 0,0,0};
    assert(em_msg_t(association, sizeof(association)).get_bss_id(&decoded));
    assert(memcmp(decoded, controller.model.source_bssid, 6) == 0);
    puts("PASS source AL/BSSID routing, absent-client ownership, bounded TLVs and late BTM command isolation");
}
'''

with tempfile.TemporaryDirectory(prefix="btm-report-ownership-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2",
                    "-x", "c++", "-", "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
