from pathlib import Path
import argparse
import re
import subprocess
import tempfile


parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path)
parser.add_argument("--case")
arguments = parser.parse_args()
source = (arguments.source / "src/em/config/em_configuration.cpp").read_text()
implementation = re.search(
    r"(?:int|void) em_configuration_t::handle_ap_vendor_operational_bss\([^\n]*\)\n\{.*?\n\}",
    source, re.S,
).group()
legacy = implementation.startswith("void ")
if not legacy:
    assert "if (handle_ap_vendor_operational_bss(tlv->value, ntohs(tlv->len)) != 0)" in source
    header = (arguments.source / "inc/em_configuration.h").read_text()
    assert "int handle_ap_vendor_operational_bss(unsigned char *value, unsigned int len);" in header

program = r'''
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <set>
#include <string>
#include <vector>
using mac_address_t = unsigned char[6];
using mac_addr_str_t = char[18];
using em_long_string_t = char[64];
enum em_haul_type_t { em_haul_type_fronthaul, em_haul_type_backhaul };
enum em_vap_mode_t { em_vap_mode_ap, em_vap_mode_sta };
constexpr unsigned int EM_MAX_BSSS = 16;
struct __attribute__((packed)) em_ap_vendor_operational_bss_t {
    mac_address_t bssid;
    unsigned short haultype;
    unsigned short vap_mode;
};
struct __attribute__((packed)) em_ap_vendor_op_bss_radio_t {
    mac_address_t ruid;
    unsigned char bss_num;
    em_ap_vendor_operational_bss_t bss[0];
};
struct __attribute__((packed)) em_ap_vendor_op_bss_t {
    unsigned char radios_num;
    em_ap_vendor_op_bss_radio_t radios[0];
};
struct address_t { mac_address_t mac; };
struct em_bss_info_t {
    struct {
        em_long_string_t net_id;
        mac_address_t dev_mac, ruid, bssid;
        em_haul_type_t haul_type;
    } id;
    address_t ruid, bssid;
    em_vap_mode_t vap_mode;
    bool enabled;
    unsigned int marker;
};
struct dm_bss_t {
    em_bss_info_t m_bss_info;
    void init() { memset(&m_bss_info, 0, sizeof(m_bss_info)); }
};
struct dm_easy_mesh_t {
    dm_bss_t m_bss[EM_MAX_BSSS]{};
    unsigned int m_num_bss = 0;
    struct {
        struct {
            struct { em_long_string_t net_id; } id;
            address_t intf;
        } m_device_info;
    } m_device{};
    void set_num_bss(unsigned int count) { assert(count <= EM_MAX_BSSS); m_num_bss = count; }
    unsigned int get_num_bss() { return m_num_bss; }
    dm_bss_t *get_bss(const unsigned char *radio, const unsigned char *bssid) {
        for (unsigned int index = 0; index < m_num_bss; ++index) {
            auto &info = m_bss[index].m_bss_info;
            if (!memcmp(info.ruid.mac, radio, 6) && !memcmp(info.bssid.mac, bssid, 6)) return &m_bss[index];
        }
        return nullptr;
    }
    static void macbytes_to_string(const unsigned char *, char *value) { value[0] = 0; }
};
struct em_configuration_t {
    dm_easy_mesh_t model;
    dm_easy_mesh_t *get_data_model() { return &model; }
    RETURN_TYPE handle_ap_vendor_operational_bss(unsigned char *, unsigned int);
    int apply(std::vector<unsigned char> &packet) { APPLY }
};
IMPLEMENTATION
void append_mac(std::vector<unsigned char> &packet, unsigned char identity) {
    packet.insert(packet.end(), {2, 0, 0, 0, 0, identity});
}
std::vector<unsigned char> report(unsigned char parent = 12) {
    std::vector<unsigned char> packet{1};
    append_mac(packet, 1);
    packet.push_back(1);
    append_mac(packet, parent);
    const unsigned short fields[]{em_haul_type_backhaul, em_vap_mode_sta};
    const auto *bytes = reinterpret_cast<const unsigned char *>(fields);
    packet.insert(packet.end(), bytes, bytes + sizeof(fields));
    return packet;
}
void add(dm_easy_mesh_t &model, unsigned char radio, unsigned char bssid,
         em_vap_mode_t mode = em_vap_mode_sta, em_haul_type_t haul = em_haul_type_backhaul,
         bool enabled = true) {
    assert(model.m_num_bss < EM_MAX_BSSS);
    auto &info = model.m_bss[model.m_num_bss++].m_bss_info;
    info.ruid.mac[0] = info.bssid.mac[0] = 2;
    info.ruid.mac[5] = radio;
    info.bssid.mac[5] = bssid;
    info.vap_mode = mode;
    info.id.haul_type = haul;
    info.enabled = enabled;
    info.marker = 123456;
}
unsigned int count(const dm_easy_mesh_t &model, unsigned char radio, unsigned char parent) {
    unsigned int found = 0;
    for (unsigned int index = 0; index < model.m_num_bss; ++index) {
        const auto &info = model.m_bss[index].m_bss_info;
        if (info.ruid.mac[5] == radio && info.bssid.mac[5] == parent) ++found;
    }
    return found;
}
int main(int argc, char **argv) {
    assert(argc == 2);
    const std::string scenario = argv[1];
    em_configuration_t controller;
    auto &model = controller.model;
    strcpy(model.m_device.m_device_info.id.net_id, "native-network");
    model.m_device.m_device_info.intf.mac[0] = 2;
    model.m_device.m_device_info.intf.mac[5] = 90;
    add(model, 1, 11);
    auto packet = report();
    if (scenario == "replace" || scenario == "return" || scenario == "disabled" ||
            scenario == "duplicates" || scenario == "capacity-replace") {
        if (scenario == "disabled") model.m_bss[0].m_bss_info.enabled = false;
        if (scenario == "duplicates") add(model, 1, 13);
        if (scenario == "capacity-replace") {
            while (model.m_num_bss < EM_MAX_BSSS) add(model, 2, 30 + model.m_num_bss, em_vap_mode_ap);
        }
        assert(controller.apply(packet) == 0);
        assert(count(model, 1, 11) == 0 && count(model, 1, 12) == 1 && count(model, 1, 13) == 0);
        if (scenario == "return") {
            packet = report(11);
            assert(controller.apply(packet) == 0);
            assert(count(model, 1, 11) == 1 && count(model, 1, 12) == 0);
        }
    } else if (scenario == "scope") {
        add(model, 2, 11);
        add(model, 1, 20, em_vap_mode_ap);
        add(model, 1, 21, em_vap_mode_sta, em_haul_type_fronthaul);
        assert(controller.apply(packet) == 0);
        assert(model.m_num_bss == 4 && count(model, 1, 11) == 0);
        assert(count(model, 2, 11) == 1 && count(model, 1, 20) == 1 && count(model, 1, 21) == 1);
        assert(model.m_bss[0].m_bss_info.marker == 123456);
    } else if (scenario == "repeat") {
        packet = report(11);
        for (unsigned int repeat = 0; repeat < 20; ++repeat) assert(controller.apply(packet) == 0);
        assert(model.m_num_bss == 1 && model.m_bss[0].m_bss_info.enabled);
        assert(model.m_bss[0].m_bss_info.marker == 123456);
        assert(model.m_bss[0].m_bss_info.id.dev_mac[5] == 90);
        assert(!strcmp(model.m_bss[0].m_bss_info.id.net_id, "native-network"));
    } else if (scenario == "empty" || scenario == "ap-only") {
        if (scenario == "empty") packet = {0};
        else {
            packet[16] = em_vap_mode_ap;
            packet[17] = 0;
        }
        assert(controller.apply(packet) == 0);
        assert(count(model, 1, 11) == 1);
    } else {
        if (scenario == "truncated-header") packet.clear();
        else if (scenario == "truncated-radio") packet.resize(7);
        else if (scenario == "truncated-bss") packet.pop_back();
        else if (scenario == "trailing") packet.push_back(0);
        else if (scenario == "late-truncation") packet[0] = 2;
        else if (scenario == "duplicate-radio") {
            auto repeated = packet;
            packet[0] = 2;
            packet.insert(packet.end(), repeated.begin() + 1, repeated.end());
        } else if (scenario == "ambiguous-parent" || scenario == "duplicate-bssid") {
            auto repeated = report(scenario == "ambiguous-parent" ? 13 : 12);
            packet[7] = 2;
            packet.insert(packet.end(), repeated.begin() + 8, repeated.end());
        } else if (scenario == "capacity-overflow") {
            while (model.m_num_bss < EM_MAX_BSSS) add(model, 2, 30 + model.m_num_bss, em_vap_mode_ap);
            packet[16] = em_vap_mode_ap;
            packet[17] = 0;
        } else assert(false);
        const auto original = model;
        assert(controller.apply(packet) == -1);
        assert(!memcmp(&original, &model, sizeof(model)));
    }
    printf("PASS: %s\n", scenario.c_str());
}
'''
program = program.replace("RETURN_TYPE", "void" if legacy else "int")
program = program.replace("APPLY", (
    "handle_ap_vendor_operational_bss(packet.data(), packet.size()); return 0;"
    if legacy else "return handle_ap_vendor_operational_bss(packet.data(), packet.size());"
))
program = program.replace("IMPLEMENTATION", implementation)
cases = [
    "replace", "return", "disabled", "duplicates", "capacity-replace", "scope",
    "repeat", "empty", "ap-only", "truncated-header", "truncated-radio",
    "truncated-bss", "trailing", "late-truncation", "duplicate-radio",
    "ambiguous-parent", "duplicate-bssid", "capacity-overflow",
]
if arguments.case:
    assert arguments.case in cases
    cases = [arguments.case]
with tempfile.TemporaryDirectory(prefix="native-backhaul-topology-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                    "-x", "c++", "-", "-o", str(executable)], input=program, text=True, check=True)
    results = [subprocess.run([str(executable), scenario]).returncode for scenario in cases]
assert not any(results), results
print(f"PASS: {len(cases)} production native backhaul topology reconciliation cases")
