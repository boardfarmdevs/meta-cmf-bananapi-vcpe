"""Compile the native candidate query serializer with deterministic transport/time."""

from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile


root = Path(sys.argv[1])
source = (root / "src/em/metrics/em_metrics.cpp").read_text()
sender = re.search(r"int em_metrics_t::send_unassoc_sta_link_metrics_query_msg\(\).*?\n}", source, re.S).group()
header = (root / "inc/em_metrics.h").read_text()
clear = re.search(r"        void clear_unassoc_sta_query_msg_id\(\)\s*\{[^}]*\}", header, re.S).group()
orchestration = (root / "src/orch/em_orch_ctrl.cpp").read_text()
cancel_function = re.search(r"void em_orch_ctrl_t::pre_process_cancel\(.*?\n}", orchestration, re.S).group()
cancel = cancel_function.split("case em_cmd_type_unassoc_sta_query:", 1)[1].split("default:", 1)[0]
program = r'''
#include <arpa/inet.h>
#include <cassert>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <set>
#include <vector>
#include "em_unassoc_query_tracker.h"
static uint64_t clock_ms=10000;
namespace test_clock {
using std::chrono::duration_cast;
using std::chrono::milliseconds;
struct steady_clock {
    struct reading { std::chrono::milliseconds time_since_epoch() { return std::chrono::milliseconds(clock_ms); } };
    static reading now() { return {}; }
};
}
#define MAX_EM_BUFF_SZ 1024
#define EM_MAX_TLV_MEMBERS 16
#define ETH_P_1905 0x893a
#define em_msg_type_unassoc_sta_link_metrics_query 0x800d
#define em_tlv_type_unassoc_sta_link_metric_query 0x97
#define em_tlv_type_eom 0
#define em_profile_type_3 3
#define em_printfout(...) ((void)0)
enum { em_state_ctrl_configured, em_state_ctrl_unassoc_sta_link_metrics_pending, unrelated_state };
using mac_address_t = unsigned char[6];
struct em_cmdu_t { unsigned char version, reserved; unsigned short type,id; unsigned char fragment,last_frag_ind:1,relay_ind:1,other:6; } __attribute__((packed));
struct em_tlv_t { unsigned char type; unsigned short len; unsigned char value[0]; } __attribute__((packed));
struct Channel { unsigned char num_sta=1; };
struct OpClass { unsigned char num_channels=1; Channel channel_list[1]; };
struct em_unassoc_query_list_t { int num_opclass=1; OpClass opclass_list[1]; };
struct em_cmd_unassoc_sta_query_t { em_unassoc_query_list_t query; em_unassoc_query_list_t *get_query() { return &query; } };
struct dm_easy_mesh_t {
    unsigned char agent[6]{2,0,0,0,0,2}, controller[6]{2,0,0,0,0,1};
    unsigned char *get_agent_al_interface_mac() { return agent; }
    unsigned char *get_ctrl_al_interface_mac() { return controller; }
};
struct Manager { unsigned short next=77; unsigned short get_next_msg_id() { return next++; } };
struct em_msg_t {
    em_msg_t(int, int, unsigned char *, unsigned int) {}
    int validate(char **) { return 1; }
};
struct em_metrics_t {
    unsigned short m_unassoc_sta_query_msg_id=0;
    unsigned int m_unassoc_sta_query_transmits=0;
    uint64_t m_unassoc_sta_query_last_send_ms=0;
    dm_easy_mesh_t model;
    em_cmd_unassoc_sta_query_t command;
    Manager manager;
    std::vector<std::vector<unsigned char>> frames;
    bool fail=false;
    dm_easy_mesh_t *get_data_model() { return &model; }
    em_cmd_unassoc_sta_query_t *get_current_cmd() { return &command; }
    Manager *get_mgr() { return &manager; }
    unsigned short get_unassoc_sta_query_msg_id() { return m_unassoc_sta_query_msg_id; }
    int send_frame(unsigned char *data, unsigned int length) {
        frames.emplace_back(data,data+length); return fail ? -1 : length;
    }
    unsigned int create_unassoc_sta_link_metrics_query_tlv(unsigned char *data, OpClass *) {
        std::memset(data,0,10); data[0]=115; data[1]=1; data[2]=36; data[3]=1; data[4]=2; return 10;
    }
    CLEAR
    int send_unassoc_sta_link_metrics_query_msg();
};
struct em_t : em_metrics_t {
    int state = em_state_ctrl_unassoc_sta_link_metrics_pending;
    int get_state() { return state; }
    void set_state(int value) { state = value; }
};
SENDER
void cancel_query(em_t *em) { do { CANCEL } while (false); }
int main() {
    em_t radio;
    assert(radio.send_unassoc_sta_link_metrics_query_msg()>0);
    const auto first=radio.frames.front();
    assert(radio.m_unassoc_sta_query_msg_id==77 && radio.manager.next==78);
    for (int attempt=1; attempt<4; attempt++) {
        clock_ms+=1999; assert(radio.send_unassoc_sta_link_metrics_query_msg()==0);
        clock_ms++; assert(radio.send_unassoc_sta_link_metrics_query_msg()>0);
        assert(radio.frames.back()==first && radio.manager.next==78);
    }
    clock_ms+=2000; assert(radio.send_unassoc_sta_link_metrics_query_msg()==0);
    assert(radio.frames.size()==4);
    cancel_query(&radio);
    assert(radio.state==em_state_ctrl_configured && !radio.m_unassoc_sta_query_msg_id);
    assert(!radio.m_unassoc_sta_query_transmits && !radio.m_unassoc_sta_query_last_send_ms);
    assert(radio.send_unassoc_sta_link_metrics_query_msg()>0 && radio.m_unassoc_sta_query_msg_id==78);
    clock_ms-=1; assert(radio.send_unassoc_sta_link_metrics_query_msg()==0);
    radio.clear_unassoc_sta_query_msg_id(); radio.fail=true;
    clock_ms+=2001; assert(radio.send_unassoc_sta_link_metrics_query_msg()==-1);
    assert(!radio.m_unassoc_sta_query_msg_id);
    clock_ms+=1999; assert(radio.send_unassoc_sta_link_metrics_query_msg()==0);
    clock_ms++; assert(radio.send_unassoc_sta_link_metrics_query_msg()==-1);
    clock_ms+=2000; assert(radio.send_unassoc_sta_link_metrics_query_msg()==-1);
    clock_ms+=2000; assert(radio.send_unassoc_sta_link_metrics_query_msg()==-1);
    clock_ms+=2000; assert(radio.send_unassoc_sta_link_metrics_query_msg()==0);
    assert(radio.m_unassoc_sta_query_transmits==4 && !radio.m_unassoc_sta_query_msg_id);
    radio.state=em_state_ctrl_unassoc_sta_link_metrics_pending;
    cancel_query(&radio);
    assert(radio.state==em_state_ctrl_configured && !radio.m_unassoc_sta_query_transmits);
    radio.fail=false; clock_ms+=2000;
    assert(radio.send_unassoc_sta_link_metrics_query_msg()>0);
    radio.state=unrelated_state;
    cancel_query(&radio);
    assert(radio.state==unrelated_state && !radio.m_unassoc_sta_query_msg_id &&
           !radio.m_unassoc_sta_query_transmits && !radio.m_unassoc_sta_query_last_send_ms);
    em_unassoc_query_tracker agent;
    assert(agent.insert(77,{"sta"},10000));
    assert(agent.insert(77,{"sta"},12000));
    auto responses=agent.accept(77,{{"sta",80,12001}},12002);
    assert(responses.size()==1 && responses[0].metrics[0].observed==12001);
    assert(agent.accept(77,{{"sta",80,12001}},12003).empty());
    assert(agent.insert(77,{"sta"},14000));
    responses=agent.accept(77,{{"sta",80,12001}},14001);
    assert(responses.size()==1 && responses[0].metrics.empty());
}
'''.replace("CLEAR", clear).replace("CANCEL", cancel).replace("SENDER", sender.replace("std::chrono::", "test_clock::"))
with tempfile.TemporaryDirectory(prefix="unassoc-retry-") as temporary:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    binary = Path(temporary) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-sign-compare", "-pthread", "-I", str(root / "inc"), "-x", "c++", "-", "-o", str(binary)], input=program, text=True, check=True)
    subprocess.run([str(binary)], check=True, timeout=10)
print("PASS: identical native retransmissions, bounded count/interval, reset, send failure, native callback age and duplicate correlation")
