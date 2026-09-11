#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile


source = Path(sys.argv[1]).read_text()
implementations = []
for name in ("create_assoc_sta_link_metrics_tlv", "create_assoc_ext_sta_link_metrics_tlv"):
    start = source.index("short em_metrics_t::" + name + "(")
    implementations.append(source[start:source.index("\n}\n", start) + 3])

program = r"""
#include <cassert>
#include <cstdint>
#include <cstring>
#include <arpa/inet.h>
using mac_address_t = unsigned char[6];
struct __attribute__((packed)) em_assoc_link_metrics_t {
    mac_address_t bssid;
    uint32_t time_delta_ms, est_mac_data_rate_dl, est_mac_data_rate_ul;
    uint8_t rcpi;
};
struct __attribute__((packed)) em_assoc_ext_link_metrics_t {
    mac_address_t bssid;
    uint32_t last_data_dl_rate, last_data_ul_rate, util_receive, util_transmit;
};
struct __attribute__((packed)) em_assoc_sta_link_metrics_t {
    mac_address_t sta_mac;
    uint8_t num_bssids;
    em_assoc_link_metrics_t assoc_link_metrics[2];
};
struct __attribute__((packed)) em_assoc_sta_ext_link_metrics_t {
    mac_address_t sta_mac;
    uint8_t num_bssids;
    em_assoc_ext_link_metrics_t assoc_ext_link_metrics[2];
};
struct sta_info_t {
    mac_address_t id, bssid;
    uint32_t delta_ms, est_dl_rate, est_ul_rate;
    uint8_t rcpi;
    uint32_t last_dl_rate, last_ul_rate, util_rx, util_tx;
};
struct dm_sta_t { sta_info_t m_sta_info; };
class em_metrics_t {
public:
    short create_assoc_sta_link_metrics_tlv(unsigned char *, mac_address_t, const dm_sta_t *);
    short create_assoc_ext_sta_link_metrics_tlv(unsigned char *, mac_address_t, const dm_sta_t *);
};
""" + "\n".join(implementations) + r"""
int main() {
    em_metrics_t metrics;
    dm_sta_t current{{{2,0,0,0,3,0}, {2,0,0,1,0,0}, 123, 100, 200, 82, 10, 20, 30, 40}};
    for (unsigned int band = 0; band < 3; band++) {
        current.m_sta_info.bssid[4] = band;
        unsigned char buffer[256] = {};
        auto length = metrics.create_assoc_sta_link_metrics_tlv(buffer, current.m_sta_info.id, &current);
        const auto *basic = reinterpret_cast<em_assoc_sta_link_metrics_t *>(buffer);
        assert(basic->num_bssids == 1);
        assert(static_cast<size_t>(length) == 7 + basic->num_bssids * sizeof(em_assoc_link_metrics_t));
        assert(memcmp(basic->assoc_link_metrics[0].bssid, current.m_sta_info.bssid, 6) == 0);
        assert(basic->assoc_link_metrics[0].rcpi == 82);
        assert(ntohl(basic->assoc_link_metrics[0].time_delta_ms) == 123);
        length = metrics.create_assoc_ext_sta_link_metrics_tlv(buffer, current.m_sta_info.id, &current);
        const auto *extended = reinterpret_cast<em_assoc_sta_ext_link_metrics_t *>(buffer);
        assert(extended->num_bssids == 1);
        assert(static_cast<size_t>(length) == 7 + extended->num_bssids * sizeof(em_assoc_ext_link_metrics_t));
        assert(memcmp(extended->assoc_ext_link_metrics[0].bssid, current.m_sta_info.bssid, 6) == 0);
        assert(ntohl(extended->assoc_ext_link_metrics[0].last_data_ul_rate) == 20);
        assert(metrics.create_assoc_sta_link_metrics_tlv(buffer, current.m_sta_info.id, nullptr) == 7);
        assert(buffer[6] == 0);
        assert(metrics.create_assoc_ext_sta_link_metrics_tlv(buffer, current.m_sta_info.id, nullptr) == 7);
        assert(buffer[6] == 0);
    }
}
"""
with tempfile.TemporaryDirectory(prefix="metrics-wire-test-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-x", "c++",
                    "-", "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
print("PASS: production STA metric TLV counts match exact serialized owners across bands")
