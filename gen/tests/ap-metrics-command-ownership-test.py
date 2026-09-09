#!/usr/bin/env python3
import argparse
import subprocess
import tempfile
from pathlib import Path


parser = argparse.ArgumentParser(description="Compile production AP event dispatch with interleaved command retirement")
parser.add_argument("source_root", type=Path)
args = parser.parse_args()
source = (args.source_root / "src/em/em.cpp").read_text()
start = source.index("        case em_cmd_event_type_ap_metrics_report:", source.index("void em_t::proto_process(em_cmd_event_t"))
end = source.index("        case em_cmd_event_type_failed_connection:", start)
dispatch = source[start:end]
harness = r'''
#include <cassert>
#include <iostream>
#include <cstddef>
constexpr int em_cmd_event_type_ap_metrics_report = 1;
struct em_cmd_ap_metrics_rprt_params_t { int num_radios; };
struct em_cmd_params_t {
    struct { em_cmd_ap_metrics_rprt_params_t ap_metrics_params; } u;
};
struct em_cmd_t {
    em_cmd_params_t parameters = {{{3}}};
    static int retired;
    em_cmd_params_t *get_param() { return &parameters; }
    void deinit() { retired++; }
};
int em_cmd_t::retired = 0;
struct em_cmd_event_t { int type; void *cmd_ptr; };
struct em_metrics_t {
    em_cmd_t *m_cmd = nullptr;
    em_cmd_t *replacement = nullptr;
    int reports = 0;
    void send_ap_metrics_response(const em_cmd_ap_metrics_rprt_params_t &params) {
        assert(params.num_radios == 3);
        m_cmd = replacement;
        assert(params.num_radios == 3);
        reports++;
    }
    void process_agent_state(int) {
        send_ap_metrics_response(m_cmd->get_param()->u.ap_metrics_params);
    }
};
struct em_t : em_metrics_t { void proto_process(em_cmd_event_t *cevt); };
void em_t::proto_process(em_cmd_event_t *cevt) {
    switch (cevt->type) {
'''
harness += dispatch
harness += r'''
    }
}
int main() {
    em_t radio;
    em_cmd_t previous, newer;
    for (em_cmd_t *replacement : {&newer, static_cast<em_cmd_t *>(nullptr)}) {
        radio.m_cmd = &previous;
        radio.replacement = replacement;
        em_cmd_event_t event{em_cmd_event_type_ap_metrics_report, new em_cmd_t};
        radio.proto_process(&event);
        assert(radio.m_cmd == replacement);
        assert(event.cmd_ptr == nullptr);
    }
    assert(radio.reports == 2);
    assert(em_cmd_t::retired == 2);
    em_cmd_event_t empty{em_cmd_event_type_ap_metrics_report, nullptr};
    radio.proto_process(&empty);
    assert(radio.reports == 2);
    std::cout << "PASS AP event ownership survives command completion/replacement and null events\n";
}
'''
with tempfile.TemporaryDirectory(prefix="ap-metrics-ownership-") as directory:
    root = Path(directory)
    translation_unit = root / "test.cpp"
    binary = root / "test"
    translation_unit.write_text(harness)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2",
                    str(translation_unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

metrics = (args.source_root / "src/em/metrics/em_metrics.cpp").read_text()
for name in ("send_ap_metrics_response", "create_ap_metrics_tlv", "create_ap_ext_metrics_tlv", "create_radio_metrics_tlv"):
    start = metrics.index("em_metrics_t::" + name + "(")
    end = metrics.index("\n}\n", start)
    body = metrics[start:end]
    assert "get_current_cmd" not in body, name + " still depends on borrowed command ownership"
    assert "const em_cmd_ap_metrics_rprt_params_t &params" in body
print("PASS all AP metrics builders use explicit event-owned parameters")
