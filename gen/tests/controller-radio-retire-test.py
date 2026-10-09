#!/usr/bin/env python3
"""A radio its agent no longer has is retired by the controller (0253).

Takes the fully patched unified-wifi-mesh source tree.
- The Topology Response's AP Operational BSS TLV notes the radios the agent lists, on the
  controller only and only when the list fits the model's radios; the controller's manager
  retires the stale ones before the dirty models are written, in this order: out of every
  command, the em out of the map (its thread told to exit, the object kept), then the model's
  and the database's rows.
- Compiled from the source with AddressSanitizer against a model of the agent's data model:
  a radio left out of EM_RADIO_UNREPORTED_RESPONSES responses in a row becomes stale, once; one
  listed again starts afresh; retiring removes its BSS rows (each recorded for the database, as
  0251 does), its operating classes and the radio, the capabilities staying with their radios;
  the other radio and its rows are untouched.
- Compiled from the source against a model of the orchestrator's queues: a retired radio leaves
  every pending command (one left with no radio goes) and is cancelled in the active ones.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("source_root", type=Path)
args = parser.parse_args()
root = args.source_root


def function(text, signature):
    start = text.index(signature)
    return text[start:text.index("\n}\n", start) + 3]


configuration = (root / "src/em/config/em_configuration.cpp").read_text()
handler = function(configuration, "int em_configuration_t::handle_ap_operational_bss(")
hook = handler.index("note_reported_radios(")
assert "get_service_type() == em_service_type_ctrl" in handler[:hook], "noted on the controller only"
assert "radios_num <= EM_MAX_BANDS" in handler[:hook], "a list longer than the model's radios is not counted"
assert handler.index("its radios and BSSes do not fit") < hook, "noted only after the TLV's length is checked"

ctrl = (root / "src/ctrl/em_ctrl.cpp").read_text()
dirty = function(ctrl, "void em_ctrl_t::handle_dirty_dm()")
assert dirty.index("retire_stale_radios();") < dirty.index("m_data_model.handle_dirty_dm();"), \
    "retired before the dirty models are written"
retire = function(ctrl, "void em_ctrl_t::retire_stale_radios()")
order = [retire.index(step) for step in ("remove_em_from_commands(", "retire_node(", "m_data_model.retire_radio(")]
assert order == sorted(order), "commands, then the map, then the model"

mgr = (root / "src/em/em_mgr.cpp").read_text()
node = function(mgr, "em_t *em_mgr_t::retire_node(")
assert "hash_map_remove(m_em_map" in node and "em->stop();" in node and "delete em" not in node, \
    "the em out of the map, its thread told to exit, the object kept"

model_source = (root / "src/dm/dm_easy_mesh.cpp").read_text()
model_methods = "\n".join(function(model_source, signature) for signature in (
    "unsigned int dm_easy_mesh_t::note_reported_radios(",
    "bool dm_easy_mesh_t::take_stale_radio(",
    "void dm_easy_mesh_t::retire_radio("))
grace = int(re.search(r"#define EM_RADIO_UNREPORTED_RESPONSES (\d+)", (root / "inc/em_base.h").read_text()).group(1))

orch_source = (root / "src/orch/em_orch.cpp").read_text()
orch_method = function(orch_source, "void em_orch_t::remove_em_from_commands(")

model_program = r'''
#include <cassert>
#include <cstring>
#include <vector>
#define EM_MAX_BANDS 3
#define EM_MAX_BSSS 24
#define EM_MAX_OPCLASS 16
#define EM_RADIO_UNREPORTED_RESPONSES @GRACE@
typedef unsigned char mac_address_t[6];
enum em_haul_type_t { em_haul_type_fronthaul, em_haul_type_backhaul };
struct em_interface_t { mac_address_t mac; };
struct em_bss_info_t { em_interface_t bssid, ruid; em_haul_type_t haul_type; };
struct dm_bss_t { em_bss_info_t m_bss_info; };
struct dm_radio_t { struct { em_interface_t intf; int band; } m_radio_info; };
struct dm_radio_cap_t { struct { em_interface_t ruid; int tag; } m_radio_cap_info; };
struct dm_op_class_t { struct { struct { mac_address_t ruid; unsigned int op_class; } id; } m_op_class_info; };
struct dm_easy_mesh_t {
    unsigned int m_num_radios = 0;
    dm_radio_t m_radio[EM_MAX_BANDS];
    dm_radio_cap_t m_radio_cap[EM_MAX_BANDS];
    unsigned int m_num_unreported_radio = 0;
    struct { mac_address_t ruid; unsigned int responses; } m_unreported_radio[EM_MAX_BANDS];
    unsigned int m_num_stale_radio = 0;
    mac_address_t m_stale_radio[EM_MAX_BANDS];
    unsigned int m_num_bss = 0;
    dm_bss_t m_bss[EM_MAX_BSSS];
    unsigned int m_num_opclass = 0;
    dm_op_class_t m_op_class[EM_MAX_OPCLASS];
    std::vector<em_bss_info_t> removed;
    void remember_removed_bss(const em_bss_info_t *bss) { removed.push_back(*bss); }
    void remove_bss_by_index(unsigned int index)
    {
        assert(index < m_num_bss);
        for (unsigned int i = index; i + 1 < m_num_bss; i++) m_bss[i] = m_bss[i + 1];
        m_num_bss--;
    }
    unsigned int note_reported_radios(const mac_address_t *reported, unsigned int num_reported);
    bool take_stale_radio(mac_address_t ruid);
    void retire_radio(const unsigned char *ruid);
};
@METHODS@
static const mac_address_t RADIO_5 = {2, 0, 0, 0, 0x6e, 0}, RADIO_24 = {2, 0, 0, 0, 0x6c, 0};
static const mac_address_t BSS_5 = {0x72, 0, 0, 0, 0x6e, 0}, BSS_24 = {0x72, 0, 0, 0, 0x6c, 0};
static const mac_address_t FH_5 = {0x82, 0, 0, 0, 0x6e, 0};
static dm_easy_mesh_t agent()
{
    dm_easy_mesh_t dm;
    const unsigned char *radios[] = {RADIO_24, RADIO_5};
    for (int r = 0; r < 2; r++) {
        memcpy(dm.m_radio[r].m_radio_info.intf.mac, radios[r], 6);
        dm.m_radio[r].m_radio_info.band = r;
        memcpy(dm.m_radio_cap[r].m_radio_cap_info.ruid.mac, radios[r], 6);
        dm.m_radio_cap[r].m_radio_cap_info.tag = 100 + r;
        memcpy(dm.m_op_class[dm.m_num_opclass].m_op_class_info.id.ruid, radios[r], 6);
        dm.m_op_class[dm.m_num_opclass++].m_op_class_info.id.op_class = r ? 115 : 81;
    }
    dm.m_num_radios = 2;
    const unsigned char *bsses[][2] = {{BSS_24, RADIO_24}, {BSS_5, RADIO_5}, {FH_5, RADIO_5}};
    for (auto &b : bsses) {
        memcpy(dm.m_bss[dm.m_num_bss].m_bss_info.bssid.mac, b[0], 6);
        memcpy(dm.m_bss[dm.m_num_bss++].m_bss_info.ruid.mac, b[1], 6);
    }
    return dm;
}
int main()
{
    dm_easy_mesh_t dm = agent();
    mac_address_t only_5[1];
    memcpy(only_5[0], RADIO_5, 6);
    mac_address_t both[2];
    memcpy(both[0], RADIO_24, 6);
    memcpy(both[1], RADIO_5, 6);
    mac_address_t ruid;
    /* left out of fewer responses than the threshold, then listed again: nothing stale */
    for (unsigned int n = 1; n < EM_RADIO_UNREPORTED_RESPONSES; n++) assert(dm.note_reported_radios(only_5, 1) == 0);
    assert(dm.note_reported_radios(both, 2) == 0 && dm.m_num_unreported_radio == 0);
    /* left out again: it takes the whole threshold anew, and becomes stale once */
    for (unsigned int n = 1; n < EM_RADIO_UNREPORTED_RESPONSES; n++) assert(dm.note_reported_radios(only_5, 1) == 0);
    assert(dm.note_reported_radios(only_5, 1) == 1);
    assert(dm.note_reported_radios(only_5, 1) == 0 && dm.m_num_stale_radio == 1);
    assert(dm.take_stale_radio(ruid) && memcmp(ruid, RADIO_24, 6) == 0 && !dm.take_stale_radio(ruid));
    /* retired: its BSS row (recorded), its operating class and the radio; the 5 GHz radio keeps its own */
    dm.retire_radio(RADIO_24);
    assert(dm.m_num_radios == 1 && memcmp(dm.m_radio[0].m_radio_info.intf.mac, RADIO_5, 6) == 0);
    assert(memcmp(dm.m_radio_cap[0].m_radio_cap_info.ruid.mac, RADIO_5, 6) == 0 && dm.m_radio_cap[0].m_radio_cap_info.tag == 101);
    assert(dm.m_num_opclass == 1 && dm.m_op_class[0].m_op_class_info.id.op_class == 115);
    assert(dm.m_num_bss == 2 && dm.removed.size() == 1 && memcmp(dm.removed[0].bssid.mac, BSS_24, 6) == 0);
    for (unsigned int i = 0; i < dm.m_num_bss; i++) assert(memcmp(dm.m_bss[i].m_bss_info.ruid.mac, RADIO_5, 6) == 0);
    assert(dm.m_num_unreported_radio == 0);
    /* the agent lists its one radio: nothing more to retire */
    for (unsigned int n = 0; n < 2 * EM_RADIO_UNREPORTED_RESPONSES; n++) assert(dm.note_reported_radios(only_5, 1) == 0);
    /* an agent that lists none of its radios: every one becomes stale, each once */
    dm_easy_mesh_t silent = agent();
    unsigned int stale = 0;
    for (unsigned int n = 0; n < 2 * EM_RADIO_UNREPORTED_RESPONSES; n++) stale += silent.note_reported_radios(nullptr, 0);
    assert(stale == 2 && silent.m_num_stale_radio == 2);
    return 0;
}
'''.replace("@METHODS@", model_methods).replace("@GRACE@", str(grace))

orch_program = r'''
#include <cassert>
#include <cstring>
#include <mutex>
#include <vector>
typedef unsigned char mac_address_t[6];
typedef std::vector<void *> queue_t;
static unsigned int queue_count(queue_t *q) { return static_cast<unsigned int>(q->size()); }
static void *queue_peek(queue_t *q, unsigned int i) { return (*q)[i]; }
static void *queue_remove(queue_t *q, unsigned int i) { void *v = (*q)[i]; q->erase(q->begin() + i); return v; }
enum em_orch_state_t { em_orch_state_idle, em_orch_state_pending, em_orch_state_progress, em_orch_state_cancel };
struct em_t {
    mac_address_t mac;
    em_orch_state_t orch = em_orch_state_progress;
    unsigned char *get_radio_interface_mac() { return mac; }
    void set_orch_state(em_orch_state_t state) { orch = state; }
};
struct em_cmd_t { queue_t candidates; queue_t *m_em_candidates = &candidates; bool destroyed = false; };
struct em_orch_t {
    queue_t pending, active;
    queue_t *m_pending = &pending, *m_active = &active;
    std::recursive_mutex mutex;
    int popped = 0;
    std::vector<em_cmd_t *> destroyed;
    std::unique_lock<std::recursive_mutex> lock_commands() { return std::unique_lock<std::recursive_mutex>(mutex); }
    void pop_stats(em_cmd_t *) { popped++; }
    void destroy_command(em_cmd_t *cmd) { cmd->destroyed = true; destroyed.push_back(cmd); }
    void remove_em_from_commands(const unsigned char *radio_mac);
};
@METHOD@
int main()
{
    em_t gone{{2, 0, 0, 0, 0x6c, 0}}, kept{{2, 0, 0, 0, 0x6e, 0}};
    em_cmd_t only_gone, both, active_both;
    only_gone.candidates = {&gone};
    both.candidates = {&gone, &kept};
    active_both.candidates = {&kept, &gone};
    em_orch_t orch;
    orch.pending = {&only_gone, &both};
    orch.active = {&active_both};
    orch.remove_em_from_commands(gone.mac);
    assert(orch.pending.size() == 1 && orch.pending[0] == &both && both.candidates.size() == 1 && both.candidates[0] == &kept);
    assert(only_gone.destroyed && orch.popped == 1 && !both.destroyed);
    assert(orch.active.size() == 1 && active_both.candidates.size() == 2);
    assert(gone.orch == em_orch_state_cancel && kept.orch == em_orch_state_progress);
    return 0;
}
'''.replace("@METHOD@", orch_method)

with tempfile.TemporaryDirectory() as tmp:
    for name, program in (("model", model_program), ("orch", orch_program)):
        src, exe = Path(tmp) / f"{name}.cpp", Path(tmp) / name
        src.write_text(program)
        subprocess.run(["g++", "-std=c++17", "-O0", "-g", "-Wall", "-Wextra", "-Wno-unused-parameter",
                        "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-o", str(exe), str(src)],
                       check=True)
        subprocess.run([str(exe)], check=True)
print("controller radio retirement: ok")
