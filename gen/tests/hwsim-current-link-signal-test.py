#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile


source = Path(sys.argv[1]).read_text()
definitions = source[source.index("enum {\n    WMDC_OP_HELLO"):source.index("static bool hwsim_local_radio_identity")]
start = source.index("static bool hwsim_current_link_rssi(")
implementation = source[start:source.index("\n}\n", start) + 3]
assert "WMDC_CAP_READ_ONLY | WMDC_CAP_FREQUENCY_QUALIFIED_SNR |" in source
assert "(*associated_dev_array)[i].cli_RSSI = sta_list.entries[i].rssi_dbm;" in source
assert "sta_list.sample_current_signal = !is_wifi_hal_vap_mesh_backhaul(apIndex);" in source
assert "if (sta_list.sample_current_signal) {" in source
assert "if (sta_list->sample_current_signal && (!owner_known ||" in source
assert "if (sta_list->signal_unavailable) {\n        return -1;" in source

program = r"""
#include <arpa/inet.h>
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
#include <pthread.h>
typedef uint8_t mac_address_t[6];
""" + definitions + implementation + r"""
struct exchange {
    int descriptor;
    int fault;
    int snr;
    uint32_t frequency;
};
static void *respond(void *opaque) {
    struct exchange *exchange = opaque;
    struct {
        struct wmdc_header header;
        struct wmdc_frequency_link link;
    } message;
    assert(recv(exchange->descriptor, &message, sizeof(message), 0) == sizeof(message));
    const uint8_t station[6] = {0x42, 0, 0, 0, 3, 0};
    const uint8_t owner[6] = {0x42, 0, 0, 0, 1, 0};
    assert(memcmp(message.link.source, station, 6) == 0);
    assert(memcmp(message.link.destination, owner, 6) == 0);
    assert(ntohl(message.link.frequency_mhz) == exchange->frequency);
    message.link.snr_db = htons((uint16_t)exchange->snr);
    switch (exchange->fault) {
    case 1: message.header.magic = 0; break;
    case 2: message.header.version = htons(2); break;
    case 3: message.header.opcode = htons(3); break;
    case 4: message.header.status = htonl(9); break;
    case 5: message.header.payload_len = 0; break;
    case 6: message.link.source[5]++; break;
    case 7: message.link.destination[5]++; break;
    case 8: message.link.frequency_mhz = htonl(exchange->frequency + 20); break;
    case 9: message.link.snr_db = htons(128); break;
    }
    size_t length = sizeof(message) - (exchange->fault == 10 ? 1 : 0);
    assert(send(exchange->descriptor, &message, length, 0) == (ssize_t)length);
    return NULL;
}
int main(void) {
    const uint32_t frequencies[] = {2437, 5180, 5955, 6135};
    const int levels[] = {-20, 0, 25, 60};
    for (unsigned int sample = 0; sample < 4; sample++) {
        for (int fault = 0; fault <= 10; fault++) {
            int sockets[2];
            assert(socketpair(AF_UNIX, SOCK_SEQPACKET, 0, sockets) == 0);
            struct wmdc_association association = {
                .station = {0x42, 0, 0, 0, 3, 0},
                .owner = {0x42, 0, 0, 0, 1, 0},
                .frequency_mhz = htonl(frequencies[sample]),
            };
            struct exchange exchange = {sockets[1], fault, levels[sample], frequencies[sample]};
            pthread_t responder;
            assert(pthread_create(&responder, NULL, respond, &exchange) == 0);
            int rssi = 12345;
            bool valid = hwsim_current_link_rssi(sockets[0], &association, &rssi);
            assert(valid == (fault == 0));
            assert(rssi == (valid ? levels[sample] - 91 : 12345));
            assert(pthread_join(responder, NULL) == 0);
            close(sockets[0]);
            close(sockets[1]);
        }
    }
    struct wmdc_association absent = {};
    int unchanged = 12345;
    assert(!hwsim_current_link_rssi(-1, &absent, &unchanged));
    assert(!hwsim_current_link_rssi(0, &absent, &unchanged));
    assert(unchanged == 12345);
}
"""
with tempfile.TemporaryDirectory(prefix="hwsim-current-signal-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-pthread",
                    "-x", "c", "-", "-o", str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
print("PASS: current uplink RSSI, all bands, asymmetric direction and fail-closed wire validation")
