from pathlib import Path
import subprocess
import sys
import tempfile


root = Path(sys.argv[1])
source = (root / "src/agent/dm_easy_mesh_agent.cpp").read_text()
start = source.index('    cJSON *query_id = cJSON_GetObjectItemCaseSensitive(json, "QueryId");')
implementation = source[start:source.index("    memset(rsp, 0, sizeof(*rsp));", start)]
program = r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>
#include "em_unassoc_query_tracker.h"
#define em_printfout(...) (void)0
struct cJSON {
    double valuedouble = 0;
    int valueint = 0;
    bool number = true;
    cJSON *query = nullptr;
    cJSON *collected = nullptr;
};
cJSON *cJSON_GetObjectItemCaseSensitive(cJSON *value, const char *name) {
    return std::string(name) == "QueryId" ? value->query : value->collected;
}
bool cJSON_IsNumber(cJSON *value) { return value && value->number; }
void cJSON_Delete(cJSON *) {}
int parse(cJSON *json, unsigned short &mid, unsigned int &age) {
IMPLEMENTATION
    mid = result_id;
    age = delta_ms;
    return 1;
}
int main() {
    const int64_t now = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    cJSON identifier{77, 77}, collected{static_cast<double>(now - 1000), 0}, document;
    document.query = &identifier;
    document.collected = &collected;
    unsigned short mid = 0;
    unsigned int age = 0;
    assert(parse(&document, mid, age) == 1 && mid == 77 && age >= 1000 && age <= 6000);
    identifier.valuedouble = identifier.valueint = 0;
    assert(parse(&document, mid, age) == 1 && mid == 0);
    identifier.valuedouble = identifier.valueint = 65535;
    assert(parse(&document, mid, age) == 1 && mid == 65535);
    identifier.valuedouble = identifier.valueint = 65536;
    assert(parse(&document, mid, age) == 0);
    identifier.valuedouble = identifier.valueint = -1;
    assert(parse(&document, mid, age) == 0);
    identifier.valuedouble = 77.5;
    identifier.valueint = 77;
    assert(parse(&document, mid, age) == 0);
    identifier.valuedouble = 77;
    document.query = nullptr;
    assert(parse(&document, mid, age) == 0);
    document.query = &identifier;
    document.collected = nullptr;
    assert(parse(&document, mid, age) == 0);
    document.collected = &collected;
    for (double invalid : {0.0, -1.0, static_cast<double>(now + 100000),
            static_cast<double>(now - 7000), static_cast<double>(now - 1000) + 0.5}) {
        collected.valuedouble = invalid;
        assert(parse(&document, mid, age) == 0);
    }
    em_unassoc_query_tracker tracker;
    assert(tracker.insert(77, {"sta"}, now - 2000));
    assert(tracker.insert(78, {"sta"}, now - 500));
    auto replies = tracker.accept(77, {{"sta", 90, now - 1000}}, now);
    assert(replies.size() == 1 && replies[0].mid == 77);
    replies = tracker.accept(78, {{"sta", 90, now - 1000}}, now);
    assert(replies.size() == 1 && replies[0].metrics.empty());
    assert(tracker.accept(77, {{"sta", 92, now}}, now).empty());
    assert(tracker.insert(78, {"sta"}, now));
    replies = tracker.accept(78, {{"sta", 94, now}}, now + 7000);
    assert(replies.size() == 1 && replies[0].metrics.empty());
    assert(tracker.insert(78, {"sta"}, now + 7000));
    replies = tracker.accept(78, {{"sta", 96, now + 7100}}, now + 7100);
    assert(replies.size() == 1 && replies[0].mid == 78 && replies[0].metrics[0].rcpi == 96);
    std::cout << "PASS: production native candidate metadata rejects missing, stale, future and malformed values; queue time ages evidence and callbacks cannot satisfy another round\n";
}
'''.replace("IMPLEMENTATION", implementation)
with tempfile.TemporaryDirectory(prefix="native-candidate-metadata-") as temporary:
    executable = Path(temporary) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
                    "-I", str(root / "inc"), "-x", "c++", "-", "-o", str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
