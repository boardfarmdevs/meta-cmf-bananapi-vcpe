#!/usr/bin/env python3
"""0268: an agent's Operating Channel Report handled before its Channel Selection Response.

Takes the fully patched unified-wifi-mesh source tree. Each radio's em sends its own Channel
Selection Request (its radio only), and the controller hands each received message to the em of
the first radio it names, each em on its own thread. An agent that reports every radio in its
Operating Channel Report, the fronthaul first, has radio B's response go to radio B's em and its
report to radio A's. Handled first on radio A's thread, the report found radio B still
channel_select_pending and changed nothing; the response then left radio B in channel_selected,
with no report to come, until em_config's time limit renewed the agent (a pod's second radio,
three rounds after a boot, 13 October). Extracts the three handlers and checks, with
AddressSanitizer: the report while the request is pending completes the radio, in either order;
a radio in another state is untouched; a late response leaves a completed radio configured. Then
the two handlers on two threads at once, many times, under ThreadSanitizer: the radio always ends
configured. --expect-stuck reproduces the defect on a source without 0268.
"""
import argparse
from pathlib import Path
import platform
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("source_root", type=Path)
parser.add_argument("--expect-stuck", action="store_true")
args = parser.parse_args()
source = (args.source_root / "src/em/channel/em_channel.cpp").read_text()


def function(signature):
    return re.search(re.escape(signature) + r"\(.*?\n\}", source, re.S).group()


handlers = "\n".join(
    function(signature)
    for signature in (
        "int em_channel_t::handle_channel_sel_rsp",
        "int em_channel_t::handle_operating_channel_rprt",
        "int em_channel_t::handle_op_channel_report",
    )
)
fixed = "before its Channel Selection Response" in handlers
assert fixed != args.expect_stuck, "this source has 0268" if args.expect_stuck else "this source lacks 0268"
constants = sorted(
    set(re.findall(r"\b(?:em_state_ctrl_\w+|em_op_class_type_\w+|db_cfg_type_\w+)", handlers))
    | {"em_state_ctrl_channel_query_pending"}
)

program = r'''
#include <arpa/inet.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
#define EM_CONF 0
#define ACK_FROM_CTRL 1
#define EM_MAX_OPCLASS 64
#define em_printfout(...) ((void)0)
#define em_util_dbg_print(...) ((void)0)
enum { CONSTANTS };
enum { em_tlv_type_eom = 0x00, em_tlv_type_channel_sel_resp = 0x8e, em_tlv_type_op_channel_report = 0x8f };
typedef unsigned char mac_address_t[6];
typedef char mac_addr_str_t[18];
std::recursive_mutex g_network_topology_mutex;
typedef struct { mac_address_t dst, src; unsigned short type; } __attribute__((__packed__)) em_raw_hdr_t;
typedef struct { unsigned char type; unsigned short len; unsigned char value[0]; } __attribute__((__packed__)) em_tlv_t;
typedef struct {
    unsigned char ver, reserved;
    unsigned short type, id;
    unsigned char frag_id;
    unsigned char reserved_field:6, relay_ind:1, last_frag_ind:1;
} __attribute__((__packed__)) em_cmdu_t;
typedef struct { mac_address_t ruid; unsigned char response_code; } __attribute__((__packed__)) em_channel_sel_rsp_t;
typedef struct { unsigned char op_class, channel; } __attribute__((__packed__)) em_op_class_ch_rprt_t;
typedef struct {
    mac_address_t ruid;
    unsigned char op_classes_num;
    em_op_class_ch_rprt_t op_classes[0];
} __attribute__((__packed__)) em_op_channel_rprt_t;
struct em_op_class_id_t { mac_address_t ruid; int type; unsigned int op_class; };
struct em_op_class_info_t { em_op_class_id_t id; unsigned int op_class, channel; };
struct dm_op_class_t { em_op_class_info_t m_op_class_info; };
struct dm_easy_mesh_t {
    unsigned int m_num_opclass = 0;
    dm_op_class_t m_op_class[EM_MAX_OPCLASS] = {};
    unsigned int get_num_op_class() { return m_num_opclass; }
    void set_num_op_class(unsigned int n) { m_num_opclass = n; }
    void set_db_cfg_param(int, const char *) {}
    static void macbytes_to_string(const unsigned char *m, char *s) {
        snprintf(s, 18, "%02x:%02x:%02x:%02x:%02x:%02x", m[0], m[1], m[2], m[3], m[4], m[5]);
    }
};
typedef std::map<std::string, void *> hash_map_t;
void *hash_map_get(hash_map_t *map, const char *key) {
    auto found = map->find(key);
    return found == map->end() ? nullptr : found->second;
}
struct em_mgr_t { hash_map_t map; hash_map_t *m_em_map = &map; };
struct em_channel_t {
    unsigned short m_chan_req_msg_id = 0;
    int state = 0;
    em_mgr_t *mgr = nullptr;
    dm_easy_mesh_t *dm = nullptr;
    std::vector<unsigned short> acks;
    em_mgr_t *get_mgr() { return mgr; }
    dm_easy_mesh_t *get_data_model() { return dm; }
    int get_state() { return state; }
    void set_state(int value) { state = value; }
    int send_1905_ack_message(unsigned short id, int) { acks.push_back(id); return 0; }
    int handle_channel_sel_rsp(unsigned char *buff, unsigned int len);
    int handle_operating_channel_rprt(unsigned char *buff, unsigned int len);
    int handle_op_channel_report(unsigned char *buff, unsigned int len);
};
struct em_t : em_channel_t {};
HANDLERS

static const unsigned char RADIO_A[6] = {0x90, 0xde, 0x80, 0x47, 0xb8, 0x52};
static const unsigned char RADIO_B[6] = {0x90, 0xde, 0x80, 0x47, 0xf6, 0x22};
struct radio_report { const unsigned char *ruid; unsigned char op_class, channel; };
/* a 1905 frame: the raw header, the CMDU and its TLVs, End of Message */
static std::vector<unsigned char> frame(unsigned short type, unsigned short mid,
                                        const std::vector<std::pair<unsigned char, std::vector<unsigned char>>> &tlvs) {
    std::vector<unsigned char> out(sizeof(em_raw_hdr_t) + sizeof(em_cmdu_t), 0);
    em_cmdu_t *cmdu = reinterpret_cast<em_cmdu_t *>(out.data() + sizeof(em_raw_hdr_t));
    cmdu->type = htons(type);
    cmdu->id = htons(mid);
    cmdu->last_frag_ind = 1;
    for (const auto &t : tlvs) {
        out.push_back(t.first);
        out.push_back(static_cast<unsigned char>(t.second.size() >> 8));
        out.push_back(static_cast<unsigned char>(t.second.size() & 0xff));
        out.insert(out.end(), t.second.begin(), t.second.end());
    }
    out.insert(out.end(), {0, 0, 0});
    return out;
}
/* the agent's answer to radio B's request: its response, radio B declined (0x02) */
static std::vector<unsigned char> response(unsigned short mid) {
    std::vector<unsigned char> value(RADIO_B, RADIO_B + 6);
    value.push_back(0x02);
    return frame(0x8007, mid, {{0x8e, value}});
}
/* then its report: every radio, the fronthaul first */
static std::vector<unsigned char> report(unsigned short mid) {
    std::vector<std::pair<unsigned char, std::vector<unsigned char>>> tlvs;
    for (radio_report r : {radio_report{RADIO_A, 81, 6}, radio_report{RADIO_B, 125, 149}}) {
        std::vector<unsigned char> value(r.ruid, r.ruid + 6);
        value.insert(value.end(), {1, r.op_class, r.channel, 30});
        tlvs.push_back({0x8f, value});
    }
    return frame(0x8008, mid, tlvs);
}
struct pod {
    em_mgr_t mgr;
    dm_easy_mesh_t dm;
    em_t a, b;
    pod(int a_state, int b_state, unsigned short b_mid = 0x0151) {
        for (em_t *em : {&a, &b}) { em->mgr = &mgr; em->dm = &dm; }
        mgr.map["90:de:80:47:b8:52"] = &a;
        mgr.map["90:de:80:47:f6:22"] = &b;
        a.state = a_state;
        b.state = b_state;
        b.m_chan_req_msg_id = b_mid;
    }
    /* each message to the em of the first radio it names, as the controller hands it */
    void to_a(std::vector<unsigned char> m) { a.handle_operating_channel_rprt(m.data(), static_cast<unsigned int>(m.size())); }
    void to_b(std::vector<unsigned char> m) { b.handle_channel_sel_rsp(m.data(), static_cast<unsigned int>(m.size())); }
    bool reported_b() {
        for (unsigned int i = 0; i < dm.m_num_opclass; i++) {
            const em_op_class_info_t &o = dm.m_op_class[i].m_op_class_info;
            if (!memcmp(o.id.ruid, RADIO_B, 6) && o.op_class == 125 && o.channel == 149) return true;
        }
        return false;
    }
};
int main(int argc, char **argv) {
    const bool expect_stuck = argc > 1 && std::string(argv[1]) == "--expect-stuck";
    const bool threads = argc > 1 && std::string(argv[1]) == "--threads";
    if (threads) {
        /* the two ems' threads at once: radio A's em with the report, radio B's with the response */
        for (int round = 0; round < 2000; round++) {
            pod p(em_state_ctrl_configured, em_state_ctrl_channel_select_pending);
            std::thread a([&] { p.to_a(report(0x0300)); });
            std::thread b([&] { p.to_b(response(0x0151)); });
            a.join();
            b.join();
            assert(p.b.get_state() == em_state_ctrl_configured);
        }
        std::puts("2000 concurrent rounds: radio B configured every time");
        return 0;
    }
    /* the good order: the response, then the report */
    {
        pod p(em_state_ctrl_configured, em_state_ctrl_channel_select_pending);
        p.to_b(response(0x0151));
        assert(p.b.get_state() == em_state_ctrl_channel_selected);
        p.to_a(report(0x0300));
        assert(p.b.get_state() == em_state_ctrl_configured && p.reported_b() && p.a.acks.size() == 1);
    }
    /* the race: the report on radio A's thread first, then radio B's response */
    pod p(em_state_ctrl_configured, em_state_ctrl_channel_select_pending);
    p.to_a(report(0x0300));
    p.to_b(response(0x0151));
    assert(p.reported_b());  /* the model has radio B's channel either way */
    if (expect_stuck) {
        assert(p.b.get_state() == em_state_ctrl_channel_selected);
        std::puts("REPRODUCED: the report handled first, radio B left in channel_selected with no report to come");
        return 0;
    }
    assert(p.b.get_state() == em_state_ctrl_configured && p.b.m_chan_req_msg_id == 0);
    /* a radio in another state is untouched by a report */
    {
        pod q(em_state_ctrl_configured, em_state_ctrl_channel_query_pending);
        q.to_a(report(0x0301));
        assert(q.b.get_state() == em_state_ctrl_channel_query_pending);
    }
    /* a response for an older request while pending selects nothing; the report completes it */
    {
        pod q(em_state_ctrl_configured, em_state_ctrl_channel_select_pending, 0x0152);
        q.to_b(response(0x0151));
        assert(q.b.get_state() == em_state_ctrl_channel_select_pending);
        q.to_a(report(0x0302));
        assert(q.b.get_state() == em_state_ctrl_configured);
        q.to_b(response(0x0152));  /* the current request's response, late */
        assert(q.b.get_state() == em_state_ctrl_configured);
    }
    std::puts("PASS: a report while the request is pending completes the radio, in either order");
    return 0;
}
'''.replace("CONSTANTS", ", ".join(constants)).replace("HANDLERS", handlers)


def build_and_run(directory, name, sanitizers, *arguments):
    src, exe = Path(directory) / f"{name}.cpp", Path(directory) / name
    src.write_text(program)
    # upstream's handle_op_channel_report leaves its len unused
    subprocess.run(["g++", "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                    "-pthread", *sanitizers, "-fno-sanitize-recover=all", "-o", str(exe), str(src)], check=True)
    # ThreadSanitizer needs a fixed address layout on kernels with wide mmap randomization
    prefix = ["setarch", platform.machine(), "-R"] if "-fsanitize=thread" in sanitizers else []
    subprocess.run([*prefix, str(exe), *arguments], check=True)


with tempfile.TemporaryDirectory(prefix="channel-report-") as directory:
    asan = ["-fsanitize=address,undefined"]
    if args.expect_stuck:
        build_and_run(directory, "stuck", asan, "--expect-stuck")
        raise SystemExit(0)
    build_and_run(directory, "orders", asan)
    build_and_run(directory, "threads", ["-fsanitize=thread"], "--threads")
print("controller Operating Channel Report before the Channel Selection Response: ok")
