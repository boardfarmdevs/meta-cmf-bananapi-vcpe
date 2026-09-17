#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT_EXPORTS = {
    "wifi_hal_backhaul_root_admit", "wifi_hal_backhaul_root_blocked",
    "wifi_hal_backhaul_root_close", "wifi_hal_backhaul_root_link",
    "wifi_hal_backhaul_root_loss", "wifi_hal_backhaul_root_name_blocked",
    "wifi_hal_backhaul_root_state",
}
ROOT_IMPORTS = {
    "wifi_hal_backhaul_root_admit", "wifi_hal_backhaul_root_loss",
    "wifi_hal_backhaul_root_state",
}


def symbols(text):
    defined, undefined = set(), set()
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 8 or not fields[0].removesuffix(":").isdigit():
            continue
        name = fields[7].split("@", 1)[0]
        (undefined if fields[6] == "UND" else defined).add(name)
    return defined, undefined


def validate(hal, onewifi):
    hal_defined, hal_undefined = hal
    _, onewifi_undefined = onewifi
    missing = (ROOT_EXPORTS | {"get_radio_by_rdk_index"}) - hal_defined
    unresolved = {name for name in hal_undefined if name.startswith("get_radio_by_")}
    missing_imports = ROOT_IMPORTS - onewifi_undefined
    if missing or unresolved or missing_imports:
        raise ValueError(f"Native linkage mismatch: missing exports={sorted(missing)}, "
                         f"unresolved radio helpers={sorted(unresolved)}, "
                         f"missing OneWifi imports={sorted(missing_imports)}")


def self_test():
    valid_hal = (ROOT_EXPORTS | {"get_radio_by_rdk_index"}, {"getrandom"})
    valid_onewifi = (set(), ROOT_IMPORTS)
    validate(valid_hal, valid_onewifi)
    rejected = 0
    for symbol in ROOT_EXPORTS | {"get_radio_by_rdk_index"}:
        try:
            validate((valid_hal[0] - {symbol}, valid_hal[1]), valid_onewifi)
        except ValueError:
            rejected += 1
    for symbol in ("get_radio_by_index", "get_radio_by_unknown_index"):
        try:
            validate((valid_hal[0], valid_hal[1] | {symbol}), valid_onewifi)
        except ValueError:
            rejected += 1
    for symbol in ROOT_IMPORTS:
        try:
            validate(valid_hal, (set(), ROOT_IMPORTS - {symbol}))
        except ValueError:
            rejected += 1
    assert rejected == 13
    assert symbols("  42: 00000000 0 FUNC GLOBAL DEFAULT UND getrandom@GLIBC_2.25 (2)\n"
                   "  43: 00001234 44 FUNC GLOBAL DEFAULT 12 get_radio_by_rdk_index\n") == (
                       {"get_radio_by_rdk_index"}, {"getrandom"})
    return {"passed": True, "cases": 15, "scope": "ELF symbol validation fixtures"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hal", type=Path)
    parser.add_argument("--onewifi", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
    else:
        if not args.hal or not args.onewifi:
            parser.error("--hal and --onewifi are required")
        reports = {}
        identities = {}
        for name, path in (("hal", args.hal), ("onewifi", args.onewifi)):
            reports[name] = symbols(subprocess.check_output(
                ["readelf", "--dyn-syms", "--wide", str(path)], text=True))
            identities[name] = {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        try:
            validate(reports["hal"], reports["onewifi"])
            result = {"passed": True, "binaries": identities, "root_exports": sorted(ROOT_EXPORTS),
                      "onewifi_imports": sorted(ROOT_IMPORTS), "unresolved_radio_helpers": []}
        except ValueError as error:
            result = {"passed": False, "binaries": identities, "error": str(error)}
    if args.output:
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
