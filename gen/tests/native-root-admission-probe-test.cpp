#include PROBE_HEADER

#include <cstdlib>
#include <functional>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

namespace rooted = em_rooted_admission;

static unsigned int failures = 0;

static void check(bool condition, const std::string &name)
{
    std::cout << (condition ? "PASS\t" : "FAIL\t") << name << '\n';
    if (!condition) ++failures;
}

static rooted::mac_address mac(unsigned char suffix)
{
    return rooted::mac_address{{2, 0, 0, 0, 0, suffix}};
}

static rooted::nonce_value nonce(unsigned char first)
{
    rooted::nonce_value value{};
    for (std::size_t index = 0; index < value.size(); ++index) {
        value[index] = static_cast<unsigned char>(first + index);
    }
    return value;
}

static rooted::link_context context()
{
    rooted::link_context value{};
    value.agent = mac(2);
    value.controller = mac(1);
    value.station = mac(16);
    value.parent = mac(32);
    value.generation = 0x0123456789abcdefULL;
    value.connected = true;
    return value;
}

static rooted::message request(const rooted::link_context &current = context())
{
    rooted::message value{};
    value.agent = current.agent;
    value.controller = current.controller;
    value.station = current.station;
    value.parent = current.parent;
    value.generation = current.generation;
    value.nonce = nonce(16);
    value.mid = 0xa1b2;
    return value;
}

static bool same_message(const rooted::message &left, const rooted::message &right)
{
    return left.opcode == right.opcode && left.agent == right.agent &&
        left.controller == right.controller && left.station == right.station &&
        left.parent == right.parent && left.generation == right.generation &&
        left.nonce == right.nonce && left.mid == right.mid;
}

static rooted::wire_frame encoded(rooted::message value = request())
{
    rooted::wire_frame frame{};
    if (!rooted::encode(value, frame)) {
        std::cerr << "Invalid fixture\n";
        std::exit(2);
    }
    return frame;
}

static rooted::wire_frame response_for(rooted::message value = request())
{
    value.opcode = rooted::operation::reply;
    return encoded(value);
}

static std::string hex(const rooted::wire_frame &frame)
{
    const char digits[] = "0123456789abcdef";
    std::string output;
    for (const auto octet : frame) {
        output.push_back(digits[octet >> 4]);
        output.push_back(digits[octet & 15]);
    }
    return output;
}

static void codec_tests()
{
    const auto valid = encoded();
    const std::string golden =
        "020000000001020000000002893a00000004a1b200800b002bd89c8e52500101"
        "101112131415161718191a1b1c1d1e1f0200000000100200000000200123456789abcdef000000";
    check(hex(valid) == golden, "wire.independent-golden-request");
    rooted::message decoded{};
    check(rooted::decode(valid.data(), valid.size(), decoded) &&
        same_message(decoded, request()), "wire.request-roundtrip");
    auto reply = response_for();
    auto expected = request();
    expected.opcode = rooted::operation::reply;
    check(rooted::decode(reply.data(), reply.size(), decoded) &&
        same_message(decoded, expected), "wire.reply-roundtrip");
    check(std::equal(valid.begin(), valid.begin() + 6, reply.begin() + 6) &&
        std::equal(valid.begin() + 6, valid.begin() + 12, reply.begin()),
        "wire.reply-swaps-only-endpoints-and-opcode");
    for (std::size_t length = 0; length < valid.size(); ++length) {
        check(!rooted::decode(valid.data(), length, decoded),
            "wire.truncated-" + std::to_string(length));
    }
    check(!rooted::decode(nullptr, valid.size(), decoded), "wire.null-pointer");
    check(!rooted::decode(valid.data(), std::numeric_limits<std::size_t>::max(), decoded),
        "wire.oversize-no-read");
    for (unsigned char suffix : {0, 1, 255}) {
        std::vector<unsigned char> extra(valid.begin(), valid.end());
        extra.push_back(suffix);
        check(!rooted::decode(extra.data(), extra.size(), decoded),
            "wire.trailing-octet-" + std::to_string(suffix));
    }
    const std::vector<std::size_t> strict_octets{12, 13, 14, 15, 16, 17, 20, 21,
        22, 23, 24, 25, 26, 27, 28, 29, 30, 68, 69, 70};
    for (const auto offset : strict_octets) {
        auto bad = valid;
        bad[offset] ^= 1;
        const auto prior = decoded;
        check(!rooted::decode(bad.data(), bad.size(), decoded) && same_message(prior, decoded),
            "wire.strict-octet-" + std::to_string(offset));
    }
    for (unsigned int bit = 0; bit < 8; ++bit) {
        auto bad = valid;
        bad[21] ^= static_cast<unsigned char>(1U << bit);
        check(!rooted::decode(bad.data(), bad.size(), decoded),
            "wire.fragment-relay-reserved-flag-" + std::to_string(bit));
    }
    for (unsigned int opcode = 0; opcode <= 255; ++opcode) {
        if (opcode == 1 || opcode == 2) continue;
        auto bad = valid;
        bad[31] = static_cast<unsigned char>(opcode);
        check(!rooted::decode(bad.data(), bad.size(), decoded),
            "wire.unknown-opcode-" + std::to_string(opcode));
    }
    for (const auto offset : {0, 6, 48, 54}) {
        auto bad = valid;
        bad[offset] |= 1;
        check(!rooted::decode(bad.data(), bad.size(), decoded),
            "wire.multicast-mac-" + std::to_string(offset));
        std::fill_n(bad.begin() + offset, 6, 0);
        check(!rooted::decode(bad.data(), bad.size(), decoded),
            "wire.zero-mac-" + std::to_string(offset));
        std::fill_n(bad.begin() + offset, 6, 255);
        check(!rooted::decode(bad.data(), bad.size(), decoded),
            "wire.broadcast-mac-" + std::to_string(offset));
    }
    auto bad = valid;
    std::copy_n(bad.begin(), 6, bad.begin() + 6);
    check(!rooted::decode(bad.data(), bad.size(), decoded), "wire.self-agent-controller");
    bad = valid;
    std::copy_n(bad.begin() + 48, 6, bad.begin() + 54);
    check(!rooted::decode(bad.data(), bad.size(), decoded), "wire.self-station-parent");
    bad = valid;
    std::fill_n(bad.begin() + 32, 16, 0);
    check(!rooted::decode(bad.data(), bad.size(), decoded), "wire.zero-nonce");
    std::vector<unsigned char> duplicate(valid.begin(), valid.end() - 3);
    duplicate.insert(duplicate.end(), valid.begin() + 22, valid.end());
    check(!rooted::decode(duplicate.data(), duplicate.size(), decoded), "wire.duplicate-vendor-tlv");
    bad = valid;
    bad[22] = 0;
    bad[23] = 0;
    bad[24] = 0;
    check(!rooted::decode(bad.data(), bad.size(), decoded), "wire.early-eom");
    for (const auto generation : {0ULL, 1ULL, 0xffffffffULL, 0x100000000ULL,
            0x8000000000000000ULL, 0xffffffffffffffffULL}) {
        auto value = request();
        value.generation = generation;
        auto frame = encoded(value);
        check(rooted::decode(frame.data(), frame.size(), decoded) && decoded.generation == generation,
            "wire.generation-u64-" + std::to_string(generation));
    }
    for (std::uint16_t mid : {0, 1, 32768, 65535}) {
        auto value = request();
        value.mid = mid;
        auto frame = encoded(value);
        check(rooted::decode(frame.data(), frame.size(), decoded) && decoded.mid == mid,
            "wire.mid-u16-" + std::to_string(mid));
    }
    auto invalid = request();
    invalid.opcode = static_cast<rooted::operation>(0);
    auto unchanged = valid;
    check(!rooted::encode(invalid, unchanged) && unchanged == valid, "wire.encode-failure-atomic");
}

static void controller_tests()
{
    const auto frame = encoded();
    rooted::wire_frame reply{};
    check(rooted::controller_reply(frame.data(), frame.size(), context().controller, reply) &&
        reply == response_for(), "controller.stateless-exact-echo");
    rooted::wire_frame repeated{};
    check(rooted::controller_reply(frame.data(), frame.size(), context().controller, repeated) &&
        repeated == reply, "controller.request-retransmission-idempotent");
    check(!rooted::controller_reply(frame.data(), frame.size(), mac(3), repeated) &&
        repeated == reply, "controller.wrong-local-identity-no-output");
    check(!rooted::controller_reply(frame.data(), frame.size(), rooted::mac_address{}, repeated),
        "controller.invalid-local-identity");
    check(!rooted::controller_reply(reply.data(), reply.size(), context().controller, repeated),
        "controller.never-echo-reply");
    auto bad = frame;
    bad[31] = 0;
    check(!rooted::controller_reply(bad.data(), bad.size(), context().controller, repeated),
        "controller.unrecognized-protocol-no-echo");
}

static bool begin(rooted::transaction_matcher &matcher, std::uint64_t now = 1000)
{
    rooted::wire_frame output{};
    return matcher.begin(context(), request().mid, request().nonce, now, output) && output == encoded();
}

static void matcher_tests()
{
    const auto current = context();
    const auto reply = response_for();
    rooted::transaction_matcher matcher;
    check(!matcher.accept(reply.data(), reply.size(), current, 1000), "matcher.unsolicited-reply");
    check(begin(matcher) && matcher.pending() && matcher.pending_message() &&
        same_message(*matcher.pending_message(), request()), "matcher.begin-owns-one-query");
    rooted::wire_frame untouched{};
    untouched.fill(7);
    auto prior = untouched;
    check(!matcher.begin(current, 4, nonce(64), 1001, untouched) && untouched == prior &&
        matcher.pending(), "matcher.second-query-cannot-overwrite");
    const auto reflected = encoded();
    check(!matcher.accept(reflected.data(), reflected.size(), current, 1001) && matcher.pending(),
        "matcher.reflected-request-not-proof");
    check(matcher.accept(reply.data(), reply.size(), current, 1002) && !matcher.pending() &&
        matcher.pending_message() == nullptr, "matcher.valid-reply-consumed");
    check(!matcher.accept(reply.data(), reply.size(), current, 1003), "matcher.consumed-replay");
    check(!matcher.begin(current, request().mid, request().nonce, 1004, untouched),
        "matcher.reject-immediate-nonce-reuse");
    for (const auto now : {1000ULL, 2999ULL, 3000ULL, 3001ULL, 999ULL}) {
        rooted::transaction_matcher bounded;
        begin(bounded);
        const bool expected = now >= 1000 && now <= 3000;
        check(bounded.accept(reply.data(), reply.size(), current, now) == expected &&
            !bounded.pending(), "matcher.deadline-" + std::to_string(now));
    }
    rooted::transaction_matcher near_overflow;
    const auto maximum = std::numeric_limits<std::uint64_t>::max();
    begin(near_overflow, maximum - 100);
    check(near_overflow.accept(reply.data(), reply.size(), current, maximum),
        "matcher.time-u64-no-deadline-addition-overflow");
    rooted::transaction_matcher zero_time;
    begin(zero_time, 0);
    check(zero_time.accept(reply.data(), reply.size(), current, 0), "matcher.monotonic-zero-valid");
    rooted::transaction_matcher expired;
    begin(expired);
    check(!expired.observe(current, 3001) && !expired.accept(reply.data(), reply.size(), current, 3001),
        "matcher.observed-expiry-invalidates");
    rooted::transaction_matcher canceled;
    begin(canceled);
    canceled.cancel();
    check(!canceled.accept(reply.data(), reply.size(), current, 1100), "matcher.canceled-replay");

    const std::vector<std::function<void(rooted::message &)>> mutations{
        [](rooted::message &value) { value.agent = mac(3); },
        [](rooted::message &value) { value.controller = mac(4); },
        [](rooted::message &value) { value.station = mac(17); },
        [](rooted::message &value) { value.parent = mac(33); },
        [](rooted::message &value) { ++value.generation; },
        [](rooted::message &value) { ++value.mid; }
    };
    for (std::size_t index = 0; index < mutations.size(); ++index) {
        rooted::transaction_matcher owner;
        begin(owner);
        auto wrong = request();
        mutations[index](wrong);
        auto frame = response_for(wrong);
        check(!owner.accept(frame.data(), frame.size(), current, 1001) && owner.pending() &&
            owner.accept(reply.data(), reply.size(), current, 1002),
            "matcher.wrong-response-field-preserves-pending-" + std::to_string(index));
    }
    for (std::size_t index = 0; index < 16; ++index) {
        rooted::transaction_matcher owner;
        begin(owner);
        auto wrong = request();
        wrong.nonce[index] ^= 1;
        auto frame = response_for(wrong);
        check(!owner.accept(frame.data(), frame.size(), current, 1001) && owner.pending(),
            "matcher.all-nonce-octets-compared-" + std::to_string(index));
    }
    for (unsigned int bit = 0; bit < 64; ++bit) {
        rooted::transaction_matcher owner;
        begin(owner);
        auto wrong = request();
        wrong.generation ^= std::uint64_t{1} << bit;
        auto frame = response_for(wrong);
        check(!owner.accept(frame.data(), frame.size(), current, 1001) && owner.pending(),
            "matcher.all-generation-bits-compared-" + std::to_string(bit));
    }
    const std::vector<std::function<void(rooted::link_context &)>> changes{
        [](rooted::link_context &value) { value.connected = false; },
        [](rooted::link_context &value) { value.agent = mac(3); },
        [](rooted::link_context &value) { value.controller = mac(4); },
        [](rooted::link_context &value) { value.station = mac(17); },
        [](rooted::link_context &value) { value.parent = mac(33); },
        [](rooted::link_context &value) { ++value.generation; }
    };
    for (std::size_t index = 0; index < changes.size(); ++index) {
        rooted::transaction_matcher owner;
        begin(owner);
        auto changed = current;
        changes[index](changed);
        check(!owner.accept(reply.data(), reply.size(), changed, 1001) && !owner.pending() &&
            !owner.accept(reply.data(), reply.size(), current, 1002),
            "matcher.current-link-change-permanently-invalidates-" + std::to_string(index));
    }
    rooted::transaction_matcher malformed;
    begin(malformed);
    check(!malformed.accept(nullptr, 0, current, 1001) && malformed.pending() &&
        malformed.accept(reply.data(), reply.size(), current, 1002),
        "matcher.malformed-frame-cannot-cancel-valid-proof");
    for (const auto variant : {0, 1, 2, 3}) {
        rooted::transaction_matcher invalid;
        auto changed = current;
        auto entropy = request().nonce;
        if (variant == 0) changed.connected = false;
        if (variant == 1) changed.controller = changed.agent;
        if (variant == 2) changed.station = changed.parent;
        if (variant == 3) entropy.fill(0);
        auto output = prior;
        check(!invalid.begin(changed, 0, entropy, 1000, output) && !invalid.pending() && output == prior,
            "matcher.invalid-begin-" + std::to_string(variant));
    }
}

static void renewal_tests()
{
    check(rooted::proof_window_ms == 2000 && rooted::renewal_interval_ms == 500 &&
        rooted::retry_interval_ms == 250 && rooted::initial_admission_ms == 10000,
        "renewal.native-timing-contract");
    const auto current = context();
    rooted::transaction_matcher matcher;
    rooted::wire_frame frame{};
    check(begin(matcher), "renewal.begin");
    check(!matcher.retry(999, frame) && !matcher.retry(1249, frame), "renewal.no-early-retry");
    check(matcher.retry(1250, frame) && frame == encoded(), "renewal.retry-exact-250-same-mid-nonce");
    check(!matcher.retry(1250, frame) && !matcher.retry(1499, frame), "renewal.retry-spacing");
    check(matcher.retry(1500, frame) && frame == encoded(), "renewal.second-retry-keeps-transaction");
    check(!matcher.expired(current, 3000) && matcher.retry(3000, frame), "renewal.window-inclusive");
    check(matcher.expired(current, 3001) && !matcher.retry(3001, frame), "renewal.retry-does-not-extend-deadline");
    auto changed = current;
    ++changed.generation;
    check(!matcher.expired(changed, 3001), "renewal.stale-generation-cannot-revoke-current");
    changed = current;
    changed.parent = mac(44);
    check(!matcher.expired(changed, 3001), "renewal.stale-parent-cannot-revoke-current");
    changed = current;
    changed.connected = false;
    check(!matcher.expired(changed, 3001), "renewal.disconnected-context-not-expiry-owner");
    matcher.cancel();
    check(!matcher.expired(current, 3001) && !matcher.retry(3001, frame), "renewal.cancel-clears-expiry-owner");
    check(matcher.begin(current, 14, nonce(40), 3500, frame), "renewal.new-round-new-nonce");
    auto old_reply = response_for();
    check(!matcher.accept(old_reply.data(), old_reply.size(), current, 3501) && matcher.pending(),
        "renewal.previous-round-replay-rejected");
    rooted::wire_frame reply{};
    check(rooted::controller_reply(frame.data(), frame.size(), current.controller, reply) &&
        matcher.accept(reply.data(), reply.size(), current, 3502), "renewal.new-round-proof");
    check(!matcher.expired(current, 9000), "renewal.accepted-round-no-stale-expiry");
}

static void generation_and_peer_tests()
{
    const auto old_reply = response_for();
    for (const bool same_parent : {false, true}) {
        for (unsigned int arrival_slot = 0; arrival_slot < 5; ++arrival_slot) {
            rooted::transaction_matcher owner;
            begin(owner);
            auto current = context();
            rooted::wire_frame new_request{};
            rooted::wire_frame new_reply{};
            bool outcome = true;
            for (unsigned int step = 0; step < 5; ++step) {
                if (step == arrival_slot) {
                    const bool accepted = owner.accept(old_reply.data(), old_reply.size(), current, 1100 + step);
                    outcome = outcome && accepted == (arrival_slot == 0);
                }
                if (step == 0) {
                    current.connected = false;
                    ++current.generation;
                    owner.observe(current, 1100 + step);
                } else if (step == 1) {
                    current.connected = true;
                    if (!same_parent) current.parent = mac(33);
                } else if (step == 2) {
                    outcome = owner.begin(current, request().mid, nonce(64), 1100 + step, new_request) && outcome;
                    outcome = rooted::controller_reply(new_request.data(), new_request.size(), current.controller,
                        new_reply) && outcome;
                } else if (step == 3) {
                    outcome = owner.accept(new_reply.data(), new_reply.size(), current, 1100 + step) && outcome;
                }
            }
            check(outcome && !owner.pending(), "generation.reconnect-" +
                std::string(same_parent ? "same-parent-" : "different-parent-") + std::to_string(arrival_slot));
        }
    }
    for (unsigned int mask = 0; mask < 16; ++mask) {
        rooted::transaction_matcher owner;
        begin(owner);
        auto next = context();
        ++next.generation;
        if (mask & 1) next.parent = mac(33);
        if (mask & 2) next.station = mac(17);
        if (mask & 4) next.controller = mac(4);
        if (mask & 8) next.agent = mac(3);
        owner.observe(next, 1100);
        rooted::wire_frame packet{};
        rooted::wire_frame reply{};
        const bool issued = owner.begin(next, request().mid, nonce(64), 1101, packet);
        const bool echoed = rooted::controller_reply(packet.data(), packet.size(), next.controller, reply);
        check(issued && echoed && !owner.accept(old_reply.data(), old_reply.size(), next, 1102) &&
            owner.accept(reply.data(), reply.size(), next, 1103),
            "generation.identity-combination-" + std::to_string(mask));
    }
    rooted::transaction_matcher first;
    rooted::transaction_matcher second;
    auto first_context = context();
    auto second_context = context();
    second_context.agent = mac(3);
    second_context.station = mac(17);
    rooted::wire_frame first_request{};
    rooted::wire_frame second_request{};
    rooted::wire_frame first_reply{};
    rooted::wire_frame second_reply{};
    const bool issued = first.begin(first_context, 77, nonce(16), 1000, first_request) &&
        second.begin(second_context, 77, nonce(64), 1000, second_request);
    const bool echoed = rooted::controller_reply(first_request.data(), first_request.size(),
        first_context.controller, first_reply) &&
        rooted::controller_reply(second_request.data(), second_request.size(),
            second_context.controller, second_reply);
    check(issued && echoed && !first.accept(second_reply.data(), second_reply.size(), first_context, 1001) &&
        !second.accept(first_reply.data(), first_reply.size(), second_context, 1001) &&
        first.accept(first_reply.data(), first_reply.size(), first_context, 1002) &&
        second.accept(second_reply.data(), second_reply.size(), second_context, 1002),
        "peers.shared-mid-proof-cannot-cross-agents");
    rooted::transaction_matcher collision_first;
    rooted::transaction_matcher collision_second;
    const bool collision_issued = collision_first.begin(first_context, 77, nonce(16), 1000, first_request) &&
        collision_second.begin(second_context, 77, nonce(16), 1000, second_request);
    const bool collision_echoed = rooted::controller_reply(first_request.data(), first_request.size(),
        first_context.controller, first_reply) &&
        rooted::controller_reply(second_request.data(), second_request.size(),
            second_context.controller, second_reply);
    check(collision_issued && collision_echoed &&
        !collision_first.accept(second_reply.data(), second_reply.size(), first_context, 1001) &&
        !collision_second.accept(first_reply.data(), first_reply.size(), second_context, 1001) &&
        collision_first.accept(first_reply.data(), first_reply.size(), first_context, 1002) &&
        collision_second.accept(second_reply.data(), second_reply.size(), second_context, 1002),
        "peers.same-mid-and-nonce-still-bound-to-agent");
    rooted::transaction_matcher disconnected;
    auto no_root = context();
    auto fake_peer = response_for();
    std::copy(second_context.agent.begin(), second_context.agent.end(), fake_peer.begin() + 6);
    begin(disconnected);
    check(!disconnected.accept(fake_peer.data(), fake_peer.size(), no_root, 1001) &&
        !disconnected.observe(no_root, 3001), "peers.peer-reply-not-controller-and-no-reply-expires");
    rooted::transaction_matcher epoch_zero;
    auto zero = context();
    zero.generation = 0;
    rooted::wire_frame packet{};
    rooted::wire_frame reply{};
    check(epoch_zero.begin(zero, 0, nonce(64), 1000, packet) &&
        rooted::controller_reply(packet.data(), packet.size(), zero.controller, reply) &&
        epoch_zero.accept(reply.data(), reply.size(), zero, 1001), "generation.zero-and-mid-zero-supported");
}

int main()
{
    codec_tests();
    controller_tests();
    matcher_tests();
    renewal_tests();
    generation_and_peer_tests();
    return failures == 0 ? 0 : 1;
}
