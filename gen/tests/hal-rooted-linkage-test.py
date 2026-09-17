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
    "wifi_hal_backhaul_root_state", "wifi_hal_backhaul_root_revoke",
}
ROOT_IMPORTS = {
    "wifi_hal_backhaul_root_admit", "wifi_hal_backhaul_root_loss",
    "wifi_hal_backhaul_root_state", "wifi_hal_backhaul_root_revoke",
}


def symbols(text):
    defined, undefined = set(), set()
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 8 or not fields[0].rstrip(":").isdigit():
            continue
        name = fields[7].split("@", 1)[0]
        (undefined if fields[6] == "UND" else defined).add(name)
    return defined, undefined


def validate(hal, onewifi, hostap):
    hal_defined, hal_undefined = hal
    _, onewifi_undefined = onewifi
    hostap_defined, hostap_undefined = hostap
    missing = (ROOT_EXPORTS | {"get_radio_by_rdk_index"}) - hal_defined
    unresolved = {name for name in hal_undefined if name.startswith("get_radio_by_")}
    missing_imports = ROOT_IMPORTS - onewifi_undefined
    wds_helper = "hostapd_set_wds_encryption"
    invalid_wds = wds_helper not in hostap_defined or wds_helper in hostap_undefined
    if missing or unresolved or missing_imports or invalid_wds:
        raise ValueError(f"Native linkage mismatch: missing exports={sorted(missing)}, "
                         f"unresolved radio helpers={sorted(unresolved)}, "
                         f"missing OneWifi imports={sorted(missing_imports)}, "
                         f"invalid hostap WDS export={invalid_wds}")


def self_test():
    valid_hal = (ROOT_EXPORTS | {"get_radio_by_rdk_index"}, {"getrandom"})
    valid_onewifi = (set(), ROOT_IMPORTS)
    valid_hostap = ({"hostapd_set_wds_encryption"}, {"malloc"})
    validate(valid_hal, valid_onewifi, valid_hostap)
    rejected = 0
    for symbol in ROOT_EXPORTS | {"get_radio_by_rdk_index"}:
        try:
            validate((valid_hal[0] - {symbol}, valid_hal[1]), valid_onewifi, valid_hostap)
        except ValueError:
            rejected += 1
    for symbol in ("get_radio_by_index", "get_radio_by_unknown_index"):
        try:
            validate((valid_hal[0], valid_hal[1] | {symbol}), valid_onewifi, valid_hostap)
        except ValueError:
            rejected += 1
    for symbol in ROOT_IMPORTS:
        try:
            validate(valid_hal, (set(), ROOT_IMPORTS - {symbol}), valid_hostap)
        except ValueError:
            rejected += 1
    for invalid_hostap in ((set(), set()), (set(), valid_hostap[0]),
                          (valid_hostap[0], valid_hostap[0])):
        try:
            validate(valid_hal, valid_onewifi, invalid_hostap)
        except ValueError:
            rejected += 1
    assert rejected == 18
    assert symbols("  42: 00000000 0 FUNC GLOBAL DEFAULT UND getrandom@GLIBC_2.25 (2)\n"
                   "  43: 00001234 44 FUNC GLOBAL DEFAULT 12 get_radio_by_rdk_index\n") == (
                       {"get_radio_by_rdk_index"}, {"getrandom"})
    return {"passed": True, "cases": 20, "scope": "ELF symbol validation fixtures"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hal", type=Path)
    parser.add_argument("--onewifi", type=Path)
    parser.add_argument("--hostap", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
    else:
        if not args.hal or not args.onewifi or not args.hostap:
            parser.error("--hal, --onewifi and --hostap are required")
        reports = {}
        identities = {}
        for name, path in (("hal", args.hal), ("onewifi", args.onewifi), ("hostap", args.hostap)):
            reports[name] = symbols(subprocess.check_output(
                ["readelf", "--dyn-syms", "--wide", str(path)], text=True))
            identities[name] = {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        try:
            validate(reports["hal"], reports["onewifi"], reports["hostap"])
            result = {"passed": True, "binaries": identities, "root_exports": sorted(ROOT_EXPORTS),
                      "onewifi_imports": sorted(ROOT_IMPORTS), "unresolved_radio_helpers": [],
                      "hostap_wds_export": "hostapd_set_wds_encryption"}
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
