#!/usr/bin/env python3
"""Runs one unified-wifi-mesh gtest binary and passes only a run that reached its end.

A test binary that crashes or aborts stops the run with the tests after it never run, and its
output then holds no summary: such a run fails here, naming the test that was running and the
signal or sanitizer report. A run passes when gtest's closing summary is there, the number of
tests that ran equals the number the same filter lists, no test failed and the binary exited 0.
Skipped tests are listed by name with gtest's message (the database tests without a MariaDB say
"skipped: no MariaDB").

  uwm-unit-run.py [--launcher 'CMD ARGS'] [--timeout S] [--log FILE] BINARY [GTEST_ARGS ...]

--launcher runs the binary through a command (a target sysroot's loader, for one). The
binary's tests/main.cpp keeps its exclusion list under any filter given here (0279).
Exit status: 0 passed, 1 tests failed, 2 the run did not reach its end, 3 counts disagree or the
binary could not be listed.
"""
import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--launcher", default="", help="command the binary runs through")
parser.add_argument("--timeout", type=int, default=3600, help="seconds for the whole run")
parser.add_argument("--log", help="file for the run's whole output")
parser.add_argument("binary")
parser.add_argument("gtest_args", nargs=argparse.REMAINDER)
args = parser.parse_args()
binary = os.path.abspath(args.binary)
command = shlex.split(args.launcher) + [binary]
gtest_args = [a for a in args.gtest_args if a != "--"]


def run(extra, timeout):
    with tempfile.TemporaryDirectory(prefix="uwm-unit-") as cwd:
        try:
            p = subprocess.run(command + gtest_args + extra, cwd=cwd, capture_output=True, timeout=timeout)
            return p.stdout.decode(errors="replace") + p.stderr.decode(errors="replace"), p.returncode
        except subprocess.TimeoutExpired as e:
            return (e.stdout or b"").decode(errors="replace") + (e.stderr or b"").decode(errors="replace"), None


listing, rc = run(["--gtest_list_tests"], 300)
if rc != 0:
    print(f"FAIL: the binary could not list its tests (exit {rc})\n{listing[-2000:]}")
    sys.exit(3)
listed = sum(1 for line in listing.splitlines() if line.startswith("  ") and line.strip())

text, rc = run(["--gtest_color=no"], args.timeout)
if args.log:
    with open(args.log, "w") as f:
        f.write(text)
# gtest's lines can follow a test's own output on the same line: search, do not anchor
summary = re.search(r"\[==========\] (\d+) tests? from (\d+) test suites? ran\.", text)
started = re.findall(r"\[ RUN      \] (\S+)", text)
ended = re.findall(r"\[ +(?:OK|FAILED|SKIPPED) +\] (\S+) \(", text)
failed = re.findall(r"\[  FAILED  \] (\S+) \(", text)
skipped = re.findall(r"\[  SKIPPED \] (\S+) \(", text)

if summary is None:
    unfinished = [t for t in started if t not in set(ended)]
    cause = "the time limit" if rc is None else (
        f"signal {-rc}" if rc < 0 else f"exit {rc}")
    # what stopped it: a sanitizer's fatal report or an assertion; UBSan's runtime errors only
    # warn, so the last of them is named only when there is neither
    report = (re.search(r"ERROR: AddressSanitizer: [\w-]+[^\n]*", text) or re.search(r"Assertion [^\n]* failed\.", text)
              or (re.findall(r"runtime error: [^\n]*", text) or [None])[-1])
    print(f"FAIL: the run did not reach its end: {len(ended)} of {listed} tests ran, stopped in "
          f"{unfinished[-1] if unfinished else 'no test'} ({cause})")
    if report:
        print(f"  {(report if isinstance(report, str) else report.group(0))[:300]}")
    sys.exit(2)

ran = int(summary.group(1))
for name in skipped:
    # gtest prints the skip's message inside the test's block, before its SKIPPED line
    block = re.search(r"\[ RUN      \] " + re.escape(name) + r"\n(.*?)\[  SKIPPED \] " + re.escape(name) + r" \(",
                      text, re.S)
    message = re.search(r"skipped: [^\n]+", block.group(1)) if block else None
    print(f"skipped: {name}" + (f" ({message.group(0)})" if message else ""))
if ran != listed:
    print(f"FAIL: {ran} tests ran, the filter lists {listed}")
    sys.exit(3)
if failed or rc != 0:
    for name in failed:
        print(f"failed: {name}")
    print(f"FAIL: {len(failed)} of {ran} tests failed (exit {rc})")
    sys.exit(1)
print(f"passed: {ran} tests ran to the end, {len(skipped)} skipped")
