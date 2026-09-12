#!/usr/bin/env python3
import argparse
from pathlib import Path
import subprocess
import tempfile


parser = argparse.ArgumentParser(description="Compile HAL PMF defaults with hostapd comeback IE encoding")
parser.add_argument("hal_source", type=Path)
parser.add_argument("hostapd_source", type=Path)
args = parser.parse_args()
hal = args.hal_source.read_text()
start = hal.rfind("#ifdef CONFIG_IEEE80211W", 0, hal.index("conf->assoc_sa_query_max_timeout ="))
defaults = hal[start:hal.index("#endif /* CONFIG_IEEE80211W */", start) + len("#endif /* CONFIG_IEEE80211W */")]
hostapd = args.hostapd_source.read_text()
start = hostapd.index("static u8 * hostapd_eid_timeout_interval(")
end = hostapd.index("\n}\n", hostapd.index("u8 * hostapd_eid_assoc_comeback_time(", start)) + 3
helpers = hostapd[start:end]
program = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define WLAN_EID_TIMEOUT_INTERVAL 56
#define WLAN_TIMEOUT_ASSOC_COMEBACK 3
#define WPA_CIPHER_AES_128_CMAC 1
static void put_le32(u8 *target, u32 value) {
    for (unsigned int index = 0; index < 4; index++) target[index] = value >> (8 * index);
}
#define WPA_PUT_LE32 put_le32
struct os_reltime { long sec, usec; };
static void os_get_reltime(struct os_reltime *now) { now->sec = 100; now->usec = 0; }
static void os_reltime_sub(struct os_reltime *now, struct os_reltime *start, struct os_reltime *passed) {
    passed->sec = now->sec - start->sec; passed->usec = now->usec - start->usec;
}
struct Config {
    unsigned int assoc_sa_query_max_timeout, assoc_sa_query_retry_timeout;
    int group_mgmt_cipher;
#ifdef CONFIG_TESTING_OPTIONS
    int test_assoc_comeback_type;
#endif
};
struct hostapd_data { struct Config *conf; };
struct sta_info { struct os_reltime sa_query_start; };
static void defaults(struct Config *conf) {
''' + defaults + r'''
}
''' + helpers + r'''
int main(void) {
    struct Config config = {0};
    defaults(&config);
    assert(config.assoc_sa_query_max_timeout == 1000);
    assert(config.assoc_sa_query_retry_timeout == 201);
    struct hostapd_data ap = {&config};
    struct sta_info station = {{100, 0}};
    u8 encoded[7] = {0};
    assert(hostapd_eid_assoc_comeback_time(&ap, &station, encoded) == encoded + 7);
    assert(encoded[0] == 56 && encoded[1] == 5 && encoded[2] == 3);
    assert(encoded[3] == 0xe8 && encoded[4] == 3 && encoded[5] == 0 && encoded[6] == 0);
    puts("PASS normal PMF comeback type 3 / 1000 TU; SA Query retry and maximum unchanged");
}
'''
with tempfile.TemporaryDirectory(prefix="hostapd-comeback-default-") as directory:
    executable = Path(directory) / "test"
    for flags in ([], ["-DCONFIG_TESTING_OPTIONS"]):
        subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                        "-DCONFIG_IEEE80211W", *flags, "-x", "c", "-", "-o", str(executable)],
                       input=program, text=True, check=True)
        subprocess.run([str(executable)], check=True)
