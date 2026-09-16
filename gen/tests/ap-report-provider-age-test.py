"""Compile the production OneWifi AP-report age calculation with a controlled clock."""

import ctypes
from pathlib import Path
import re
import subprocess
import sys
import tempfile


source = (Path(sys.argv[1]) / "source/apps/em/wifi_em.c").read_text()
function = re.search(r"static int prepare_sta_lins_metrics_data\(.*?\n\}", source, re.S).group()
initialization = re.search(r"uint32_t delta_ms = .*?;", function).group()
calculation = function[function.index("    if (stats->last_update_time.tv_sec"):function.index("    // Associated STA Link Metrics")]
program = r"""
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <time.h>
#include <assert.h>
static struct timespec clock_value;
static int clock_failure;
static int test_clock(clockid_t identifier, struct timespec *result) {
    assert(identifier == CLOCK_MONOTONIC);
    *result = clock_value;
    return clock_failure;
}
#define clock_gettime test_clock
uint32_t age(int64_t sample_seconds, long sample_nanoseconds, int64_t current_seconds,
             long current_nanoseconds, int failure) {
    struct { struct timespec last_update_time; } storage;
    storage.last_update_time.tv_sec = sample_seconds;
    storage.last_update_time.tv_nsec = sample_nanoseconds;
    __typeof__(storage) *stats = &storage;
    struct timespec now, diff;
    INITIALIZATION
    clock_value.tv_sec = current_seconds;
    clock_value.tv_nsec = current_nanoseconds;
    clock_failure = failure;
    CALCULATION
    return delta_ms;
}
""".replace("INITIALIZATION", initialization).replace("CALCULATION", calculation)

with tempfile.TemporaryDirectory(prefix="ap-provider-age-") as temporary:
    library = Path(temporary) / "age.so"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    "-x", "c", "-", "-o", str(library)], input=program, text=True, check=True)
    implementation = ctypes.CDLL(str(library))
    implementation.age.argtypes = [ctypes.c_int64, ctypes.c_long, ctypes.c_int64, ctypes.c_long, ctypes.c_int]
    implementation.age.restype = ctypes.c_uint32
    for arguments, expected in (
        ((10, 0, 10, 0, 0), 0),
        ((10, 500000000, 12, 100000000, 0), 1600),
        ((10, 0, 10, 345000000, 0), 345),
        ((0, 0, 10, 0, 0), 2**32 - 1),
        ((10, 0, 9, 0, 0), 2**32 - 1),
        ((10, 900000000, 10, 800000000, 0), 2**32 - 1),
        ((10, -1, 11, 0, 0), 2**32 - 1),
        ((10, 1000000000, 11, 0, 0), 2**32 - 1),
        ((10, 0, 11, 1000000000, 0), 2**32 - 1),
        ((10, 0, 11, 0, -1), 2**32 - 1),
        ((10, 0, 10 + (2**32 - 1) // 1000, ((2**32 - 1) % 1000) * 1000000, 0), 2**32 - 1),
        ((10, 0, 10 + 2**32 // 1000, (2**32 % 1000) * 1000000, 0), 2**32 - 1),
        ((10, 0, 10 + 2**33 // 1000, (2**33 % 1000) * 1000000, 0), 2**32 - 1),
    ):
        assert implementation.age(*arguments) == expected, arguments
print("PASS: production provider ages, nanosecond borrow, missing/future/invalid timestamps, clock failure and saturating age overflow")
