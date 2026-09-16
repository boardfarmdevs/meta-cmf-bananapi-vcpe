from pathlib import Path
import subprocess
import sys
import tempfile


root = Path(sys.argv[1])
source = (root / "src/ctrl/em_backhaul_ctrl.cpp").read_text()
handler = source[source.index("bool em_ctrl_t::handle_native_backhaul_frame"):]
refresh = source[source.index("void em_ctrl_t::collect_native_backhaul_refresh"):source.index("void em_ctrl_t::handle_native_backhaul_tick")]
header = (root / "inc/em_ctrl.h").read_text()
state = header[header.index("    struct backhaul_query_t"):header.index("    void handle_native_backhaul_tick();")]
serving_marker = source.index("backhaul_query_t serving_query")
query_start = source.rfind("            for (const auto &entry : network.aps)", 0, serving_marker)
query_end = source.index("            for (const auto &entry : network.aps)", serving_marker)
ap_queries = source[query_start:query_end]
program = r'''
#include "em_backhaul_policy.h"
#include "em_backhaul_wire.h"
#include <cassert>
#include <chrono>
#include <mutex>
#include <iostream>
#define em_printfout(...) (void)0
struct em_t {};
struct __attribute__((packed)) em_assoc_link_metrics_t { unsigned char bytes[19]; };
struct __attribute__((packed)) em_unassoc_sta_metric_t { unsigned char bytes[12]; };
struct __attribute__((packed)) em_bh_steering_resp_t { unsigned char bytes[13]; };
enum {
    em_msg_type_topo_query = 0x0002,
    em_tlv_type_profile = 0xb3,
    em_profile_type_3 = 3,
    em_msg_type_1905_ack = 0x8000,
    em_msg_type_ap_metrics_query = 0x800b,
    em_msg_type_ap_metrics_rsp = 0x800c,
    em_msg_type_assoc_sta_link_metrics_rsp = 0x800e,
    em_msg_type_unassoc_sta_link_metrics_rsp = 0x8010,
    em_msg_type_bh_steering_rsp = 0x801a,
    em_tlv_type_assoc_sta_link_metric = 0x96,
    em_tlv_type_ap_metrics_query = 0x93,
    em_tlv_type_unassoc_sta_link_metric_rsp = 0x98,
    em_tlv_type_bh_steering_rsp = 0x9f
};
int64_t backhaul_now() { return 12000; }
std::string backhaul_mac(const unsigned char *bytes) {
    return std::string(reinterpret_cast<const char *>(bytes), 6);
}
class em_ctrl_t {
public:
STATE
    unsigned short next_mid = 1000;
    unsigned short get_next_msg_id() { return ++next_mid; }
    void collect_ap_queries(std::vector<std::vector<unsigned char>> &outgoing) {
        const auto &network = m_backhaul_network;
        const auto &controller = m_backhaul_controller;
        const int64_t now = backhaul_now();
AP_QUERIES
    }
    bool handle_native_backhaul_frame(unsigned char *data, unsigned int len, em_t *al_em);
    void collect_native_backhaul_refresh(const em_backhaul::snapshot &network, int64_t now,
        std::vector<std::vector<unsigned char>> &outgoing);
};
REFRESH
HANDLER
int main() {
    em_ctrl_t controller;
    const std::string control("\x02\x00\x00\x00\x00\x01", 6);
    const std::string parent("\x02\x00\x00\x00\x00\x02", 6);
    const std::string child("\x02\x00\x00\x00\x00\x03", 6);
    const std::string target("\x02\x00\x00\x00\x00\x04", 6);
    const std::string station("\x02\x00\x00\x00\x01\x03", 6);
    const std::string bssid("\x02\x00\x00\x00\x02\x02", 6);
    const std::string target_bssid("\x02\x00\x00\x00\x02\x04", 6);
    controller.m_backhaul_controller = control;
    auto &network = controller.m_backhaul_network;
    network.root = parent;
    network.nodes[child] = {child, station, bssid, {}};
    network.aps[bssid] = {parent, bssid, 115, 36};
    network.aps[target_bssid] = {target, target_bssid, 115, 36};
    auto restore_query = [&]() {
        controller.m_backhaul_queries[77] = {false, network.aps[target_bssid], {{station, bssid}}, 11000, 7};
    };
    auto send = [&](std::vector<unsigned char> packet) {
        return controller.handle_native_backhaul_frame(packet.data(), packet.size(), nullptr);
    };
    std::vector<unsigned char> associated(station.begin(), station.end());
    associated.push_back(1);
    associated.insert(associated.end(), bssid.begin(), bssid.end());
    associated.insert(associated.end(), 12, 0);
    associated.push_back(62);
    auto packet = em_backhaul::frame(control, parent, 0x800e, 1, 0x96, associated);
    assert(!send(packet));
    assert(network.nodes[child].serving.rcpi == -1);
    packet = em_backhaul::frame(control, parent, 0x800c, 1, 0x96, associated);
    assert(!send(packet));
    assert(network.nodes[child].serving.rcpi == -1);
    controller.m_backhaul_queries[1] = {true, network.aps[bssid], {{station, bssid}}, 11000, 1};
    assert(!send(packet));
    assert(network.nodes[child].serving.rcpi == 62);
    assert(network.nodes[child].serving.observed == 11000);
    const auto original_parent = network.aps[bssid];
    network.nodes[child].serving = {};
    controller.m_backhaul_queries[1] = {true, original_parent, {{station, bssid}}, 11000, 1};
    network.aps[bssid].channel = 40;
    assert(!send(packet));
    assert(network.nodes[child].serving.rcpi == -1);
    network.aps[bssid] = original_parent;
    controller.m_backhaul_queries[1] = {true, original_parent, {{station, bssid}}, 11000, 1};
    assert(!send(packet));
    assert(network.nodes[child].serving.rcpi == 62);
    controller.m_backhaul_queries[77] = {false, network.aps[target_bssid], {{station, bssid}}, 11000, 7};
    std::vector<unsigned char> candidate{115, 1};
    candidate.insert(candidate.end(), station.begin(), station.end());
    candidate.insert(candidate.end(), {36, 0, 0, 0, 0, 92});
    packet = em_backhaul::frame(control, target, 0x8010, 77, 0x98, candidate);
    assert(send(packet));
    assert(network.candidates.at({station, target_bssid}).rcpi == 92);
    assert(network.candidates.at({station, target_bssid}).round == 7);
    assert(controller.m_backhaul_queries.count(77) == 0);
    assert(!send(packet));
    assert(network.candidates.at({station, target_bssid}).observed == 12000);
    network.candidates.clear();
    const auto original_target = network.aps[target_bssid];
    for (unsigned int variant = 0; variant < 3; ++variant) {
        network.aps[target_bssid] = original_target;
        restore_query();
        if (variant == 0) network.aps[target_bssid].channel = 40;
        if (variant == 1) network.aps[target_bssid].op_class = 81;
        if (variant == 2) network.aps[target_bssid].al = child;
        assert(send(packet));
        assert(network.candidates.empty());
    }
    network.aps[target_bssid] = original_target;
    auto changed = packet;
    changed[19] = 78;
    assert(!send(changed) && network.candidates.empty());
    changed = packet;
    changed[11] = 9;
    assert(!send(changed) && network.candidates.empty());
    changed = packet;
    changed[5] = 9;
    assert(!send(changed) && network.candidates.empty());
    changed = packet;
    changed[25] = 81;
    restore_query();
    assert(send(changed) && network.candidates.empty());
    changed = packet;
    changed[32] = 9;
    restore_query();
    assert(send(changed) && network.candidates.empty());
    changed = packet;
    changed[33] = 40;
    restore_query();
    assert(send(changed) && network.candidates.empty());
    changed = packet;
    changed[36] = 0x27;
    changed[37] = 0x10;
    restore_query();
    assert(send(changed) && network.candidates.empty());
    changed = packet;
    changed[38] = 255;
    restore_query();
    assert(send(changed) && network.candidates.empty());
    changed = packet;
    changed[26] = 2;
    restore_query();
    assert(send(changed) && network.candidates.empty());
    changed = packet;
    changed.resize(changed.size() - 1);
    restore_query();
    assert(send(changed) && network.candidates.empty());
    restore_query();
    controller.m_backhaul_queries[77].sent = 1000;
    assert(send(packet) && network.candidates.empty());
    restore_query();
    network.nodes[child].parent_bssid = target_bssid;
    assert(send(packet) && network.candidates.empty());
    network.nodes[child].parent_bssid = bssid;
    restore_query();
    assert(send(em_backhaul::frame(control, target, 0x8000, 77, 0, {})));
    assert(!send(em_backhaul::frame(control, target, 0x8000, 78, 0, {})));
    controller.m_backhaul_steer = {{child, station, bssid, target_bssid, 62, 92, 66}, 80, 11000, false};
    std::vector<unsigned char> reply(station.begin(), station.end());
    reply.insert(reply.end(), target_bssid.begin(), target_bssid.end());
    reply.push_back(0);
    assert(send(em_backhaul::frame(control, child, 0x801a, 80, 0x9f, reply)));
    assert(controller.m_backhaul_steer.response);
    assert(network.nodes[child].parent_bssid == bssid);
    std::vector<std::vector<unsigned char>> refreshes;
    controller.m_backhaul_last_query = 11900;
    controller.collect_native_backhaul_refresh(network, 12000, refreshes);
    assert(refreshes.size() == 1);
    const auto &refresh = refreshes.front();
    assert(backhaul_mac(refresh.data()) == child);
    assert(backhaul_mac(refresh.data() + 6) == control);
    assert(em_backhaul::read16(refresh.data() + 16) == em_msg_type_topo_query);
    assert(refresh[22] == em_tlv_type_profile && refresh[25] == em_profile_type_3);
    assert(network.nodes[child].parent_bssid == bssid);
    assert(controller.m_backhaul_last_query == 11900);
    assert(!controller.m_backhaul_steer.parent_observed);
    assert(send(em_backhaul::frame(control, child, 0x801a, 80, 0x9f, reply)));
    controller.collect_native_backhaul_refresh(network, 13999, refreshes);
    assert(refreshes.size() == 1);
    controller.collect_native_backhaul_refresh(network, 14000, refreshes);
    controller.collect_native_backhaul_refresh(network, 16000, refreshes);
    controller.collect_native_backhaul_refresh(network, 18000, refreshes);
    assert(refreshes.size() == 3);
    network.nodes[child].parent_bssid = target_bssid;
    controller.collect_native_backhaul_refresh(network, 18001, refreshes);
    assert(controller.m_backhaul_steer.parent_observed);
    assert(controller.m_backhaul_last_query == 0);
    assert(network.nodes[child].serving.observed == 11000);
    controller.m_backhaul_last_query = 18001;
    controller.collect_native_backhaul_refresh(network, 18002, refreshes);
    assert(controller.m_backhaul_last_query == 18001);
    assert(refreshes.size() == 3);
    network.nodes[child].parent_bssid = bssid;
    reply.back() = 1;
    assert(send(em_backhaul::frame(control, child, 0x801a, 80, 0x9f, reply)));
    assert(controller.m_backhaul_steer.mid == 0);
    assert(controller.m_backhaul_uncertain.at(child).failures == 1);
    assert(controller.m_backhaul_uncertain.at(child).request.target == target_bssid);
    controller.collect_native_backhaul_refresh(network, 18003, refreshes);
    assert(refreshes.size() == 3);
    for (unsigned int variant = 0; variant < 4; ++variant) {
        controller.m_backhaul_steer = {{child, station, bssid, target_bssid, 62, 92, 66}, 80, 11000, true};
        if (variant == 0) controller.m_backhaul_steer.response = false;
        if (variant == 1) controller.m_backhaul_steer.mid = 0;
        if (variant == 2) controller.m_backhaul_steer.sent = -3000;
        if (variant == 3) controller.m_backhaul_steer.request.sta = parent;
        controller.collect_native_backhaul_refresh(network, 12000, refreshes);
        assert(refreshes.size() == 3);
    }
    em_ctrl_t poller;
    poller.m_backhaul_controller = control;
    poller.m_backhaul_network = network;
    const std::string leaf_bssid("\x02\x00\x00\x00\x00\x77", 6);
    poller.m_backhaul_network.aps[leaf_bssid] = {child, leaf_bssid, 115, 36};
    std::vector<std::vector<unsigned char>> polls;
    poller.collect_ap_queries(polls);
    assert(polls.size() == poller.m_backhaul_network.aps.size());
    bool leaf_queried = false;
    for (const auto &packet : polls) {
        const auto mid = em_backhaul::read16(packet.data() + 18);
        const auto &query = poller.m_backhaul_queries.at(mid);
        assert(query.associated && query.sent == backhaul_now());
        assert(em_backhaul::read16(packet.data() + 16) == em_msg_type_ap_metrics_query);
        assert(packet[22] == em_tlv_type_ap_metrics_query && packet[25] == 1);
        assert(backhaul_mac(packet.data() + 26) == query.ap.bssid);
        if (query.ap.bssid == leaf_bssid) {
            leaf_queried = true;
            assert(query.stations.empty());
            const auto previous = poller.m_backhaul_network.nodes.at(child).serving.observed;
            auto empty = em_backhaul::frame(control, child, 0x800c, mid, 0x94, {});
            poller.handle_native_backhaul_frame(empty.data(), empty.size(), nullptr);
            assert(poller.m_backhaul_queries.count(mid) == 0);
            assert(poller.m_backhaul_network.nodes.at(child).serving.observed == previous);
        }
    }
    assert(leaf_queried);
    std::cout << "PASS: correlated handover success triggers bounded targeted topology refresh; observed parent changes trigger fresh metrics without inventing evidence\n";
    std::cout << "PASS: production polling includes childless APs; their native replies exercise idle uplinks without inventing serving samples\n";
    std::cout << "PASS: production controller wire handler enforces MID, sender, destination, STA, parent epoch, channel, freshness, RCPI and native completion ownership\n";
}
'''.replace("STATE", state).replace("HANDLER", handler).replace("AP_QUERIES", ap_queries).replace("REFRESH", refresh)
with tempfile.TemporaryDirectory(prefix="native-backhaul-controller-") as temporary:
    executable = Path(temporary) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-parameter", "-pthread", "-I", str(root / "inc"),
                    "-x", "c++", "-", "-o", str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
