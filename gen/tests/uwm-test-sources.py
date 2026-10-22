#!/usr/bin/env python3
"""Prints, from src/PART/Makefile.am, what the image's unit build compiles for one part (ctrl or
agent) beyond the part's own product sources, as paths under ROOT:
  sources   the files onewifi_em_PART_test_SOURCES lists by name: the tests, and the product
            files the test binary compiles in besides the part's own
  ldadd     the sources of the libraries onewifi_em_PART_test_LDADD links (src/DIR/libNAME.la,
            from src/DIR/Makefile.am's libNAME_la_SOURCES)
uwm-unit.mk builds the native test binary from them, so CI runs the image's test set.
  uwm-test-sources.py ROOT PART sources|ldadd
"""
import re
import sys

root, part, what = sys.argv[1:4]


def assignments(path):
    """The Makefile.am's variables, each with its whole value (continuations joined, += added)."""
    values = {}
    text = re.sub(r"\\\n", " ", open(path).read())
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9_]+)\s*(\+?=)(.*)$", line)
        if m:
            name, op, value = m.groups()
            values[name] = (values.get(name, "") + " " if op == "+=" else "") + value.split("#")[0]
    return values


def expand(value, values, depth=0):
    """value with the Makefile.am's own variables in it expanded; others are left as they are."""
    if depth > 10:
        sys.exit(f"{value}: variables nested too deep")

    def one(m):
        inner = values.get(m.group(1))
        return m.group(0) if inner is None else expand(inner, values, depth + 1)

    return re.sub(r"\$\(([A-Za-z0-9_]+)\)", one, value)


def files(value):
    return re.findall(r"\$\(top_srcdir\)/((?:tests|src)/[A-Za-z0-9_/-]+\.cpp)", value)


makefile_am = f"{root}/src/{part}/Makefile.am"
values = assignments(makefile_am)
name = f"onewifi_em_{part}_test_SOURCES"
if name not in values:
    sys.exit(f"no {name} in src/{part}/Makefile.am")
if what == "sources":
    # by name only: the part's own sources, $(onewifi_em_PART_SOURCES), are the native makefile's
    out = files(values[name])
    if not any(s.startswith("tests/") for s in out):
        sys.exit(f"{name} lists no tests")
elif what == "ldadd":
    out = []
    for lib in re.findall(r"\$\(top_builddir\)/(src/[A-Za-z0-9_/-]+)/lib([A-Za-z0-9_]+)\.la",
                          expand(values.get(f"onewifi_em_{part}_test_LDADD", ""), values)):
        libdir, libname = lib
        lib_values = assignments(f"{root}/{libdir}/Makefile.am")
        sources = files(lib_values.get(f"lib{libname}_la_SOURCES", ""))
        if not sources:
            sys.exit(f"lib{libname}_la_SOURCES lists no sources in {libdir}/Makefile.am")
        out += sources
else:
    sys.exit(f"{what}: sources or ldadd")
print(" ".join(f"{root}/{s}" for s in out))
