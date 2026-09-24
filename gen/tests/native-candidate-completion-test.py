"""Compile production candidate completion/serialization and exercise the HTTP handler offline."""

from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile


native = Path(sys.argv[1])
metrics = (native / "src/em/metrics/em_metrics.cpp").read_text()
controller = (native / "src/ctrl/dm_easy_mesh_ctrl.cpp").read_text()
model = (native / "inc/dm_easy_mesh.h").read_text()
main = (native / "src/rdkb-cli/main.go").read_text()


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index("\n}", start) + 2]


fields = model[model.index("    unsigned int m_num_unassoc_sta_metrics;"):
               model.index("    unsigned int m_num_unassoc_sta_errors")]
start = controller.index("            if (agent_dm != NULL && agent_dm->m_unassoc_sta_metrics_received_ms != 0)")
serializer = controller[start:controller.index("                for (unsigned int metric_idx", start)] + "\n}"
limit = re.search(r"^#define EM_MAX_UNASSOC_STA .*?$", (native / "inc/em_base.h").read_text(), re.M).group()
native_program = r'''
#include <arpa/inet.h>
#include <sys/time.h>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
LIMIT
using mac_address_t = unsigned char[6];
using mac_addr_str_t = char[18];
constexpr int EM_MAX_TLV_MEMBERS = 8;
constexpr int em_msg_type_unassoc_sta_link_metrics_rsp = 0x800e;
constexpr unsigned char em_tlv_type_unassoc_sta_link_metric_rsp = 0x98;
constexpr unsigned char em_tlv_type_eom = 0;
enum { em_state_ctrl_configured, em_state_ctrl_unassoc_sta_link_metrics_pending,
       em_cmd_type_unassoc_sta_query };
struct __attribute__((packed)) em_raw_hdr_t { mac_address_t dst, src; unsigned short type; };
struct __attribute__((packed)) em_cmdu_t {
    unsigned char version, reserved;
    unsigned short type, id;
    unsigned char fragment, flags;
};
struct __attribute__((packed)) em_tlv_t {
    unsigned char type;
    unsigned short len;
    unsigned char value[0];
};
struct __attribute__((packed)) em_unassoc_sta_metric_t {
    mac_address_t sta_mac;
    unsigned char channel;
    unsigned int time_delta;
    unsigned char rcpi;
};
struct em_unassoc_sta_metric_entry_t {
    mac_address_t sta_mac;
    unsigned char channel, op_class, rcpi;
    unsigned int time_delta;
};
static_assert(sizeof(em_raw_hdr_t) == 14 && sizeof(em_cmdu_t) == 8 &&
              sizeof(em_unassoc_sta_metric_t) == 12, "wire sizes");
struct dm_easy_mesh_t {
FIELDS
    static void macbytes_to_string(const unsigned char *address, char *output) {
        snprintf(output, 18, "%02x:%02x:%02x:%02x:%02x:%02x", address[0], address[1],
                 address[2], address[3], address[4], address[5]);
    }
};
struct cJSON {
    std::map<std::string, std::string> strings;
    std::map<std::string, double> numbers;
    std::map<std::string, std::unique_ptr<cJSON>> objects;
};
cJSON *cJSON_AddObjectToObject(cJSON *parent, const char *name) {
    parent->objects[name] = std::make_unique<cJSON>();
    return parent->objects[name].get();
}
void cJSON_AddStringToObject(cJSON *object, const char *name, const char *value) {
    object->strings[name] = value;
}
void cJSON_AddNumberToObject(cJSON *object, const char *name, double value) {
    object->numbers[name] = value;
}
void serialize(dm_easy_mesh_t *agent_dm, cJSON *dev_obj) {
    (void)dev_obj;
    mac_addr_str_t ruid_str;
SERIALIZER
}
void em_printfout(const char *, ...) {}
bool valid_message = true;
struct em_msg_t {
    em_msg_t(int, int, unsigned char *, unsigned int) {}
    int validate(char **) { return valid_message; }
};
struct em_orch_t {
    std::recursive_mutex mutex;
    int completed = 0;
    auto lock_commands() { return std::unique_lock<std::recursive_mutex>(mutex); }
    bool complete_command(int kind) {
        assert(kind == em_cmd_type_unassoc_sta_query);
        completed++;
        return true;
    }
};
struct em_t;
struct Manager {
    em_orch_t orchestration;
    std::vector<em_t *> radios;
    em_orch_t *get_orch() { return &orchestration; }
    void get_all_em_for_al_mac(const unsigned char *, std::vector<em_t *> &);
};
struct em_metrics_t {
    Manager *manager;
    bool m_unassoc_in_progress = false;
    Manager *get_mgr() { return manager; }
    int get_profile_type() { return 3; }
    int handle_unassoc_sta_link_metrics_tlv(unsigned char *, unsigned int, dm_easy_mesh_t *);
    int handle_unassoc_sta_link_metrics_rsp(unsigned char *, unsigned int);
};
struct em_t : em_metrics_t {
    dm_easy_mesh_t model{};
    mac_address_t agent{2, 0, 0, 0, 2, 0x20}, radio{2, 0, 0, 0, 2, 0x30};
    int state = em_state_ctrl_unassoc_sta_link_metrics_pending;
    unsigned short mid = 77;
    int get_state() { return state; }
    void set_state(int value) { state = value; }
    unsigned short get_unassoc_sta_query_msg_id() { return mid; }
    void clear_unassoc_sta_query_msg_id() { mid = 0; }
    dm_easy_mesh_t *get_data_model() { return &model; }
    unsigned char *get_radio_interface_mac() { return radio; }
};
void Manager::get_all_em_for_al_mac(const unsigned char *agent, std::vector<em_t *> &result) {
    for (auto *radio : radios) {
        if (memcmp(agent, radio->agent, 6) == 0) result.push_back(radio);
    }
}
METHODS
std::vector<unsigned char> response(em_t &owner, unsigned char count) {
    std::vector<unsigned char> frame(22 + 3 + 2 + count * 12 + 3, 0);
    memcpy(frame.data() + 6, owner.agent, 6);
    auto *header = reinterpret_cast<em_cmdu_t *>(frame.data() + 14);
    header->id = htons(owner.mid);
    auto *tlv = reinterpret_cast<em_tlv_t *>(frame.data() + 22);
    tlv->type = em_tlv_type_unassoc_sta_link_metric_rsp;
    tlv->len = htons(2 + count * 12);
    tlv->value[0] = 115;
    tlv->value[1] = count;
    for (unsigned int index = 0; index < count; ++index) {
        auto *metric = reinterpret_cast<em_unassoc_sta_metric_t *>(tlv->value + 2 + index * 12);
        metric->sta_mac[0] = 2;
        metric->sta_mac[5] = index + 1;
        metric->channel = 36;
        metric->rcpi = 88 + index;
        metric->time_delta = htonl(23);
    }
    return frame;
}
int main() {
    Manager manager;
    em_t receiver, owner;
    receiver.manager = owner.manager = &manager;
    manager.radios = {&owner};
    cJSON initial;
    serialize(&owner.model, &initial);
    assert(initial.objects.empty());
    for (unsigned char count : {0, 1, 2}) {
        owner.state = em_state_ctrl_unassoc_sta_link_metrics_pending;
        owner.mid = 77 + count;
        auto frame = response(owner, count);
        assert(receiver.handle_unassoc_sta_link_metrics_rsp(frame.data(), frame.size()) == 0);
        assert(owner.state == em_state_ctrl_configured && owner.mid == 0);
        assert(owner.model.m_num_unassoc_sta_metrics == count);
        assert(owner.model.m_unassoc_sta_metrics_received_ms > 0);
        assert(owner.model.m_unassoc_sta_metrics_msg_id == 77 + count);
        assert(memcmp(owner.model.m_unassoc_sta_metrics_ruid, owner.radio, 6) == 0);
        assert(receiver.model.m_unassoc_sta_metrics_received_ms == 0);
        for (unsigned int index = 0; index < count; ++index) {
            assert(owner.model.m_unassoc_sta_metrics[index].rcpi == 88 + index);
            assert(owner.model.m_unassoc_sta_metrics[index].time_delta == 23);
        }
        cJSON document;
        serialize(&owner.model, &document);
        auto &record = *document.objects.at("UnassociatedSTAQuery");
        assert(record.strings.at("RUID") == "02:00:00:00:02:30");
        assert(std::stoull(record.strings.at("ReceivedAtMS")) == owner.model.m_unassoc_sta_metrics_received_ms);
        assert(record.numbers.at("MessageID") == 77 + count);
        assert(record.numbers.at("MetricCount") == count);
        assert(record.numbers.size() == 2 && record.strings.size() == 2);
        const int completed = manager.orchestration.completed;
        assert(receiver.handle_unassoc_sta_link_metrics_rsp(frame.data(), frame.size()) == -1);
        assert(manager.orchestration.completed == completed);
    }
    owner.state = em_state_ctrl_unassoc_sta_link_metrics_pending;
    owner.mid = 91;
    const auto timestamp = owner.model.m_unassoc_sta_metrics_received_ms;
    const int completed = manager.orchestration.completed;
    auto reject = [&](std::vector<unsigned char> frame) {
        assert(receiver.handle_unassoc_sta_link_metrics_rsp(frame.data(), frame.size()) == -1);
        assert(!receiver.m_unassoc_in_progress);
        assert(owner.mid == 91 && owner.state == em_state_ctrl_unassoc_sta_link_metrics_pending);
        assert(owner.model.m_unassoc_sta_metrics_received_ms == timestamp);
        assert(owner.model.m_unassoc_sta_metrics_msg_id == 79);
        assert(owner.model.m_num_unassoc_sta_metrics == 2);
        assert(owner.model.m_unassoc_sta_metrics[0].rcpi == 88);
        assert(manager.orchestration.completed == completed);
    };
    auto frame = response(owner, 1);
    frame[11] ^= 1;
    reject(frame);
    frame = response(owner, 1);
    reinterpret_cast<em_cmdu_t *>(frame.data() + 14)->id = htons(92);
    reject(frame);
    valid_message = false;
    reject(response(owner, 1));
    valid_message = true;
    frame = response(owner, 1);
    frame.resize(10);
    reject(frame);
    frame = response(owner, 1);
    frame.pop_back();
    reject(frame);
    frame = response(owner, 1);
    reinterpret_cast<em_tlv_t *>(frame.data() + 22)->value[1] = 2;
    reject(frame);
    frame = response(owner, 1);
    reinterpret_cast<em_tlv_t *>(frame.data() + 22)->len = htons(100);
    reject(frame);
    frame = response(owner, 0);
    frame.resize(25);
    reinterpret_cast<em_tlv_t *>(frame.data() + 22)->type = em_tlv_type_eom;
    reinterpret_cast<em_tlv_t *>(frame.data() + 22)->len = 0;
    reject(frame);
    frame = response(owner, 1);
    frame[frame.size() - 1] = 1;
    reject(frame);
    reject(response(owner, EM_MAX_UNASSOC_STA + 1));
    frame = response(owner, 1);
    auto second = response(owner, 0);
    frame.resize(frame.size() - 3);
    frame.insert(frame.end(), second.begin() + 22, second.end());
    auto malformed = frame;
    reinterpret_cast<em_tlv_t *>(malformed.data() + 39)->value[1] = 1;
    reject(malformed);
    assert(receiver.handle_unassoc_sta_link_metrics_rsp(frame.data(), frame.size()) == 0);
    assert(owner.model.m_num_unassoc_sta_metrics == 1 && owner.model.m_unassoc_sta_metrics_msg_id == 91);
    puts("PASS native empty/partial/full completion, exact serialization, wrong AL/MID, duplicate and malformed response safety");
}
'''.replace("LIMIT", limit).replace("FIELDS", fields).replace("SERIALIZER", serializer).replace(
    "METHODS", "\n\n".join(function(metrics, signature) for signature in (
        "int em_metrics_t::handle_unassoc_sta_link_metrics_tlv(",
        "int em_metrics_t::handle_unassoc_sta_link_metrics_rsp(",
    )))

handler = function(main, "func unassocStaQueryHandler(")
assert "deadline := time.Now().Add(8 * time.Second)" in handler
assert handler.index("candidateRequests.acquire(") < handler.index("if current, currentErrors")
loader = function(main, "func loadCandidateLinkState(")
loader = "func decodeCandidateState(tree *nativeNode) ([]candidateLinkMetric, []candidateLinkError, []candidateCompletion, error) {\n" + loader[loader.index("    deviceList :="):]
loader = loader.replace("C.get_node_type(", "getNodeType(").replace(
    "C.em_network_node_data_type_number", "nativeNumber")
go_program = '''package main
import (
    "encoding/json"
    "fmt"
    "log"
    "net"
    "net/http"
    "sort"
    "strconv"
    "strings"
    "time"
)
type nativeNode struct {
    num_children int
    value_int int
    nodeType int
    child []*nativeNode
    values map[string]string
    objects map[string]*nativeNode
}
const nativeNumber = 1
func getNodeType(node *nativeNode) int { return node.nodeType }
func getNetworkTreeByKey(node *nativeNode, key string) *nativeNode { return node.objects[key] }
func getTreeValue(node *nativeNode, key string) string { return node.values[key] }
func getKeyIntValue(node *nativeNode, key string) int {
    value, _ := strconv.Atoi(getTreeValue(node, key))
    return value
}
var loadCandidateLinkState func() ([]candidateLinkMetric, []candidateLinkError, []candidateCompletion, error)
var submitCandidateQuery func([]byte) error
func nativeSteeringAvailable() bool { return false }
'''
go_program += "\n\n".join(function(main, signature) for signature in (
    "type unassocStaChannel struct {", "type unassocStaOpClass struct {",
    "type unassocStaQueryRequest struct {", "type candidateLinkMetric struct {",
    "func candidateMetricKey(", "func candidateMetricsForJSON(", "func candidateErrorsForJSON(",
)) + "\n" + loader + "\n" + handler
go_tests = r'''package main
import (
    "context"
    "encoding/json"
    "fmt"
    "net/http"
    "net/http/httptest"
    "reflect"
    "strings"
    "testing"
    "time"
)
const agent = "02:00:00:00:02:20"
const radio = "02:00:00:00:02:30"
const requestBody = `{"AlMac":"02:00:00:00:02:20","UnassocStaQueryList":[{"opclass":115,"channels":[{"channel":36,"sta_macs":["02:00:00:00:00:01","02:00:00:00:00:02"]}]}]}`
type snapshot struct {
    metrics []candidateLinkMetric
    rejected []candidateLinkError
    completions []candidateCompletion
    err error
}
func sample(count int) snapshot {
    received := uint64(time.Now().UnixMilli())
    state := snapshot{completions: []candidateCompletion{{AgentAL: agent, RUID: radio,
        MessageID: 77, ReceivedAt: received, MetricCount: count}}}
    for index := 0; index < count; index++ {
        state.metrics = append(state.metrics, candidateLinkMetric{AgentAL: agent, RUID: radio,
            STA: fmt.Sprintf("02:00:00:00:00:%02x", index+1), OpClass: 115, Channel: 36,
            RCPI: 88+index, MessageID: 77, ReceivedAt: received})
    }
    return state
}
func runQuery(test *testing.T, baseline snapshot, after func() snapshot, bound time.Duration) (*httptest.ResponseRecorder, int) {
    test.Helper()
    candidateRequests = newCandidateCoordinator(1, 32)
    submitted := 0
    var current snapshot
    submitCandidateQuery = func([]byte) error {
        submitted++
        current = after()
        return nil
    }
    loadCandidateLinkState = func() ([]candidateLinkMetric, []candidateLinkError, []candidateCompletion, error) {
        state := baseline
        if submitted != 0 { state = current }
        return state.metrics, state.rejected, state.completions, state.err
    }
    ctx, cancel := context.WithTimeout(context.Background(), bound)
    defer cancel()
    request := httptest.NewRequest(http.MethodPost, "/unassoc_sta_query", strings.NewReader(requestBody)).WithContext(ctx)
    writer := httptest.NewRecorder()
    unassocStaQueryHandler(writer, request)
    if len(candidateRequests.active) != 0 { test.Fatal("candidate gate leaked") }
    return writer, submitted
}
func decode(test *testing.T, writer *httptest.ResponseRecorder) map[string]interface{} {
    test.Helper()
    var body map[string]interface{}
    if err := json.Unmarshal(writer.Body.Bytes(), &body); err != nil { test.Fatal(err) }
    return body
}
func TestTerminalPartialAndEmpty(test *testing.T) {
    for _, count := range []int{0, 1} {
        test.Run(fmt.Sprint(count), func(test *testing.T) {
            started := time.Now()
            writer, submitted := runQuery(test, snapshot{}, func() snapshot { return sample(count) }, time.Second)
            if writer.Code != http.StatusServiceUnavailable || submitted != 1 { test.Fatalf("status=%d submits=%d: %s", writer.Code, submitted, writer.Body) }
            body := decode(test, writer)
            if body["success"] != false || body["native_completed"] != true { test.Fatal(body) }
            if len(body["metrics"].([]interface{})) != count || len(body["rejected"].([]interface{})) != 0 { test.Fatal(body) }
            wanted := []interface{}{"02:00:00:00:00:01/115/36", "02:00:00:00:00:02/115/36"}[count:]
            if !reflect.DeepEqual(body["missing_expected_keys"], wanted) { test.Fatal(body) }
            if count == 1 && body["metrics"].([]interface{})[0].(map[string]interface{})["rcpi"] != float64(88) { test.Fatal(body) }
            completion := body["completion"].(map[string]interface{})
            if completion["metric_count"] != float64(count) || completion["message_id"] != float64(77) || completion["ruid"] != radio { test.Fatal(completion) }
            if time.Since(started) >= time.Second { test.Fatal("terminal response waited for transport timeout") }
        })
    }
}
func TestCompleteAndRealRejectionPreserved(test *testing.T) {
    for _, count := range []int{0, 1, 2} {
        writer, _ := runQuery(test, snapshot{}, func() snapshot {
            state := sample(count)
            for index := count; index < 2; index++ {
                state.rejected = append(state.rejected, candidateLinkError{AgentAL: agent, RUID: radio,
                    STA: fmt.Sprintf("02:00:00:00:00:%02x", index+1), ErrorCode: 1,
                    MessageID: 77, ReceivedAt: state.completions[0].ReceivedAt})
            }
            if count == 0 { state.completions = nil }
            return state
        }, time.Second)
        body := decode(test, writer)
        if writer.Code != http.StatusOK || body["success"] != true || body["native_completed"] != nil { test.Fatal(writer.Code, body) }
        if len(body["metrics"].([]interface{})) != count || len(body["rejected"].([]interface{})) != 2-count { test.Fatal(body) }
    }
}
func TestRejectionMustMatchCompletion(test *testing.T) {
    for _, field := range []string{"mid", "ruid", "before-submit", "after-completion"} {
        writer, _ := runQuery(test, snapshot{}, func() snapshot {
            state := sample(1)
            rejected := candidateLinkError{AgentAL: agent, RUID: radio, STA: "02:00:00:00:00:02",
                ErrorCode: 1, MessageID: 77, ReceivedAt: state.completions[0].ReceivedAt}
            switch field {
            case "mid": rejected.MessageID++
            case "ruid": rejected.RUID = "02:00:00:00:02:31"
            case "before-submit": rejected.ReceivedAt -= 1000
            case "after-completion": rejected.ReceivedAt++
            }
            state.rejected = []candidateLinkError{rejected}
            return state
        }, time.Second)
        body := decode(test, writer)
        if writer.Code != http.StatusServiceUnavailable || len(body["rejected"].([]interface{})) != 0 { test.Fatal(field, body) }
    }
}
func TestStaleUncorrelatedAndInconsistentCompletionIgnored(test *testing.T) {
    for _, field := range []string{"stale", "future", "before-submit", "al", "mid", "ruid", "count", "baseline-error", "no-record"} {
        test.Run(field, func(test *testing.T) {
            baseline := snapshot{}
            if field == "baseline-error" { baseline.err = fmt.Errorf("read failed") }
            writer, _ := runQuery(test, baseline, func() snapshot {
                state := sample(1)
                record := &state.completions[0]
                switch field {
                case "stale": record.ReceivedAt -= 16000
                case "future": record.ReceivedAt += 16000
                case "before-submit": record.ReceivedAt -= 1000
                case "al": record.AgentAL = "02:00:00:00:03:20"
                case "mid": record.MessageID++
                case "ruid": record.RUID = "02:00:00:00:02:31"
                case "count": record.MetricCount++
                case "no-record": state.completions = nil
                }
                return state
            }, 150*time.Millisecond)
            if writer.Body.Len() != 0 { test.Fatalf("uncorrelated completion used: %s", writer.Body) }
        })
    }
}
func TestBaselineAndMIDWrap(test *testing.T) {
    baseline := sample(0)
    writer, _ := runQuery(test, baseline, func() snapshot { return baseline }, 150*time.Millisecond)
    if writer.Body.Len() != 0 { test.Fatalf("baseline reused: %s", writer.Body) }
    writer, _ = runQuery(test, snapshot{}, func() snapshot {
        state := sample(0)
        state.completions[0].MessageID = 0
        return state
    }, time.Second)
    if writer.Code != http.StatusServiceUnavailable { test.Fatal(writer.Body) }
}
func TestTransportLossStillWaitsEightSeconds(test *testing.T) {
    started := time.Now()
    writer, submitted := runQuery(test, snapshot{}, func() snapshot { return snapshot{} }, 11*time.Second)
    elapsed := time.Since(started)
    body := decode(test, writer)
    if writer.Code != http.StatusGatewayTimeout || elapsed < 8*time.Second || submitted != 1 { test.Fatal(writer.Code, elapsed, submitted) }
    if body["success"] != false || body["native_completed"] != nil { test.Fatal(body) }
}
func TestPerALGatePrecedesBaselineAndSubmission(test *testing.T) {
    candidateRequests = newCandidateCoordinator(1, 32)
    release, err := candidateRequests.acquire(context.Background(), agent)
    if err != nil { test.Fatal(err) }
    defer release()
    loadCandidateLinkState = func() ([]candidateLinkMetric, []candidateLinkError, []candidateCompletion, error) {
        test.Fatal("baseline read escaped occupied AL gate")
        return nil, nil, nil, nil
    }
    submitCandidateQuery = func([]byte) error {
        test.Fatal("submission escaped occupied AL gate")
        return nil
    }
    ctx, cancel := context.WithTimeout(context.Background(), 150*time.Millisecond)
    defer cancel()
    request := httptest.NewRequest(http.MethodPost, "/unassoc_sta_query", strings.NewReader(requestBody)).WithContext(ctx)
    writer := httptest.NewRecorder()
    unassocStaQueryHandler(writer, request)
    if writer.Code != http.StatusServiceUnavailable { test.Fatal(writer.Code) }
}
func TestCompletionDoesNotMixAgentsOrRounds(test *testing.T) {
    baseline := sample(0)
    baseline.completions[0].AgentAL = "02:00:00:00:03:20"
    baseline.completions[0].ReceivedAt += 10000
    writer, _ := runQuery(test, baseline, func() snapshot {
        state := sample(2)
        state.completions[0].MetricCount = 0
        state.metrics[0].MessageID++
        state.metrics[1].RUID = "02:00:00:00:02:31"
        return state
    }, time.Second)
    body := decode(test, writer)
    if writer.Code != http.StatusServiceUnavailable || len(body["metrics"].([]interface{})) != 0 ||
        len(body["missing_expected_keys"].([]interface{})) != 2 { test.Fatal(body) }
}
func TestNativeCompletionDecoder(test *testing.T) {
    for _, count := range []string{"0", "1", "bad", ""} {
        record := &nativeNode{values: map[string]string{"RUID": radio, "ReceivedAtMS": "12345"},
            objects: map[string]*nativeNode{"MessageID": {nodeType: nativeNumber, value_int: 77}}}
        if count == "0" || count == "1" {
            record.objects["MetricCount"] = &nativeNode{nodeType: nativeNumber, value_int: int(count[0]-'0')}
        } else if count == "bad" {
            record.objects["MetricCount"] = &nativeNode{}
        }
        device := &nativeNode{values: map[string]string{"ID": agent}, objects: map[string]*nativeNode{"UnassociatedSTAQuery": record}}
        tree := &nativeNode{objects: map[string]*nativeNode{"DeviceList": {num_children: 1, child: []*nativeNode{device}}}}
        metrics, rejected, completions, err := decodeCandidateState(tree)
        if err != nil || len(metrics) != 0 || len(rejected) != 0 { test.Fatal(err, metrics, rejected) }
        if count == "bad" || count == "" {
            if len(completions) != 0 { test.Fatal(completions) }
        } else if len(completions) != 1 || completions[0].AgentAL != agent || completions[0].RUID != radio || completions[0].MessageID != 77 || completions[0].ReceivedAt != 12345 {
            test.Fatal(completions)
        }
    }
}
'''

with tempfile.TemporaryDirectory(prefix="native-candidate-completion-") as temporary:
    directory = Path(temporary)
    executable = directory / "native-test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
                    "-x", "c++", "-", "-o", str(executable)],
                   input=native_program, text=True, check=True, timeout=60)
    subprocess.run([str(executable)], check=True, timeout=10)
    (directory / "handler.go").write_text(go_program)
    (directory / "handler_test.go").write_text(go_tests)
    for name in ("candidate_completion.go", "candidate_rejection.go", "candidate_coordination.go"):
        (directory / name).write_text((native / "src/rdkb-cli" / name).read_text())
    environment = dict(os.environ, GO111MODULE="off", GOWORK="off", GOCACHE=str(directory / "go-cache"))
    subprocess.run(["go", "test", "-v", "-timeout=45s", "."], cwd=directory,
                   env=environment, check=True, timeout=120)
print("PASS offline native/CLI terminal completion contract; real transport-loss timeout remains eight seconds")
