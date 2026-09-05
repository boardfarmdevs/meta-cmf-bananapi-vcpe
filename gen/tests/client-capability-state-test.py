#!/usr/bin/env python3
import argparse
import subprocess
import tempfile
from pathlib import Path


parser = argparse.ArgumentParser(description="Compile the real client capability handler against state/reply test doubles")
parser.add_argument("source", type=Path, help="patched src/em/capability/em_capability.cpp")
args = parser.parse_args()
source = args.source.read_text()
start = source.index("void em_capability_t::handle_client_cap_query(")
end = source.index("\nint em_capability_t::handle_bsta_cap_query(", start)
handler = source[start:end]
harness = r'''
#include <arpa/inet.h>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

using mac_address_t = unsigned char[6];
using bssid_t = unsigned char[6];
constexpr int EM_MAX_TLV_MEMBERS = 4;
constexpr int em_msg_type_client_cap_query = 1;
constexpr int em_profile_type_3 = 3;
constexpr int em_state_agent_configured = 999;
constexpr unsigned char em_tlv_type_eom = 0;
constexpr unsigned char em_tlv_type_client_info = 1;
struct em_raw_hdr_t { unsigned char bytes[14]; };
struct em_cmdu_t { uint16_t id; };
struct __attribute__((packed)) em_tlv_t {
    unsigned char type;
    uint16_t len;
    unsigned char value[0];
};
bool valid_message = true;
struct em_msg_t {
    em_msg_t(int, int, unsigned char *, unsigned int) {}
    int validate(char **) { return valid_message; }
};
template <typename... Values> void em_printfout(const char *, Values...) {}
namespace util {
std::string mac_to_string(const unsigned char *) { return "test-station"; }
}
class em_capability_t {
public:
    int state = 0;
    int result = 0;
    int replies = 0;
    unsigned short reply_id = 0;
    mac_address_t reply_sta = {};
    bssid_t reply_bss = {};
    void set_state(int next) { state = next; }
    int send_client_cap_report_msg(const unsigned char *station,
                                  const unsigned char *bssid, unsigned short identifier) {
        replies++;
        reply_id = identifier;
        std::memcpy(reply_sta, station, sizeof(reply_sta));
        std::memcpy(reply_bss, bssid, sizeof(reply_bss));
        return result;
    }
    void handle_client_cap_query(unsigned char *, unsigned int);
};
'''
harness += handler
harness += r'''
int main() {
    std::vector<unsigned char> packet(sizeof(em_raw_hdr_t) + sizeof(em_cmdu_t)
        + 2 * sizeof(em_tlv_t) + 2 * sizeof(mac_address_t), 0);
    auto *message = reinterpret_cast<em_cmdu_t *>(packet.data() + sizeof(em_raw_hdr_t));
    message->id = htons(1234);
    auto *info = reinterpret_cast<em_tlv_t *>(packet.data()
        + sizeof(em_raw_hdr_t) + sizeof(em_cmdu_t));
    info->type = em_tlv_type_client_info;
    info->len = htons(2 * sizeof(mac_address_t));
    const mac_address_t bssid = {2, 0, 0, 1, 2, 3};
    const mac_address_t station = {2, 0, 0, 4, 5, 6};
    std::memcpy(info->value, bssid, sizeof(bssid));
    std::memcpy(info->value + sizeof(bssid), station, sizeof(station));
    for (int prior_state : {0, 1, 2, 3, 4, 5, 6, 7, 999}) {
        for (int send_result : {-1, 100}) {
            em_capability_t capability;
            capability.state = prior_state;
            capability.result = send_result;
            capability.handle_client_cap_query(packet.data(), packet.size());
            assert(capability.state == prior_state);
            assert(capability.replies == 1 && capability.reply_id == 1234);
            assert(std::memcmp(capability.reply_sta, station, sizeof(station)) == 0);
            assert(std::memcmp(capability.reply_bss, bssid, sizeof(bssid)) == 0);
        }
    }
    em_capability_t malformed;
    malformed.state = 42;
    malformed.handle_client_cap_query(nullptr, 0);
    malformed.handle_client_cap_query(packet.data(), 1);
    valid_message = false;
    malformed.handle_client_cap_query(packet.data(), packet.size());
    valid_message = true;
    info->len = htons(1);
    malformed.handle_client_cap_query(packet.data(), packet.size());
    info->type = em_tlv_type_eom;
    malformed.handle_client_cap_query(packet.data(), packet.size());
    assert(malformed.state == 42 && malformed.replies == 0);
    std::cout << "PASS: capability queries preserve onboarding/operational state, "
        "reply identity, send-failure behavior and malformed-input guards\n";
}
'''
with tempfile.TemporaryDirectory(prefix="client-capability-state-") as temporary:
    directory = Path(temporary)
    implementation = directory / "handler.cpp"
    executable = directory / "handler-test"
    implementation.write_text(harness)
    subprocess.run(["g++", "-std=gnu++17", "-Wall", "-Wextra", "-Werror",
                    str(implementation), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
