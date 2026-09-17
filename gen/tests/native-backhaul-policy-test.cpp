#include "em_backhaul_policy.h"
#include "em_backhaul_wire.h"
#include "em_unassoc_query_tracker.h"
#include <cassert>
#include <iostream>

using em_backhaul::snapshot;

snapshot fixture(int64_t now, uint64_t round)
{
    snapshot network;
    network.root = "gateway";
    network.nodes["gateway"] = {"gateway", "", "", {}};
    network.nodes["upper"] = {"upper", "upper-sta", "root-ap", {66, now, 0}};
    network.nodes["lower"] = {"lower", "lower-sta", "root-ap", {66, now, 0}};
    network.nodes["moving"] = {"moving", "moving-sta", "upper-ap", {62, now, 0}};
    network.aps["root-ap"] = {"gateway", "root-ap", 115, 36};
    network.aps["upper-ap"] = {"upper", "upper-ap", 115, 36};
    network.aps["lower-ap"] = {"lower", "lower-ap", 115, 36};
    network.aps["moving-ap"] = {"moving", "moving-ap", 115, 36};
    network.candidates[{"moving-sta", "lower-ap"}] = {92, now, round};
    return network;
}

bool selects(snapshot network)
{
    em_backhaul::policy policy;
    policy.observe(network, 1000);
    assert(policy.evaluate(network, 11000).empty());
    for (auto &entry : network.candidates) ++entry.second.round;
    return !policy.evaluate(network, 12000).empty();
}

int main()
{
    auto network = fixture(11000, 1);
    assert(selects(network));
    em_backhaul::policy policy;
    policy.observe(network, 1000);
    assert(policy.evaluate(network, 9000).empty());
    assert(policy.evaluate(network, 11000).empty());
    assert(policy.evaluate(network, 12000).empty());
    network.candidates[{"moving-sta", "lower-ap"}].round = 2;
    auto decisions = policy.evaluate(network, 12000);
    assert(decisions.size() == 1 && decisions.front().target == "lower-ap");
    assert(decisions.front().path_rcpi == 66 && decisions.front().serving_rcpi == 62);
    policy.attempted("moving", 12000, true);
    network = fixture(15000, 3);
    assert(policy.evaluate(network, 15000).empty());
    network = fixture(33000, 4);
    assert(policy.evaluate(network, 33000).empty());
    network = fixture(34000, 5);
    assert(policy.evaluate(network, 34000).size() == 1);
    network.nodes["moving"].parent_bssid = "lower-ap";
    network.nodes["moving"].serving = {92, 35000, 0};
    assert(policy.evaluate(network, 35000).empty());

    network = fixture(11000, 1);
    network.nodes["lower"].serving.rcpi = 60;
    assert(!selects(network));
    network = fixture(11000, 1);
    network.candidates[{"moving-sta", "lower-ap"}].rcpi = 73;
    assert(!selects(network));
    network.candidates[{"moving-sta", "lower-ap"}].rcpi = 74;
    assert(selects(network));
    network = fixture(11000, 1);
    network.nodes["lower"].parent_bssid = "moving-ap";
    assert(!selects(network));
    network = fixture(11000, 1);
    network.nodes["lower"].parent_bssid = "missing-ap";
    assert(!selects(network));
    network = fixture(11000, 1);
    network.nodes["upper"].parent_bssid = "moving-ap";
    assert(!selects(network));
    network = fixture(11000, 1);
    network.nodes["lower"].serving.observed = 1000;
    assert(!selects(network));
    network = fixture(11000, 1);
    network.nodes["moving"].serving.observed = 1000;
    assert(!selects(network));
    network = fixture(11000, 1);
    network.candidates[{"moving-sta", "lower-ap"}].observed = 500;
    assert(!selects(network));
    network = fixture(11000, 1);
    network.candidates[{"moving-sta", "lower-ap"}].observed = 13000;
    assert(!selects(network));
    network = fixture(11000, 1);
    network.aps["lower-ap"].channel = 40;
    assert(!selects(network));
    network = fixture(11000, 1);
    network.aps["lower-ap"].op_class = 81;
    assert(!selects(network));
    for (int invalid : {-1, 221, 255}) {
        network = fixture(11000, 1);
        network.candidates[{"moving-sta", "lower-ap"}].rcpi = invalid;
        assert(!selects(network));
    }
    network = fixture(11000, 1);
    network.nodes["lower"].parent_bssid = "upper-ap";
    network.nodes["upper"].serving.rcpi = 62;
    assert(!selects(network));
    network.nodes["upper"].serving.rcpi = 66;
    assert(selects(network));
    network = fixture(11000, 1);
    assert(em_backhaul::root_path(network, "lower", "moving", 11000).valid);
    network.uncertain["lower"] = "moving-ap";
    assert(!em_backhaul::root_path(network, "lower", "moving", 11000).valid);
    assert(!selects(network));
    network = fixture(11000, 1);
    network.uncertain["moving"] = "lower-ap";
    assert(selects(network));
    network.uncertain["moving"] = "root-ap";
    assert(!selects(network));
    network.uncertain["moving"] = "";
    assert(!selects(network));

    em_unassoc_query_tracker tracker;
    assert(tracker.insert(10, {"client"}, 1000));
    assert(tracker.insert(11, {"backhaul"}, 1100));
    assert(!tracker.insert(10, {"wrong"}, 1100));
    auto stale = tracker.accept(10, {{"client", 90, 999}}, 1200);
    assert(stale.size() == 1 && stale.front().metrics.empty());
    assert(tracker.insert(10, {"client"}, 1200));
    auto replies = tracker.accept(11, {{"backhaul", 94, 1150}}, 1200);
    assert(replies.size() == 1 && replies.front().mid == 11);
    replies = tracker.accept(10, {{"client", 88, 1250}}, 1300);
    assert(replies.size() == 1 && replies.front().mid == 10);
    assert(tracker.accept(10, {{"client", 88, 1250}}, 1300).empty());
    assert(tracker.insert(12, {"first", "second"}, 1500));
    replies = tracker.accept(12, {{"first", 82, 1600}}, 1700);
    assert(replies.size() == 1 && replies.front().metrics.size() == 1);
    replies = tracker.accept(12, {{"second", 84, 1750}}, 1800);
    assert(replies.empty());
    assert(tracker.insert(13, {"overlap"}, 2000));
    assert(tracker.insert(14, {"overlap"}, 2100));
    replies = tracker.accept(13, {{"overlap", 255, 2200}}, 2300);
    assert(replies.size() == 1 && replies[0].mid == 13);
    assert(replies.front().metrics.front().rcpi == 255);
    assert(tracker.accept(13, {{"overlap", 80, 2400}}, 2400).empty());
    replies = tracker.accept(14, {{"overlap", 80, 2500}}, 2500);
    assert(replies.size() == 1 && replies[0].mid == 14);
    assert(tracker.insert(15, {"late"}, 3000));
    assert(tracker.accept(15, {{"late", 80, 40000}}, 40000).empty());
    assert(tracker.insert(16, {"first", "second"}, 41000));
    replies = tracker.accept(16, {}, 42000);
    assert(replies.size() == 1 && replies.front().mid == 16 && replies.front().metrics.empty());
    assert(!replies.front().op_classes.empty());
    assert(!tracker.contains(16, 42000));

    const std::string destination("\x02\x01\x02\x03\x04\x05", 6);
    const std::string source("\x02\x01\x02\x03\x04\x06", 6);
    auto packet = em_backhaul::frame(destination, source, 0x8019, 0x1234, 0x9e,
        std::vector<unsigned char>(14, 1));
    std::vector<em_backhaul::wire_tlv> tlvs;
    assert(em_backhaul::parse_frame(packet.data(), packet.size(), tlvs));
    assert(tlvs.size() == 1 && tlvs.front().size == 14);
    assert(em_backhaul::read16(packet.data() + 18) == 0x1234);
    for (size_t size = 0; size < packet.size(); ++size)
        assert(!em_backhaul::parse_frame(packet.data(), size, tlvs));
    packet[20] = 1;
    assert(!em_backhaul::parse_frame(packet.data(), packet.size(), tlvs));
    packet[20] = 0;
    packet[21] = 0;
    assert(!em_backhaul::parse_frame(packet.data(), packet.size(), tlvs));
    packet[21] = 0x80;
    packet[24] = 255;
    assert(!em_backhaul::parse_frame(packet.data(), packet.size(), tlvs));
    std::cout << "PASS: native backhaul policy, loop/path guards, freshness, dwell, hysteresis, wire bounds and concurrent query ownership\n";
}
