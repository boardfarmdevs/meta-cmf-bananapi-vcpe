#include <errno.h>
#include <net/if.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/types.h>

#define RETURN_OK 0
#define RETURN_ERR -1
#define WIFI_HAL_INVALID_ARGUMENTS -4
#define wifi_vap_mode_ap 0
#define wifi_vap_mode_sta 1
#define NULL_PTR_ASSERT(value) do { if ((value) == NULL) return RETURN_ERR; } while (0)
#define wifi_hal_error_print(...) fixture_log(__VA_ARGS__)
#define wifi_hal_info_print(...) fixture_log(__VA_ARGS__)
#define wifi_hal_dbg_print(...) fixture_log(__VA_ARGS__)
#define getrandom fixture_getrandom
#define socket fixture_socket
#define ioctl fixture_ioctl
#define close fixture_close
#define hash_map_foreach(map, item) \
    for (size_t slot = 0; (map) != NULL && slot < (map)->count && (((item) = (map)->items[slot]) != NULL); ++slot)

typedef int INT;
typedef unsigned char mac_address_t[6];
typedef unsigned char bssid_t[6];
typedef struct { void *items[16]; size_t count; } hash_map_t;
typedef struct { bssid_t bssid; char ssid[32]; int rssi; unsigned int freq; } wifi_bss_info_t;
typedef struct {
    unsigned int vap_index, radio_index;
    int vap_mode;
    union {
        struct { mac_address_t mac; char ssid[32]; } sta_info;
        struct { bool enabled; } bss_info;
    } u;
} wifi_vap_info_t;
typedef struct {
    wifi_vap_info_t vap_info;
    char name[32];
    bool vap_initialized, bss_started, mesh, kernel_ap;
    int beacon_set;
    short kernel_flags;
    unsigned int downstream;
    union {
        struct { wifi_bss_info_t backhaul; } sta;
        struct { struct { void *conf; } hapd; } ap;
    } u;
    pthread_mutex_t scan_info_mutex;
    hash_map_t *scan_info_map;
} wifi_interface_info_t;
typedef struct { hash_map_t *interface_map; bool configured; struct { bool enable; } oper_param; } wifi_radio_info_t;
static struct { unsigned int num_radios; } g_wifi_hal;
static wifi_radio_info_t radios[3];
static hash_map_t maps[3], scans;
static wifi_interface_info_t interfaces[13];
static wifi_bss_info_t scan_rows[3];
static int missing_radio = -1, stop_failure = -1, down_failure = -1;
static int socket_failure, initial_read_failure = -1, readback_failure = -1, sticky_up = -1;
static int reload_failure = -1, restart_failure = -1, reopen_up_failure = -1;
static int rng_mode, connect_failure, disconnect_during_reopen = -1;
static int connect_calls, unsafe_connect, kernel_calls_while_locked;
static int disconnect_calls, disconnect_failure, reconnect_during_reload = -1;
static int stops[13], downs[13], reads[13], reloads[13], starts[13], ups[13];
static int ordering[256], order_count;
static const int station_index = 7;
static pthread_mutex_t backhaul_root_lock;

static void fixture_log(const char *format, ...);
static ssize_t fixture_getrandom(void *buffer, size_t size, unsigned int flags);
static int fixture_socket(int domain, int type, int protocol);
static int fixture_ioctl(int fd, unsigned long request, struct ifreq *configuration);
static int fixture_close(int fd);
static int get_vap_state(const char *name, short *flags);
static wifi_interface_info_t *get_interface_by_vap_index(INT index);
static wifi_radio_info_t *get_radio_by_rdk_index(unsigned int index);
static bool is_backhaul_interface(wifi_interface_info_t *interface);
static bool is_wifi_hal_vap_mesh_sta(INT index);
static int nl80211_enable_ap(wifi_interface_info_t *interface, bool enable);
static int nl80211_interface_enable(const char *ifname, bool enable);
static int reload_interface(wifi_interface_info_t *interface);
static int restart_interface(wifi_interface_info_t *interface);
static int nl80211_connect_sta(wifi_interface_info_t *interface);
static int nl80211_disconnect_sta(wifi_interface_info_t *interface);
INT wifi_hal_disconnect(INT ap_index);
static void *hash_map_get_first(hash_map_t *map);
static void *hash_map_get_next(hash_map_t *map, void *current);
static const char *get_vap_ssid(wifi_vap_info_t *vap);

PRODUCTION_FUNCTIONS

static void fixture_log(const char *format, ...)
{
    (void)format;
}

static void event(int value)
{
    if (order_count < (int)(sizeof(ordering) / sizeof(ordering[0]))) ordering[order_count++] = value;
    if (pthread_mutex_trylock(&backhaul_root_lock) == 0) pthread_mutex_unlock(&backhaul_root_lock);
    else ++kernel_calls_while_locked;
}

static wifi_interface_info_t *by_name(const char *name)
{
    for (size_t index = 0; index < 13; ++index) {
        if (strcmp(interfaces[index].name, name) == 0) return &interfaces[index];
    }
    return NULL;
}

static ssize_t fixture_getrandom(void *buffer, size_t size, unsigned int flags)
{
    (void)flags;
    uint64_t value = rng_mode == 3 ? 0 : 0x2468ace02468ace0ULL;
    if (rng_mode == 1) return -1;
    if (size != sizeof(value)) return -1;
    memcpy(buffer, &value, size);
    return rng_mode == 2 ? (ssize_t)size - 1 : (ssize_t)size;
}

static int fixture_socket(int domain, int type, int protocol)
{
    (void)domain;
    (void)type;
    (void)protocol;
    return socket_failure ? -1 : 73;
}

static int fixture_ioctl(int fd, unsigned long request, struct ifreq *configuration)
{
    (void)fd;
    if (request != SIOCSIFFLAGS) return -1;
    wifi_interface_info_t *interface = by_name(configuration->ifr_name);
    if (interface == NULL) return -1;
    int index = (int)interface->vap_info.vap_index;
    bool enable = (configuration->ifr_flags & IFF_UP) != 0;
    event((enable ? 400 : 100) + index);
    if (enable) {
        ++ups[index];
        if (reopen_up_failure == index) return -1;
    } else {
        ++downs[index];
        if (down_failure == index) return -1;
    }
    if (sticky_up != index) interface->kernel_flags = configuration->ifr_flags;
    if (!(interface->kernel_flags & IFF_UP)) {
        interface->kernel_ap = false;
        interface->downstream = 0;
    }
    return 0;
}

static int fixture_close(int fd)
{
    (void)fd;
    return 0;
}

static int get_vap_state(const char *name, short *flags)
{
    wifi_interface_info_t *interface = by_name(name);
    if (interface == NULL) return -1;
    int index = (int)interface->vap_info.vap_index;
    ++reads[index];
    event(200 + index);
    if (initial_read_failure == index || (readback_failure == index && downs[index] > 0)) return -1;
    *flags = interface->kernel_flags;
    return 0;
}

static wifi_interface_info_t *get_interface_by_vap_index(INT index)
{
    for (unsigned int radio = 0; radio < g_wifi_hal.num_radios && radio < 3; ++radio) {
        for (size_t slot = 0; slot < maps[radio].count; ++slot) {
            wifi_interface_info_t *interface = maps[radio].items[slot];
            if ((int)interface->vap_info.vap_index == index) return interface;
        }
    }
    return NULL;
}

static wifi_radio_info_t *get_radio_by_rdk_index(unsigned int index)
{
    return index >= g_wifi_hal.num_radios || (int)index == missing_radio ? NULL : &radios[index];
}

static bool is_backhaul_interface(wifi_interface_info_t *interface)
{
    return interface->mesh && interface->vap_info.vap_mode == wifi_vap_mode_ap;
}

static bool is_wifi_hal_vap_mesh_sta(INT index)
{
    wifi_interface_info_t *interface = get_interface_by_vap_index(index);
    return interface != NULL && interface->mesh && interface->vap_info.vap_mode == wifi_vap_mode_sta;
}

static int nl80211_enable_ap(wifi_interface_info_t *interface, bool enable)
{
    int index = (int)interface->vap_info.vap_index;
    event(index);
    if (enable) return -1;
    ++stops[index];
    if (stop_failure == index) return -1;
    interface->kernel_ap = false;
    interface->downstream = 0;
    return 0;
}

static int reload_interface(wifi_interface_info_t *interface)
{
    int index = (int)interface->vap_info.vap_index;
    ++reloads[index];
    event(300 + index);
    if (reconnect_during_reload == index) {
        reconnect_during_reload = -1;
        interfaces[station_index].u.sta.backhaul.bssid[5] ^= 1;
        wifi_hal_backhaul_root_link(&interfaces[station_index], true);
    }
    return reload_failure == index ? -1 : 0;
}

static int nl80211_disconnect_sta(wifi_interface_info_t *interface)
{
    if ((int)interface->vap_info.vap_index != station_index) return -1;
    event(1100);
    ++disconnect_calls;
    return disconnect_failure ? -1 : 0;
}

static int restart_interface(wifi_interface_info_t *interface)
{
    int index = (int)interface->vap_info.vap_index;
    event(500 + index);
    ++starts[index];
    if (restart_failure == index) return -1;
    if (wifi_hal_backhaul_root_blocked(interface)) return 0;
    interface->bss_started = true;
    interface->kernel_ap = true;
    if (disconnect_during_reopen == index) {
        wifi_hal_backhaul_root_link(&interfaces[station_index], false);
    }
    return 0;
}

static bool all_down(void)
{
    for (int index = 0; index <= 8; index += 4) {
        if ((interfaces[index].kernel_flags & IFF_UP) || interfaces[index].kernel_ap || interfaces[index].downstream)
            return false;
    }
    return true;
}

static int nl80211_connect_sta(wifi_interface_info_t *interface)
{
    event(1000);
    ++connect_calls;
    if (is_wifi_hal_vap_mesh_sta((int)interface->vap_info.vap_index) && !all_down()) ++unsafe_connect;
    return connect_failure ? -1 : 0;
}

static void *hash_map_get_first(hash_map_t *map)
{
    return map == NULL || map->count == 0 ? NULL : map->items[0];
}

static void *hash_map_get_next(hash_map_t *map, void *current)
{
    if (map == NULL) return NULL;
    for (size_t index = 0; index + 1 < map->count; ++index) {
        if (map->items[index] == current) return map->items[index + 1];
    }
    return NULL;
}

static const char *get_vap_ssid(wifi_vap_info_t *vap)
{
    return vap->u.sta_info.ssid;
}

static void fixture_init(void)
{
    g_wifi_hal.num_radios = 3;
    for (unsigned int index = 0; index < 13; ++index) {
        wifi_interface_info_t *interface = &interfaces[index];
        interface->vap_info.vap_index = index;
        interface->vap_info.radio_index = index / 4;
        interface->vap_info.vap_mode = index % 4 == 3 || index == 12 ? wifi_vap_mode_sta : wifi_vap_mode_ap;
        interface->mesh = index < 12 && (index % 4 == 0 || index % 4 == 3);
        snprintf(interface->name, sizeof(interface->name), "vif%u", index);
        interface->vap_initialized = true;
        interface->kernel_flags = IFF_UP;
        interface->scan_info_map = &scans;
        pthread_mutex_init(&interface->scan_info_mutex, NULL);
        if (interface->vap_info.vap_mode == wifi_vap_mode_ap) {
            interface->vap_info.u.bss_info.enabled = true;
            interface->bss_started = true;
            interface->kernel_ap = true;
            interface->beacon_set = 1;
            interface->downstream = interface->mesh ? 2 : 5;
            interface->u.ap.hapd.conf = interface;
        } else {
            interface->vap_info.u.sta_info.mac[0] = 2;
            interface->vap_info.u.sta_info.mac[5] = (unsigned char)(index + 32);
            strcpy(interface->vap_info.u.sta_info.ssid, "mesh_backhaul");
        }
        if (index < 12) maps[index / 4].items[maps[index / 4].count++] = interface;
    }
    maps[0].items[maps[0].count++] = &interfaces[12];
    for (unsigned int radio = 0; radio < 3; ++radio) {
        radios[radio].configured = true;
        radios[radio].oper_param.enable = true;
        radios[radio].interface_map = &maps[radio];
    }
    for (unsigned int index = 0; index < 3; ++index) {
        scan_rows[index].bssid[0] = 2;
        scan_rows[index].bssid[5] = (unsigned char)(64 + index);
        strcpy(scan_rows[index].ssid, index == 2 ? "other_ssid" : "mesh_backhaul");
        scan_rows[index].rssi = -80 + (int)index * 10;
        scans.items[scans.count++] = &scan_rows[index];
    }
}

static wifi_bss_info_t target(void)
{
    return scan_rows[0];
}

static bool untouched_other_vaps(void)
{
    for (int index = 0; index < 13; ++index) {
        if (index < 12 && index % 4 == 0) continue;
        if (stops[index] || downs[index] || ups[index] || reloads[index] || starts[index]) return false;
        if (!(interfaces[index].kernel_flags & IFF_UP)) return false;
    }
    return true;
}

static uint64_t generation(const unsigned char *state)
{
    uint64_t value = 0;
    for (unsigned int index = 0; index < 8; ++index) value = (value << 8) | state[index];
    return value;
}

static bool connect_and_snapshot(unsigned char *state)
{
    wifi_bss_info_t selected = target();
    if (wifi_hal_connect(station_index, &selected) != RETURN_OK) return false;
    wifi_hal_backhaul_root_link(&interfaces[station_index], true);
    return wifi_hal_backhaul_root_state(station_index, state) == RETURN_OK;
}

#define REQUIRE(condition) do { if (!(condition)) { \
    fprintf(stderr, "FAIL line %d: %s; connect=%d unsafe=%d admitted=%d connected=%d all_down=%d\n", \
        __LINE__, #condition, connect_calls, unsafe_connect, backhaul_root_admitted, backhaul_root_connected, all_down()); \
    return 1; } } while (0)

static const char *cases[] = {
    "explicit-all-aps-before-connect", "scan-selected-all-aps-before-connect", "same-parent-reconnect-barrier",
    "stop-failure-iffdown-safe", "iffdown-ioctl-failure", "iffdown-socket-failure", "initial-flags-failure",
    "readback-failure", "readback-still-up", "reload-failure", "missing-radio-failclosed",
    "rng-failure", "rng-short", "rng-zero", "missing-interface", "not-sta", "null-target",
    "missing-scan-target", "failed-sta-connect", "ordinary-sta-unchanged", "configured-disabled-ap-preserved",
    "state-before-any-connect", "state-disconnected-after-close", "state-connected-abi22", "state-null-output",
    "state-wrong-vap", "admit-exact-current", "admit-wrong-generation", "admit-wrong-station",
    "admit-wrong-parent", "admit-disconnected-input", "admit-after-disconnect", "admit-after-reconnect",
    "admit-other-vap", "admit-null", "admit-repeat-idempotent", "admit-restart-failure",
    "admit-iffup-failure", "admit-missing-radio", "disconnect-during-last-reopen", "connected-parent-change",
    "duplicate-connected-callback", "secondary-sta-callback-isolation", "loss-closes-downstream",
    "loss-other-vap-nochange", "no-controller-proof-no-reopen", "peer-model-no-local-proof-shortcut",
    "name-gate-fronthaul-sta-excluded", "name-gate-blocks-real-iffup", "generation-all-eight-bytes",
    "zero-radio-quiesce", "zero-radio-connect", "zero-radio-admit",
    "reload-before-stop-and-down", "revoke-current", "revoke-unadmitted",
    "revoke-stale-generation", "revoke-stale-parent", "revoke-stale-station",
    "revoke-disconnected", "revoke-other-vap", "revoke-null", "revoke-repeat",
    "revoke-quiesce-failure-still-disconnects", "revoke-disconnect-failure-stays-closed",
    "revoke-reconnect-during-quiesce"
};

static int run_case(const char *name)
{
    wifi_bss_info_t selected = target();
    unsigned char state[22], newer[22];
    memset(state, 0xa5, sizeof(state));
    if (strcmp(name, "reload-before-stop-and-down") == 0) {
        REQUIRE(wifi_hal_connect(station_index, &selected) == RETURN_OK);
        for (int index = 0; index <= 8; index += 4) {
            int reload_position = -1, stop_position = -1, down_position = -1;
            for (int position = 0; position < order_count; ++position) {
                if (ordering[position] == 300 + index && reload_position < 0) reload_position = position;
                if (ordering[position] == index && stop_position < 0) stop_position = position;
                if (ordering[position] == 100 + index && down_position < 0) down_position = position;
            }
            REQUIRE(reload_position >= 0 && reload_position < stop_position && stop_position < down_position);
        }
        return 0;
    }
    if (strncmp(name, "revoke-", 7) == 0) {
#if HAVE_ROOT_REVOKE
        REQUIRE(connect_and_snapshot(state));
        if (strcmp(name, "revoke-unadmitted") != 0)
            REQUIRE(wifi_hal_backhaul_root_admit(station_index, state) == RETURN_OK);
        REQUIRE(wifi_hal_backhaul_root_state(station_index, state) == RETURN_OK);
        state[21] = 2;
        int expected_vap = station_index;
        const unsigned char *request = state;
        bool invalid = false;
        if (strcmp(name, "revoke-stale-generation") == 0) { state[7] ^= 1; invalid = true; }
        if (strcmp(name, "revoke-stale-parent") == 0) { state[19] ^= 1; invalid = true; }
        if (strcmp(name, "revoke-stale-station") == 0) { state[13] ^= 1; invalid = true; }
        if (strcmp(name, "revoke-other-vap") == 0) { expected_vap = 3; invalid = true; }
        if (strcmp(name, "revoke-null") == 0) { request = NULL; invalid = true; }
        if (strcmp(name, "revoke-disconnected") == 0) {
            wifi_hal_backhaul_root_link(&interfaces[station_index], false);
            invalid = true;
        }
        if (invalid) {
            int prior_events = order_count;
            REQUIRE(wifi_hal_backhaul_root_revoke(expected_vap, request) == RETURN_ERR);
            REQUIRE(disconnect_calls == 0 && order_count == prior_events);
            return 0;
        }
        if (strcmp(name, "revoke-quiesce-failure-still-disconnects") == 0) down_failure = 4;
        if (strcmp(name, "revoke-disconnect-failure-stays-closed") == 0) disconnect_failure = 1;
        if (strcmp(name, "revoke-reconnect-during-quiesce") == 0) {
            reconnect_during_reload = 4;
            REQUIRE(wifi_hal_backhaul_root_revoke(station_index, request) == RETURN_ERR);
            REQUIRE(disconnect_calls == 0 && !backhaul_root_admitted);
            return 0;
        }
        REQUIRE(wifi_hal_backhaul_root_revoke(station_index, request) ==
            ((down_failure >= 0 || disconnect_failure) ? RETURN_ERR : RETURN_OK));
        REQUIRE(disconnect_calls == 1 && !backhaul_root_admitted && !kernel_calls_while_locked);
        REQUIRE(ordering[order_count - 1] == 1100 && untouched_other_vaps());
        REQUIRE(wifi_hal_backhaul_root_state(station_index, newer) == RETURN_OK);
        REQUIRE(generation(newer) != generation(state));
        REQUIRE(wifi_hal_backhaul_root_admit(station_index, state) == RETURN_ERR);
        if (down_failure < 0) REQUIRE(all_down());
        if (strcmp(name, "revoke-repeat") == 0) {
            REQUIRE(wifi_hal_backhaul_root_revoke(station_index, request) == RETURN_ERR);
            REQUIRE(disconnect_calls == 1);
        }
        return 0;
#else
        REQUIRE(false);
#endif
    }
    if (strcmp(name, "zero-radio-connect") == 0) {
        g_wifi_hal.num_radios = 0;
        REQUIRE(wifi_hal_connect(station_index, &selected) == RETURN_ERR && connect_calls == 0);
        return 0;
    }
    if (strcmp(name, "zero-radio-quiesce") == 0) {
        REQUIRE(wifi_hal_backhaul_root_close(station_index) == RETURN_OK);
        g_wifi_hal.num_radios = 0;
        REQUIRE(backhaul_root_quiesce() == RETURN_ERR && !backhaul_root_admitted);
        return 0;
    }
    if (strcmp(name, "explicit-all-aps-before-connect") == 0 ||
        strcmp(name, "scan-selected-all-aps-before-connect") == 0 ||
        strcmp(name, "same-parent-reconnect-barrier") == 0) {
        if (strcmp(name, "scan-selected-all-aps-before-connect") == 0) memset(selected.bssid, 0, 6);
        if (strcmp(name, "same-parent-reconnect-barrier") == 0) {
            REQUIRE(connect_and_snapshot(state));
            REQUIRE(wifi_hal_backhaul_root_admit(station_index, state) == RETURN_OK);
        }
        REQUIRE(wifi_hal_connect(station_index, &selected) == RETURN_OK);
        REQUIRE(all_down() && !unsafe_connect && !kernel_calls_while_locked && untouched_other_vaps());
        REQUIRE(order_count > 0 && ordering[order_count - 1] == 1000);
        for (int index = 0; index <= 8; index += 4) REQUIRE(stops[index] && reads[index] >= 2 && reloads[index]);
        if (strcmp(name, "scan-selected-all-aps-before-connect") == 0)
            REQUIRE(memcmp(interfaces[station_index].u.sta.backhaul.bssid, scan_rows[1].bssid, 6) == 0);
        return 0;
    }
    if (strcmp(name, "stop-failure-iffdown-safe") == 0) {
        stop_failure = 4;
        REQUIRE(wifi_hal_connect(station_index, &selected) == RETURN_OK);
        REQUIRE(all_down() && !unsafe_connect && stops[4] && downs[4] && reads[4] >= 2);
        return 0;
    }
    if (strcmp(name, "iffdown-ioctl-failure") == 0) down_failure = 4;
    else if (strcmp(name, "iffdown-socket-failure") == 0) socket_failure = 1;
    else if (strcmp(name, "initial-flags-failure") == 0) initial_read_failure = 4;
    else if (strcmp(name, "readback-failure") == 0) readback_failure = 4;
    else if (strcmp(name, "readback-still-up") == 0) sticky_up = 4;
    else if (strcmp(name, "reload-failure") == 0) reload_failure = 4;
    else if (strcmp(name, "missing-radio-failclosed") == 0) missing_radio = 2;
    else if (strcmp(name, "rng-failure") == 0) rng_mode = 1;
    else if (strcmp(name, "rng-short") == 0) rng_mode = 2;
    else if (strcmp(name, "rng-zero") == 0) rng_mode = 3;
    if (down_failure >= 0 || socket_failure || initial_read_failure >= 0 || readback_failure >= 0 ||
        sticky_up >= 0 || reload_failure >= 0 || missing_radio >= 0 || rng_mode) {
        REQUIRE(wifi_hal_connect(station_index, &selected) == RETURN_ERR);
        REQUIRE(connect_calls == 0 && !backhaul_root_admitted && untouched_other_vaps());
        return 0;
    }
    if (strcmp(name, "missing-interface") == 0) {
        REQUIRE(wifi_hal_connect(99, &selected) == RETURN_ERR && connect_calls == 0);
        return 0;
    }
    if (strcmp(name, "not-sta") == 0) {
        REQUIRE(wifi_hal_connect(1, &selected) == WIFI_HAL_INVALID_ARGUMENTS && order_count == 0);
        return 0;
    }
    if (strcmp(name, "null-target") == 0) {
        REQUIRE(wifi_hal_connect(station_index, NULL) == RETURN_ERR && connect_calls == 0);
        return 0;
    }
    if (strcmp(name, "missing-scan-target") == 0) {
        scans.count = 0;
        memset(selected.bssid, 0, 6);
        REQUIRE(wifi_hal_connect(station_index, &selected) == RETURN_ERR && connect_calls == 0 && all_down());
        return 0;
    }
    if (strcmp(name, "failed-sta-connect") == 0) {
        connect_failure = 1;
        REQUIRE(wifi_hal_connect(station_index, &selected) == RETURN_ERR && connect_calls == 1 && all_down());
        REQUIRE(!backhaul_root_connected && !backhaul_root_admitted);
        return 0;
    }
    if (strcmp(name, "ordinary-sta-unchanged") == 0) {
        REQUIRE(wifi_hal_connect(12, &selected) == RETURN_OK && connect_calls == 1 && !unsafe_connect);
        REQUIRE(backhaul_root_vap < 0 && untouched_other_vaps() && stops[0] == 0 && stops[4] == 0 && stops[8] == 0);
        return 0;
    }
    if (strcmp(name, "state-before-any-connect") == 0) {
        REQUIRE(wifi_hal_backhaul_root_state(station_index, state) == RETURN_ERR && state[0] == 0xa5);
        return 0;
    }
    if (strcmp(name, "state-disconnected-after-close") == 0) {
        REQUIRE(wifi_hal_backhaul_root_close(station_index) == RETURN_OK);
        REQUIRE(wifi_hal_backhaul_root_state(station_index, state) == RETURN_OK && state[20] == 0 && state[21] == 0);
        unsigned char zero[6] = {0};
        REQUIRE(memcmp(state + 14, zero, 6) == 0 && generation(state) != 0 && all_down());
        return 0;
    }
    if (strcmp(name, "configured-disabled-ap-preserved") == 0) interfaces[4].vap_info.u.bss_info.enabled = false;
    REQUIRE(connect_and_snapshot(state));
    if (strcmp(name, "zero-radio-admit") == 0) {
        g_wifi_hal.num_radios = 0;
        REQUIRE(wifi_hal_backhaul_root_admit(station_index, state) == RETURN_ERR && !backhaul_root_admitted);
        return 0;
    }
    if (strcmp(name, "state-connected-abi22") == 0) {
        REQUIRE(generation(state) == (0x2468ace02468ace0ULL >> 1) + 1);
        REQUIRE(memcmp(state + 8, interfaces[station_index].vap_info.u.sta_info.mac, 6) == 0);
        REQUIRE(memcmp(state + 14, selected.bssid, 6) == 0 && state[20] == 1 && state[21] == 0);
        return 0;
    }
    if (strcmp(name, "state-null-output") == 0) {
        REQUIRE(wifi_hal_backhaul_root_state(station_index, NULL) == RETURN_ERR);
        return 0;
    }
    if (strcmp(name, "state-wrong-vap") == 0) {
        REQUIRE(wifi_hal_backhaul_root_state(3, newer) == RETURN_ERR);
        REQUIRE(wifi_hal_backhaul_root_state(1, newer) == RETURN_ERR);
        return 0;
    }
    if (strcmp(name, "admit-wrong-generation") == 0) state[0] ^= 1;
    else if (strcmp(name, "admit-wrong-station") == 0) state[13] ^= 1;
    else if (strcmp(name, "admit-wrong-parent") == 0) state[19] ^= 1;
    else if (strcmp(name, "admit-disconnected-input") == 0) state[20] = 0;
    else if (strcmp(name, "admit-after-disconnect") == 0) wifi_hal_backhaul_root_link(&interfaces[station_index], false);
    else if (strcmp(name, "admit-after-reconnect") == 0) {
        REQUIRE(wifi_hal_connect(station_index, &selected) == RETURN_OK);
        wifi_hal_backhaul_root_link(&interfaces[station_index], true);
    }
    if (strncmp(name, "admit-wrong-", 12) == 0 || strcmp(name, "admit-disconnected-input") == 0 ||
        strcmp(name, "admit-after-disconnect") == 0 || strcmp(name, "admit-after-reconnect") == 0) {
        REQUIRE(wifi_hal_backhaul_root_admit(station_index, state) == RETURN_ERR && all_down() && !backhaul_root_admitted);
        return 0;
    }
    if (strcmp(name, "admit-other-vap") == 0 || strcmp(name, "admit-null") == 0) {
        REQUIRE(wifi_hal_backhaul_root_admit(strcmp(name, "admit-other-vap") == 0 ? 3 : station_index,
            strcmp(name, "admit-null") == 0 ? NULL : state) == RETURN_ERR && all_down());
        return 0;
    }
    if (strcmp(name, "no-controller-proof-no-reopen") == 0 || strcmp(name, "peer-model-no-local-proof-shortcut") == 0) {
        REQUIRE(all_down() && !backhaul_root_admitted);
        REQUIRE(nl80211_interface_enable(interfaces[4].name, true) == 0 && all_down());
        wifi_hal_backhaul_root_link(&interfaces[station_index], true);
        REQUIRE(all_down() && !backhaul_root_admitted);
        return 0;
    }
    if (strcmp(name, "name-gate-fronthaul-sta-excluded") == 0) {
        REQUIRE(wifi_hal_backhaul_root_name_blocked("vif0") && wifi_hal_backhaul_root_name_blocked("vif4"));
        REQUIRE(!wifi_hal_backhaul_root_name_blocked("vif1") && !wifi_hal_backhaul_root_name_blocked("vif7"));
        REQUIRE(!wifi_hal_backhaul_root_blocked(NULL) && untouched_other_vaps());
        return 0;
    }
    if (strcmp(name, "name-gate-blocks-real-iffup") == 0) {
        REQUIRE(nl80211_interface_enable("vif0", true) == 0 && ups[0] == 0 && all_down());
        REQUIRE(nl80211_interface_enable("vif1", true) == 0 && untouched_other_vaps());
        return 0;
    }
    if (strcmp(name, "generation-all-eight-bytes") == 0) {
        for (unsigned int index = 0; index < 8; ++index) {
            memcpy(newer, state, 22);
            newer[index] ^= 1;
            REQUIRE(wifi_hal_backhaul_root_admit(station_index, newer) == RETURN_ERR && all_down());
        }
        return 0;
    }
    if (strcmp(name, "admit-restart-failure") == 0) restart_failure = 4;
    if (strcmp(name, "admit-iffup-failure") == 0) reopen_up_failure = 4;
    if (strcmp(name, "admit-missing-radio") == 0) missing_radio = 2;
    if (strcmp(name, "disconnect-during-last-reopen") == 0) disconnect_during_reopen = 8;
    if (restart_failure >= 0 || reopen_up_failure >= 0 || missing_radio >= 0 || disconnect_during_reopen >= 0) {
        REQUIRE(wifi_hal_backhaul_root_admit(station_index, state) == RETURN_ERR);
        REQUIRE(!backhaul_root_admitted && all_down());
        return 0;
    }
    REQUIRE(wifi_hal_backhaul_root_admit(station_index, state) == RETURN_OK);
    REQUIRE(untouched_other_vaps() && !kernel_calls_while_locked);
    if (strcmp(name, "configured-disabled-ap-preserved") == 0) {
        REQUIRE(!interfaces[4].vap_info.u.bss_info.enabled && starts[4] == 0 && ups[4] == 0);
        REQUIRE(starts[0] == 1 && starts[8] == 1);
        return 0;
    }
    if (strcmp(name, "admit-repeat-idempotent") == 0) {
        int prior = order_count;
        REQUIRE(wifi_hal_backhaul_root_admit(station_index, state) == RETURN_OK && order_count == prior);
        return 0;
    }
    if (strcmp(name, "connected-parent-change") == 0) {
        interfaces[station_index].u.sta.backhaul.bssid[5] ^= 1;
        wifi_hal_backhaul_root_link(&interfaces[station_index], true);
        REQUIRE(wifi_hal_backhaul_root_state(station_index, newer) == RETURN_OK);
        REQUIRE(newer[21] == 0 && generation(newer) != generation(state));
        return 0;
    }
    if (strcmp(name, "duplicate-connected-callback") == 0) {
        wifi_hal_backhaul_root_link(&interfaces[station_index], true);
        REQUIRE(wifi_hal_backhaul_root_state(station_index, newer) == RETURN_OK);
        REQUIRE(newer[21] == 1 && generation(newer) == generation(state));
        return 0;
    }
    if (strcmp(name, "secondary-sta-callback-isolation") == 0) {
        wifi_hal_backhaul_root_link(&interfaces[3], false);
        REQUIRE(wifi_hal_backhaul_root_state(station_index, newer) == RETURN_OK);
        REQUIRE(newer[21] == 1 && generation(newer) == generation(state));
        return 0;
    }
    if (strcmp(name, "loss-closes-downstream") == 0) {
        wifi_hal_backhaul_root_link(&interfaces[station_index], false);
        REQUIRE(wifi_hal_backhaul_root_loss(station_index) == RETURN_OK && all_down());
        REQUIRE(wifi_hal_backhaul_root_state(station_index, newer) == RETURN_OK && newer[20] == 0 && newer[21] == 0);
        REQUIRE(generation(newer) != generation(state));
        return 0;
    }
    if (strcmp(name, "loss-other-vap-nochange") == 0) {
        int prior = order_count;
        REQUIRE(wifi_hal_backhaul_root_loss(3) == RETURN_OK && order_count == prior && backhaul_root_admitted);
        return 0;
    }
    REQUIRE(strcmp(name, "admit-exact-current") == 0);
    REQUIRE(wifi_hal_backhaul_root_state(station_index, newer) == RETURN_OK && newer[20] == 1 && newer[21] == 1);
    for (int index = 0; index <= 8; index += 4)
        REQUIRE(interfaces[index].kernel_ap && (interfaces[index].kernel_flags & IFF_UP) && starts[index] == 1);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    if (strcmp(argv[1], "--list") == 0) {
        for (size_t index = 0; index < sizeof(cases) / sizeof(cases[0]); ++index) puts(cases[index]);
        return 0;
    }
    bool known = false;
    for (size_t index = 0; index < sizeof(cases) / sizeof(cases[0]); ++index)
        if (strcmp(argv[1], cases[index]) == 0) known = true;
    if (!known) return 2;
    fixture_init();
    return run_case(argv[1]);
}
