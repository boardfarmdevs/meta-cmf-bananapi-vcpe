"""Compile native admission/quiescence with hwsim hostapd/kernel fixtures."""

import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    arguments = parser.parse_args()
    source = arguments.source / "src" if (arguments.source / "src").is_dir() else arguments.source
    core = (source / "wifi_hal.c").read_text()
    start = core.index("static pthread_mutex_t backhaul_root_lock")
    end = core.index("\nINT wifi_hal_connect(", start)
    production = core[start:end]
    netlink = (source / "wifi_hal_nl80211.c").read_text()
    for method, boundary in (("wifi_drv_sta_add", "vap = &interface->vap_info"),
                             ("wifi_drv_sta_set_flags", "if (!(msg = nl80211_drv_cmd_msg")):
        start = netlink.index("int " + method + "(")
        body = netlink[start:netlink.index("\n}", start)]
        assert 0 <= body.find("wifi_hal_backhaul_root_blocked(interface)") < body.index(boundary), method
        assert "return -EPERM;" in body[:body.index(boundary)], method
    program = r'''
#include <assert.h>
#include <errno.h>
#include <net/if.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>
#define HWSIM_RADIO 1
#define RETURN_OK 0
#define RETURN_ERR -1
#define WLAN_REASON_PREV_AUTH_NOT_VALID 2
#define wifi_vap_mode_ap 0
#define wifi_vap_mode_sta 1
#define wifi_hal_error_print(...) ((void)0)
#define wifi_hal_info_print(...) ((void)0)
#define hash_map_foreach(map, item) for (unsigned int slot=0; slot<2 && ((item)=&(map)[slot]); ++slot)
typedef int INT;
typedef unsigned char mac_address_t[6];
struct sta_info { unsigned char addr[6]; struct sta_info *next; };
struct hostapd_data { void *conf; struct sta_info *sta_list; int kernel_peers, flushes; bool fail, started; };
typedef struct {
    int vap_mode, vap_index;
    union { struct { bool enabled; } bss_info; struct { mac_address_t mac; } sta_info; } u;
} vap_info_t;
typedef struct {
    vap_info_t vap_info;
    char name[16];
    bool mesh, vap_initialized, bss_started;
    int beacon_set, stops, starts;
    union { struct { struct hostapd_data hapd; } ap; struct { struct { mac_address_t bssid; } backhaul; } sta; } u;
} wifi_interface_info_t;
typedef struct { wifi_interface_info_t *interface_map; bool configured; struct { bool enable; } oper_param; } wifi_radio_info_t;
static struct { unsigned int num_radios; pthread_mutex_t hapd_lock; } g_wifi_hal = {1, PTHREAD_MUTEX_INITIALIZER};
static wifi_interface_info_t interfaces[2], station;
static wifi_radio_info_t radio = {interfaces, true, {true}};
static int missing_radio, disconnects, deauths, down_interface;
static wifi_radio_info_t *get_radio_by_rdk_index(unsigned int index) { return index || missing_radio ? NULL : &radio; }
static wifi_interface_info_t *get_interface_by_vap_index(int index) { return index == 7 ? &station : NULL; }
static bool is_backhaul_interface(wifi_interface_info_t *interface) { return interface->mesh; }
static bool is_wifi_hal_vap_mesh_sta(int index) { return index == 7; }
static int wifi_hal_disconnect(int index) { assert(index==7); disconnects++; return 0; }
static int hostapd_drv_sta_deauth(struct hostapd_data *hapd, const unsigned char *address, int reason) {
    assert(hapd && address && reason == WLAN_REASON_PREV_AUTH_NOT_VALID);
    assert(pthread_mutex_trylock(&g_wifi_hal.hapd_lock) == EBUSY);
    deauths++;
    return 0;
}
static void ap_free_sta(struct hostapd_data *hapd, struct sta_info *child) { assert(hapd->sta_list==child); hapd->sta_list=child->next; free(child); }
static int hostapd_flush(struct hostapd_data *hapd) {
    assert(pthread_mutex_trylock(&g_wifi_hal.hapd_lock) == EBUSY);
    hapd->flushes++;
    if (hapd->fail) return -1;
    hapd->kernel_peers=0;
    return 0;
}
static int reload_interface(wifi_interface_info_t *interface) { interface->u.ap.hapd.kernel_peers=0; interface->u.ap.hapd.started=false; return 0; }
static int nl80211_enable_ap(wifi_interface_info_t *interface, bool enabled) { assert(!enabled); interface->stops++; return 0; }
static int nl80211_interface_enable(const char *name, bool enabled) { (void)name; down_interface=!enabled; return 0; }
static int get_vap_state(const char *name, short *flags) { (void)name; *flags=down_interface ? 0 : IFF_UP; return 0; }
static int restart_interface(wifi_interface_info_t *interface) { assert(!interface->u.ap.hapd.started); interface->u.ap.hapd.started=true; interface->starts++; interface->bss_started=true; interface->beacon_set=1; return 0; }
PRODUCTION
static void add_child(wifi_interface_info_t *interface) {
    struct hostapd_data *hapd=&interface->u.ap.hapd;
    struct sta_info *child=calloc(1, sizeof(*child)); assert(child);
    child->next=hapd->sta_list; hapd->sta_list=child; hapd->kernel_peers++;
}
int main(void) {
    for (int index=0; index<2; index++) {
        interfaces[index].mesh=index==0;
        interfaces[index].vap_initialized=true;
        interfaces[index].bss_started=true;
        interfaces[index].beacon_set=1;
        interfaces[index].vap_info.u.bss_info.enabled=true;
        interfaces[index].u.ap.hapd.conf=&radio;
        interfaces[index].u.ap.hapd.started=true;
        snprintf(interfaces[index].name, sizeof(interfaces[index].name), "ap%d", index);
        add_child(&interfaces[index]);
    }
    station.vap_info.vap_mode=wifi_vap_mode_sta; station.vap_info.vap_index=7;
    station.vap_info.u.sta_info.mac[0]=2; station.u.sta.backhaul.bssid[0]=2;
    assert(!wifi_hal_backhaul_root_blocked(&interfaces[0]));
    assert(wifi_hal_backhaul_root_close(7)==0);
    assert(wifi_hal_backhaul_root_blocked(&interfaces[0]));
    assert(!wifi_hal_backhaul_root_blocked(&interfaces[1]));
    assert(!wifi_hal_backhaul_beacon_blocked(&interfaces[0]));
    assert(!wifi_hal_backhaul_root_name_blocked("ap0"));
    assert(interfaces[0].bss_started && interfaces[0].beacon_set && interfaces[0].stops==0);
    assert(interfaces[0].u.ap.hapd.kernel_peers==0 && deauths==1);
    assert(interfaces[1].u.ap.hapd.kernel_peers==1 && interfaces[1].u.ap.hapd.flushes==0);
    unsigned char state[22], outdated[22];
    wifi_hal_backhaul_root_link(&station, true);
    assert(wifi_hal_backhaul_root_state(7, state)==0);
    memcpy(outdated,state,sizeof(state)); outdated[0]^=1;
    assert(wifi_hal_backhaul_root_admit(7,outdated)==-1);
    assert(wifi_hal_backhaul_root_admit(7,state)==0);
    assert(!wifi_hal_backhaul_root_blocked(&interfaces[0]) && interfaces[0].starts==0);
    add_child(&interfaces[0]);
    wifi_hal_backhaul_root_link(&station,false);
    assert(wifi_hal_backhaul_root_loss(7)==0);
    assert(wifi_hal_backhaul_root_admit(7,state)==-1);
    assert(interfaces[0].bss_started && !interfaces[0].u.ap.hapd.kernel_peers && deauths==2);
    interfaces[0].u.ap.hapd.fail=true;
    down_interface=1;
    int flushes=interfaces[0].u.ap.hapd.flushes;
    assert(wifi_hal_backhaul_root_loss(7)==0);
    assert(interfaces[0].u.ap.hapd.flushes==flushes);
    assert(!interfaces[0].bss_started && !interfaces[0].beacon_set);
    down_interface=0;
    assert(wifi_hal_backhaul_root_loss(7)==-1);
    assert(!interfaces[0].bss_started && interfaces[0].stops==1);
    interfaces[0].u.ap.hapd.fail=false;
    wifi_hal_backhaul_root_link(&station,true);
    assert(wifi_hal_backhaul_root_state(7,state)==0 && wifi_hal_backhaul_root_admit(7,state)==0);
    assert(interfaces[0].starts==1);
    assert(wifi_hal_backhaul_root_revoke(7,state)==0 && disconnects==1);
    assert(interfaces[0].bss_started && wifi_hal_backhaul_root_blocked(&interfaces[0]));
    interfaces[0].bss_started=false;
    add_child(&interfaces[0]);
    assert(backhaul_root_quiesce()==0 && interfaces[0].u.ap.hapd.kernel_peers==0);
    wifi_hal_backhaul_root_link(&station,true);
    assert(wifi_hal_backhaul_root_state(7,state)==0 && wifi_hal_backhaul_root_admit(7,state)==0);
    assert(interfaces[0].starts==2 && interfaces[0].u.ap.hapd.started);
    missing_radio=1; assert(backhaul_root_quiesce()==-1);
    ap_free_sta(&interfaces[1].u.ap.hapd,interfaces[1].u.ap.hapd.sta_list);
    puts("PASS: native hwsim beacon/admission separation, child flush, stale proof, recovery and fail-closed fallback");
}
'''.replace("PRODUCTION", production)
    with tempfile.TemporaryDirectory(prefix="hal-backhaul-beacon-") as temporary:
        binary = Path(temporary) / "test"
        subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-pthread", "-x", "c", "-", "-o", str(binary)], input=program, text=True, check=True)
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
