"""The EM app reads a radio's transmit power again until it has a reading, and when it changes
(OneWifi 0045). It read the HAL once, at the monitor's start (0044): a radio whose interface was
not on a channel yet had no reading, and its agent's Operating Channel Report said 0 dBm (every
extender of the RDK lab, 10 October).

Compiled from 0045's own lines and 0043's reading table (its measured flag: a reading recorded by
the HAL's process is not overwritten by a decoded one), with a scripted HAL: a radio not up at
the start is read on the 5 s tick until it has a reading; once all have one, every 60 s; a
reading taken or changed asks for the radio subdoc again; a radio that reads none keeps its
last; a channel change reads its radio at once; the first reading and the first miss are logged
once each."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

PATCHES = Path(__file__).resolve().parents[2] / "recipes-ccsp/ccsp/ccsp-one-wifi"
P0043 = "0043-webconfig-radio-transmit-power-reading-in-dbm.patch"
P0045 = "0045-em-app-reads-the-radio-transmit-power-again-until-it-has-one.patch"


def added_file(patch, path):
    text = (PATCHES / patch).read_text()
    header = re.search(rf"^\+\+\+ b/{re.escape(path)}(\t.*)?$", text, re.M)
    body = text[header.end():].split("\n", 1)[1]
    following = re.search(r"^(diff --git|--- )", body, re.M)
    lines = (body if following is None else body[:following.start()]).splitlines()
    return "\n".join(line[1:] for line in lines if line.startswith("+"))


def test_the_patch_is_applied_after_0044():
    recipe = (PATCHES.parent / "ccsp-one-wifi.bbappend").read_text()
    assert recipe.index("d.getVar('WIFI_EM_TX_POWER_PERCENT_PATCH')") < recipe.index("d.getVar('WIFI_EM_TX_POWER_REREAD_PATCH')")
    assert 'do_patch[file-checksums] += "${WIFI_EM_TX_POWER_REREAD_PATCH}:True"' in recipe
    subprocess.run(["git", "apply", "--numstat", str(PATCHES / P0045)], check=True, capture_output=True)


def test_the_channel_change_reads_its_radio():
    em = added_file(P0045, "source/apps/em/wifi_em.c")
    assert "case wifi_event_hal_channel_change:" in em
    assert 'em_tx_power_read(((wifi_channel_change_event_t *)data)->radioIndex, "channel change")' in em
    assert "scheduler_add_timer_task(app->ctrl->sched, FALSE, &em_tx_power_sched_id, em_tx_power_tick," in em


@pytest.mark.skipif(shutil.which("gcc") is None, reason="C compiler required")
def test_a_radio_is_read_until_it_has_a_reading_and_when_it_changes(tmp_path):
    em = added_file(P0045, "source/apps/em/wifi_em.c")
    block = em[em.index("#define EM_TX_POWER_TICK_MSEC"):]
    block = block[:block.index("\n}\n", block.index("static int em_tx_power_tick(")) + 3]
    table = added_file(P0043, "source/webconfig/wifi_webconfig.c")
    table = table[table.index("// The radios' transmit power readings"):]
    (tmp_path / "model.c").write_text(r'''#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#define MAX_NUM_RADIOS 3
#define RETURN_OK 0
#define TIMER_TASK_COMPLETE 0
#define WIFI_EM 0
#define wifi_util_info_print(module, ...) printf(__VA_ARGS__)
typedef int INT;
typedef unsigned long ULONG;
enum { ctrl_webconfig_state_radio_cfg_rsp_pending = 0x10 };
static struct { struct { unsigned int webconfig_state; } ctrl; } mgr;
#define get_wifimgr_obj() (&mgr)
static ULONG hal[MAX_NUM_RADIOS];
static INT wifi_hal_getRadioTransmitPower(INT radio, ULONG *power) { *power = hal[radio]; return RETURN_OK; }
static unsigned int getNumberRadios(void) { return MAX_NUM_RADIOS; }
''' + table + "\n" + block + r'''
static void state(const char *step)
{
    bool m[3];
    int d[3];
    for (int i = 0; i < 3; i++) d[i] = webconfig_get_radio_tx_power_dbm(i, &m[i]);
    printf("STATE %s %d%c %d%c %d%c all=%d push=%d\n", step, d[0], m[0] ? 'm' : '-', d[1], m[1] ? 'm' : '-',
        d[2], m[2] ? 'm' : '-', em_tx_power_all_read, mgr.ctrl.webconfig_state != 0);
    mgr.ctrl.webconfig_state = 0;
}

int main(void)
{
    (void)em_tx_power_sched_id;                        // the monitor start's timer, not modelled
    hal[0] = 20; hal[1] = 0; hal[2] = 33;              // the 5 GHz radio not up yet
    em_tx_power_read_all("monitor start"); state("start");
    em_tx_power_tick(NULL); state("tick1");            // still none: no new log line
    hal[1] = 30;
    em_tx_power_tick(NULL); state("tick2");            // the 5 GHz reading arrives
    hal[0] = 18;
    for (int i = 3; i < 12; i++) em_tx_power_tick(NULL);
    state("tick11");                                   // all read: nothing until the 12th tick
    em_tx_power_tick(NULL); state("tick12");           // the refresh sees 20 -> 18
    hal[1] = 0;                                        // the radio goes down: keeps its 30
    for (int i = 13; i <= 24; i++) em_tx_power_tick(NULL);
    state("down");
    webconfig_set_radio_tx_power_dbm(2, 7, false);     // a decoded subdoc does not overwrite
    hal[2] = 30;
    em_tx_power_read(2, "channel change"); state("channel");
    return 0;
}
''')
    subprocess.run(["gcc", "-Wall", "-Werror", "-o", str(tmp_path / "model"), str(tmp_path / "model.c"), "-lpthread"],
                   check=True)
    out = subprocess.run([str(tmp_path / "model")], check=True, capture_output=True, text=True).stdout
    states = dict(line.split(" ", 2)[1:] for line in out.splitlines() if line.startswith("STATE "))
    assert states["start"] == "20m 0- 33m all=0 push=1"
    assert states["tick1"] == "20m 0- 33m all=0 push=0"
    assert states["tick2"] == "20m 30m 33m all=1 push=1"
    assert states["tick11"] == "20m 30m 33m all=1 push=0"
    assert states["tick12"] == "18m 30m 33m all=1 push=1"
    assert states["down"] == "18m 30m 33m all=1 push=0"
    assert states["channel"] == "18m 30m 30m all=1 push=1"
    logged = [line for line in out.splitlines() if not line.startswith("STATE ")]
    assert sum("radio_index=1 no transmit power reading yet (monitor start" in line for line in logged) == 1
    assert not any("no transmit power reading yet (retry" in line for line in logged)
    assert sum("radio_index=1 first transmit power reading 30 dBm (retry, uptime" in line for line in logged) == 1
    assert any("radio_index=0 transmit power reading 20 -> 18 dBm (refresh)" in line for line in logged)
    assert any("radio_index=2 transmit power reading 33 -> 30 dBm (channel change)" in line for line in logged)
