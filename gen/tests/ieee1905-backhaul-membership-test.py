#!/usr/bin/env python3
import argparse
from pathlib import Path
import re
import subprocess
import textwrap


parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path)
parser.add_argument("--regression-source", type=Path)
arguments = parser.parse_args()
root = arguments.source.resolve()
regressions = (arguments.regression_source or root).resolve()
proxy = (root / "ieee1905-core/src/cmdu_proxy.rs").read_text()
test_proxy = (regressions / "ieee1905-core/src/cmdu_proxy.rs").read_text()
test_codec = (regressions / "ieee1905-core/src/cmdu_codec.rs").read_text()
implementation = re.search(r"async fn inject_topology_response_tlvs\([\s\S]*?\n\}", proxy).group()
imports = """use ieee1905::cmdu_codec::*;
use ieee1905::tlv_cmdu_codec::{TLV, TLVTrait};
use ieee1905::topology_manager::{TopologyDatabase, Ieee1905DeviceData, Ieee1905LocalInterface, UpdateType};
use pnet::datalink::MacAddr;
use std::collections::HashMap;
"""
tests = []
for name in [
    "topology_response_preserves_live_hle_wifi_membership",
    "topology_response_rejects_unbound_or_incomplete_membership",
    "test_inject_topology_response_tlvs_failure",
    "test_inject_topology_response_tlvs_clear",
    "test_inject_topology_response_tlvs",
]:
    method = re.search(r"    async fn " + name + r"\([\s\S]*?\n    \}", test_proxy).group()
    tests.append("#[tokio::test]\n" + textwrap.dedent(method))
method = re.search(r"    fn modern_wifi_membership_round_trip_preserves_supplied_bytes\([\s\S]*?\n    \}", test_codec).group()
tests.append("#[test]\n" + textwrap.dedent(method))
target = root / "ieee1905-core/tests/backhaul_membership_regression.rs"
target.parent.mkdir(exist_ok=True)
with target.open("x") as output:
    output.write(imports + implementation + "\n" + "\n".join(tests) + "\n")
try:
    subprocess.run(["cargo", "test", "--offline", "--locked", "-p", "ieee1905",
                    "--test", "backhaul_membership_regression"], cwd=root, check=True)
finally:
    target.unlink()
