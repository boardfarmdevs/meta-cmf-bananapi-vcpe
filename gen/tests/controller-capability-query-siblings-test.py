#!/usr/bin/env python3
"""A renewed radio's AP Capability Query does not wait for configured siblings.

Takes the fully patched unified-wifi-mesh source tree, extracts the controller's
ap_cap_query_pending branch and compiles it against a small model of an agent's radios.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("source_root", type=Path)
args = parser.parse_args()
source = (args.source_root / "src/em/capability/em_capability.cpp").read_text()
method = source.split("void em_capability_t::process_ctrl_state()", 1)[1].split("\n}\n", 1)[0]
branch = re.search(r"        case em_state_ctrl_ap_cap_query_pending:\s*\{.*?\n            \}\n            break;", method, re.S)
assert branch, "the controller must handle ap_cap_query_pending in process_ctrl_state"

program = r'''
#include <cassert>
#include <cstddef>
#include <string>
#include <vector>
#define em_printfout(...) ((void)0)
enum {
    em_state_ctrl_unconfigured = 0x100,
    em_state_ctrl_wsc_m1_pending,
    em_state_ctrl_wsc_m2_sent,
    em_state_ctrl_topo_sync_pending,
    em_state_ctrl_topo_synchronized,
    em_state_ctrl_ap_cap_query_pending,
    em_state_ctrl_ap_cap_report_received,
    em_state_ctrl_configured,
    em_state_ctrl_misconfigured
};
namespace util { std::string mac_to_string(const unsigned char *) { return ""; } }
struct dm_easy_mesh_t { unsigned char *get_agent_al_interface_mac() { return NULL; } };
struct em_t;
struct em_mgr_t {
    std::vector<em_t *> radios;
    void get_all_em_for_al_mac(unsigned char *, std::vector<em_t *> &out) { out = radios; }
};
struct em_capability_t {
    int state = em_state_ctrl_configured;
    int queries = 0;
    em_mgr_t *manager = NULL;
    dm_easy_mesh_t model;
    int get_state() { return state; }
    em_mgr_t *get_mgr() { return manager; }
    dm_easy_mesh_t *get_data_model() { return &model; }
    unsigned char *get_radio_interface_mac() { return NULL; }
    void send_ap_cap_query_msg() { queries++; }
    void process_ctrl_state();
};
struct em_t : em_capability_t {};
void em_capability_t::process_ctrl_state()
{
    switch (get_state()) {
''' + branch.group() + r'''
        default:
            break;
    }
}
static int tick(em_t *radios, int count, const int *states)
{
    em_mgr_t manager;
    int sent = 0;
    for (int i = 0; i < count; i++) {
        radios[i] = em_t();
        radios[i].state = states[i];
        radios[i].manager = &manager;
        manager.radios.push_back(&radios[i]);
    }
    for (int i = 0; i < count; i++) radios[i].process_ctrl_state();
    for (int i = 0; i < count; i++) sent += radios[i].queries;
    return sent;
}
int main()
{
    em_t radios[3];
    // one radio renewed alone: it sends, whichever its place among the agent's radios
    const int renewed_first[] = {em_state_ctrl_ap_cap_query_pending, em_state_ctrl_configured, em_state_ctrl_configured};
    assert(tick(radios, 3, renewed_first) == 1 && radios[0].queries == 1);
    const int renewed_last[] = {em_state_ctrl_configured, em_state_ctrl_configured, em_state_ctrl_ap_cap_query_pending};
    assert(tick(radios, 3, renewed_last) == 1 && radios[2].queries == 1);
    // a sibling about to be renewed does not hold it either
    const int beside_misconfigured[] = {em_state_ctrl_misconfigured, em_state_ctrl_ap_cap_query_pending, em_state_ctrl_configured};
    assert(tick(radios, 3, beside_misconfigured) == 1 && radios[1].queries == 1);
    // a sibling still onboarding holds the query: one report then serves both
    const int sibling_onboarding[] = {em_state_ctrl_ap_cap_query_pending, em_state_ctrl_topo_sync_pending, em_state_ctrl_configured};
    assert(tick(radios, 3, sibling_onboarding) == 0);
    const int sibling_synchronized[] = {em_state_ctrl_topo_synchronized, em_state_ctrl_ap_cap_query_pending, em_state_ctrl_configured};
    assert(tick(radios, 3, sibling_synchronized) == 0);
    // first onboarding: every radio waits, one query for the agent
    const int all_waiting[] = {em_state_ctrl_ap_cap_query_pending, em_state_ctrl_ap_cap_query_pending, em_state_ctrl_ap_cap_query_pending};
    assert(tick(radios, 3, all_waiting) == 1 && radios[0].queries == 1);
    // nothing waits: nothing is sent
    const int all_configured[] = {em_state_ctrl_configured, em_state_ctrl_configured, em_state_ctrl_configured};
    assert(tick(radios, 3, all_configured) == 0);
    return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / "test.cpp").write_text(program)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "test.cpp", "-o", "test"],
                   cwd=path, check=True)
    subprocess.run([str(path / "test")], check=True)
print("PASS: a renewed radio sends its AP Capability Query beside configured siblings; "
      "a sibling still onboarding holds it")
