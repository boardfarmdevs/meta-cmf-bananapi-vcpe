#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cxx", default="g++")
    parser.add_argument("--std", choices=("c++11", "c++14", "c++17"), default="c++11")
    arguments = parser.parse_args()
    header = arguments.header.resolve(strict=True)
    fixture = Path(__file__).with_suffix(".cpp").resolve(strict=True)
    report = {
        "header": str(header),
        "header_sha256": digest(header),
        "fixture": str(fixture),
        "fixture_sha256": digest(fixture),
        "runner_sha256": digest(Path(__file__)),
        "scope": "production codec and transaction matcher only; no AP enforcement or live qualification",
        "functions": ["encode", "decode", "controller_reply", "transaction_matcher::begin",
                      "transaction_matcher::observe", "transaction_matcher::accept",
                      "transaction_matcher::retry", "transaction_matcher::expired"],
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="rooted-admission-probe-") as temporary:
        executable = Path(temporary) / "probe-test"
        command = [arguments.cxx, f"-std={arguments.std}", "-O2", "-Wall", "-Wextra",
                   "-Werror", "-pedantic", f'-DPROBE_HEADER="{header}"',
                   str(fixture), "-o", str(executable)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        report["compile"] = {"command": command, "exit_code": compiled.returncode,
                             "stdout": compiled.stdout, "stderr": compiled.stderr}
        if compiled.returncode == 0:
            executed = subprocess.run([str(executable)], capture_output=True, text=True,
                                      timeout=15, check=False)
            report["run"] = {"exit_code": executed.returncode, "stdout": executed.stdout,
                             "stderr": executed.stderr}
            for line in executed.stdout.splitlines():
                status, separator, name = line.partition("\t")
                if not separator or status not in ("PASS", "FAIL"):
                    raise RuntimeError(f"Unexpected fixture output: {line!r}")
                report["cases"].append({"name": name, "passed": status == "PASS"})
    names = [case["name"] for case in report["cases"]]
    report["passed"] = sum(case["passed"] for case in report["cases"])
    report["total"] = len(report["cases"])
    report["status"] = "PASS" if (
        report["compile"]["exit_code"] == 0
        and report.get("run", {}).get("exit_code") == 0
        and report["total"] > 0
        and report["passed"] == report["total"]
        and len(set(names)) == len(names)
    ) else "FAIL"
    if arguments.output:
        with arguments.output.open("x") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
    print(f'{report["status"]}: {report["passed"]}/{report["total"]} compiled cases')
    if report["compile"]["exit_code"]:
        print(report["compile"]["stderr"])
    elif report["status"] != "PASS":
        print("\n".join(case["name"] for case in report["cases"] if not case["passed"]))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
