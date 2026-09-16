#!/usr/bin/env python3
"""Run production wifi_getNASta against a real read-only SOCK_SEQPACKET peer.

Pass wifi_hal.c after applying the HAL recipe patches. Only sysfs and Unix
socket paths are redirected; production serialization and socket I/O execute
unchanged. No lab services, medium settings or containers are touched.
"""

import argparse
import dataclasses
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import tempfile
import threading


HEADER = struct.Struct("!IHHIIQ")
INFO = struct.Struct("!QQIIII")
ASSOCIATION = struct.Struct("!6s6s6s2sII")
LINK = struct.Struct("!6s6sIhH")
CAPABILITIES = (1 << 4) | (1 << 5) | (1 << 10)
RAW_BSTA = bytes.fromhex("0200005dbdd4")
CANONICAL_BSTA = bytes.fromhex("420000000200")
LOCAL_RADIO = bytes.fromhex("420000000300")
OWNER_RADIO = bytes.fromhex("420000000000")


@dataclasses.dataclass
class Case:
    name: str
    success: bool = False
    raw: bytes = RAW_BSTA
    station: bytes = CANONICAL_BSTA
    owner: bytes = OWNER_RADIO
    flags: int = 2
    association_frequency: int = 5180
    capabilities: int = CAPABILITIES
    phase: int = 0
    mutation: str = ""
    opclass: int = 115
    channel: int = 36
    frequency: int = 5180
    snr: int = 26
    expected_rcpi: int = 90


def response(opcode, payload, mutation=""):
    fields = [0x574D4443, 1, opcode, len(payload), 0, 77]
    if mutation == "magic":
        fields[0] ^= 1
    elif mutation == "version":
        fields[1] = 2
    elif mutation == "opcode":
        fields[2] = opcode + 1
    elif mutation == "length":
        fields[3] += 1
    elif mutation == "unknown":
        fields[4] = 9
        payload = b""
        fields[3] = 0
    elif mutation == "ambiguous":
        fields[4] = 4
        payload = b""
        fields[3] = 0
    elif mutation == "status":
        fields[4] = 1
    packet = HEADER.pack(*fields) + payload
    if mutation == "short":
        return packet[:-1]
    if mutation == "oversized":
        return packet + b"x" * 64
    return packet


def serve(listener, case, requests, errors):
    try:
        listener.settimeout(3)
        with listener.accept()[0] as connection:
            connection.settimeout(3)
            for unused_round in range(4):
                packet = connection.recv(4096)
                if not packet:
                    return
                assert len(packet) >= HEADER.size, "short HAL request"
                magic, version, opcode, length, status, generation = HEADER.unpack_from(packet)
                assert magic == 0x574D4443 and version == 1 and status == 0 and generation == 0
                payload = packet[HEADER.size:]
                assert length == len(payload), "HAL request length mismatch"
                requests.append((opcode, payload))
                mutation = case.mutation if case.phase == opcode else ""
                if mutation == "eof":
                    return
                if opcode == 1:
                    assert payload == b"" and len(requests) == 1
                    answer = INFO.pack(1, 2, case.capabilities, 256, 106, 0)
                elif opcode == 14:
                    endpoint, station, owner, reserved, frequency, flags = ASSOCIATION.unpack(payload)
                    assert endpoint == case.raw, "GET_ASSOCIATION must use the unchanged raw STA MAC"
                    assert station == owner == bytes(6) and reserved == bytes(2)
                    assert frequency == flags == 0
                    endpoint = case.raw if mutation != "endpoint" else bytes.fromhex("020000ffffff")
                    reserved = b"\x00\x01" if mutation == "reserved" else bytes(2)
                    answer = ASSOCIATION.pack(endpoint, case.station, case.owner, reserved,
                                              case.association_frequency, case.flags)
                elif opcode == 7:
                    source, destination, frequency, snr, flags = LINK.unpack(payload)
                    assert destination == LOCAL_RADIO, "ledger owner must not replace the receiving AP radio"
                    assert frequency == case.frequency and snr == flags == 0
                    if source != case.station:
                        connection.sendall(response(opcode, b"", "ambiguous"))
                        continue
                    source = source if mutation != "source" else case.raw
                    destination = destination if mutation != "destination" else case.owner
                    frequency = frequency if mutation != "frequency" else frequency + 5
                    answer = LINK.pack(source, destination, frequency, case.snr, 0)
                else:
                    raise AssertionError(f"unexpected/non-read-only opcode {opcode}")
                connection.sendall(response(opcode, answer, mutation))
            raise AssertionError("unexpected repeated HAL request")
    except BaseException as error:
        errors.append(error)


PROGRAM = r"""
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <dirent.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <arpa/inet.h>
#define HWSIM_RADIO 1
#define WIFI_HAL_ERROR -1
#define WIFI_HAL_SUCCESS 0
#define AP_INDEX_ASSERT(index) do { if ((index) != 0) return WIFI_HAL_ERROR; } while (0)
#define wifi_hal_error_print(...) ((void)0)
#define wifi_hal_dbg_print(...) ((void)0)
typedef int INT;
typedef unsigned int UINT;
typedef struct {uint8_t sta_mac[6]; UINT channel; UINT op_class;} wifi_na_sta_req_params_t;
typedef struct {uint8_t sta_mac[6]; UINT channel; UINT op_class; UINT rcpi;} wifi_na_sta_info_t;
static DIR *test_opendir(const char *path) {
    assert(strcmp(path, "/sys/class/ieee80211") == 0);
    return opendir(getenv("HAL_TEST_SYSFS"));
}
static FILE *test_fopen(const char *path, const char *mode) {
    const char *prefix = "/sys/class/ieee80211/";
    assert(strncmp(path, prefix, strlen(prefix)) == 0 && strcmp(mode, "r") == 0);
    char redirected[4096];
    assert(snprintf(redirected, sizeof(redirected), "%s/%s", getenv("HAL_TEST_SYSFS"),
        path + strlen(prefix)) < (int)sizeof(redirected));
    return fopen(redirected, mode);
}
static int test_connect(int descriptor, const struct sockaddr *address, socklen_t length) {
    assert(length == sizeof(struct sockaddr_un) && address->sa_family == AF_UNIX);
    const struct sockaddr_un *original = (const struct sockaddr_un *)address;
    assert(strcmp(original->sun_path, "/wmediumd-metrics/control.sock") == 0);
    int type = 0;
    socklen_t type_length = sizeof(type);
    assert(getsockopt(descriptor, SOL_SOCKET, SO_TYPE, &type, &type_length) == 0);
    assert(type == SOCK_SEQPACKET);
    struct sockaddr_un redirected = { .sun_family = AF_UNIX };
    assert(snprintf(redirected.sun_path, sizeof(redirected.sun_path), "%s", getenv("HAL_TEST_SOCKET"))
        < (int)sizeof(redirected.sun_path));
    return connect(descriptor, (const struct sockaddr *)&redirected, sizeof(redirected));
}
#define opendir test_opendir
#define fopen test_fopen
#define connect test_connect
PRODUCTION_FUNCTION
int main(int count, char **arguments) {
    assert(count == 4);
    wifi_na_sta_req_params_t query = {0};
    for (unsigned int index = 0; index < 6; ++index) {
        unsigned int octet;
        assert(sscanf(arguments[1] + index * 2, "%2x", &octet) == 1);
        query.sta_mac[index] = octet;
    }
    query.op_class = strtoul(arguments[2], NULL, 10);
    query.channel = strtoul(arguments[3], NULL, 10);
    wifi_na_sta_info_t result;
    memset(&result, 0xa5, sizeof(result));
    wifi_na_sta_info_t initial = result;
    int status = wifi_getNASta(0, &query, &result);
    if (status != WIFI_HAL_SUCCESS) assert(memcmp(&result, &initial, sizeof(result)) == 0);
    printf("%d %02x%02x%02x%02x%02x%02x %u %u %u\n", status,
        result.sta_mac[0], result.sta_mac[1], result.sta_mac[2],
        result.sta_mac[3], result.sta_mac[4], result.sta_mac[5],
        result.op_class, result.channel, result.rcpi);
    return 0;
}
"""


def cases():
    yield Case("random-backhaul-STA", success=True)
    yield Case("deterministic-client", success=True, raw=bytes.fromhex("020000000a00"),
               station=bytes.fromhex("420000000a00"), flags=1)
    yield Case("random-client", success=True, raw=bytes.fromhex("02abcdef2345"),
               station=bytes.fromhex("420000000b00"), flags=3)
    yield Case("owner-not-target", success=True, owner=bytes.fromhex("420000000400"))
    yield Case("2.4GHz-request-independent-of-serving-band", success=True,
               opclass=81, channel=6, frequency=2437)
    yield Case("6GHz-request-independent-of-serving-band", success=True,
               opclass=131, channel=5, frequency=5975)
    yield Case("RCPI-low-clamp", success=True, snr=-30, expected_rcpi=0)
    yield Case("RCPI-high-clamp", success=True, snr=120, expected_rcpi=220)
    for capability in (1 << 4, 1 << 5, 1 << 10):
        yield Case(f"missing-capability-{capability}", capabilities=CAPABILITIES & ~capability)
    for phase in (1, 14, 7):
        for mutation in ("magic", "version", "opcode", "length", "status", "short", "oversized", "eof"):
            yield Case(f"phase-{phase}-{mutation}", phase=phase, mutation=mutation)
    for mutation in ("unknown", "ambiguous", "endpoint", "reserved"):
        yield Case(f"association-{mutation}", phase=14, mutation=mutation)
    for flags in (0, 4, 5, 6, 8, 0x80000002):
        yield Case(f"association-unconfirmed-flags-{flags}", flags=flags)
    yield Case("association-zero-station", station=bytes(6))
    yield Case("association-multicast-station", station=bytes.fromhex("430000000200"))
    yield Case("association-zero-owner", owner=bytes(6))
    yield Case("association-multicast-owner", owner=bytes.fromhex("430000000000"))
    yield Case("association-self-owner", owner=CANONICAL_BSTA)
    yield Case("association-no-frequency", association_frequency=0)
    for mutation in ("source", "destination", "frequency"):
        yield Case(f"frequency-conflicting-{mutation}", phase=7, mutation=mutation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="patched src/wifi_hal.c")
    args = parser.parse_args()
    source = args.source.read_text()
    production = re.search(r"INT wifi_getNASta\([^;]*?\)\s*\{.*?\n\}", source, re.S).group()
    failures = []
    tested = 0
    with tempfile.TemporaryDirectory(prefix="hal-candidate-") as directory:
        root = Path(directory)
        executable = root / "test"
        subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-Wno-format-truncation", "-x", "c", "-", "-o", str(executable)],
                       input=PROGRAM.replace("PRODUCTION_FUNCTION", production), text=True, check=True)
        phy = root / "sysfs" / "phy0"
        phy.mkdir(parents=True)
        (phy / "macaddress").write_text("02:00:00:00:03:00\n")
        endpoint = root / "control.sock"
        environment = dict(os.environ, HAL_TEST_SYSFS=str(phy.parent), HAL_TEST_SOCKET=str(endpoint))
        for case in cases():
            tested += 1
            requests = []
            errors = []
            with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as listener:
                listener.bind(str(endpoint))
                listener.listen(1)
                server = threading.Thread(target=serve, args=(listener, case, requests, errors), daemon=True)
                server.start()
                result = subprocess.run([str(executable), case.raw.hex(), str(case.opclass), str(case.channel)],
                                        env=environment, text=True, capture_output=True, timeout=4)
                server.join(4)
                assert not server.is_alive(), f"{case.name}: fake provider did not terminate"
            endpoint.unlink()
            try:
                assert not errors, errors
                assert result.returncode == 0, (result.returncode, result.stderr)
                fields = result.stdout.split()
                assert len(fields) == 5, result.stdout
                status = int(fields[0])
                opcodes = [request[0] for request in requests]
                if case.success:
                    assert status == 0, f"HAL returned {status}; requests={opcodes}"
                    assert fields[1] == case.raw.hex(), "report must retain requested STA identity"
                    assert [int(field) for field in fields[2:]] == [case.opclass, case.channel, case.expected_rcpi]
                    assert opcodes == [1, 14, 7], f"uncorrelated or out-of-order lookup {opcodes}"
                else:
                    assert status == -1, f"HAL fabricated success; requests={opcodes}"
                    if case.phase != 7:
                        assert 7 not in opcodes, f"frequency lookup without valid ownership {opcodes}"
            except AssertionError as error:
                failures.append(case.name)
                print(f"FAIL: {case.name}: {error}", flush=True)
        print(f"{tested - len(failures)}/{tested} production HAL socket cases PASS", flush=True)
    if failures:
        return 1
    print("PASS: canonical BSTA/client identity, unchanged requested MAC/frequency, local AP destination, "
          "capability/framing/correlation rejection and no output mutation on failure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
