#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def matching(text, opening, left="{", right="}"):
    depth = 0
    position = opening
    mode = "code"
    while position < len(text):
        current = text[position]
        following = text[position:position + 2]
        if mode == "line":
            if current == "\n":
                mode = "code"
        elif mode == "block":
            if following == "*/":
                mode = "code"
                position += 1
        elif mode in ("'", '"'):
            if current == "\\":
                position += 1
            elif current == mode:
                mode = "code"
        elif following == "//":
            mode = "line"
            position += 1
        elif following == "/*":
            mode = "block"
            position += 1
        elif current in ("'", '"'):
            mode = current
        elif current == left:
            depth += 1
        elif current == right:
            depth -= 1
            if depth == 0:
                return position + 1
        position += 1
    raise ValueError("Unbalanced production source")


def function(text, name):
    expression = re.compile(r"(?m)^(?:static\s+)?[A-Za-z_][\w\s*]*?\b" + re.escape(name) + r"\s*\(")
    for found in expression.finditer(text):
        opening = text.find("(", found.start())
        close = matching(text, opening, "(", ")")
        body = close
        while body < len(text) and text[body].isspace():
            body += 1
        if text[body:body + 1] == "{":
            end = matching(text, body)
            return found.start(), end, text[found.start():end]
    raise ValueError(f"Production function missing: {name}")


def guards(sources):
    checks = []
    wanted = {
        "wifi_hal.c": ("wifi_hal_setRadioOperatingParameters", "wifi_hal_createVAP"),
        "wifi_hal_hostapd.c": ("start_bss",),
        "wifi_hal_nl80211_utils.c": ("restart_interface",),
        "wifi_hal_nl80211.c": ("wifi_drv_set_ap", "nl80211_interface_enable"),
    }
    for filename, names in wanted.items():
        for name in names:
            if name == "wifi_hal_createVAP":
                start = sources[filename].index("INT wifi_hal_createVAP(")
                end = sources[filename].index("\n}", start) + 2
                body = sources[filename][start:end]
            else:
                start, end, body = function(sources[filename], name)
            guarded = "wifi_hal_backhaul_root_blocked" in body or "wifi_hal_backhaul_root_name_blocked" in body
            required_count = 2 if name == "wifi_hal_createVAP" else 1
            found_count = body.count("wifi_hal_backhaul_root_blocked") + body.count("wifi_hal_backhaul_root_name_blocked")
            checks.append({"name": f"static.{name}.guard-present", "passed": guarded and found_count >= required_count,
                           "source": filename, "line": sources[filename].count("\n", 0, start) + 1,
                           "function_sha256": sha(body.encode()), "guard_count": found_count,
                           "scope": "static guard presence only, not dynamic domination or concurrency proof"})
    start, _, body = function(sources["wifi_hal_nl80211_utils.c"], "reload_interface")
    checks.append({"name": "static.reload-hostapd-before-stop", "passed":
                   0 <= body.find("hostapd_reload_config(") < body.find("nl80211_enable_ap(interface, false)"),
                   "source": "wifi_hal_nl80211_utils.c", "function_sha256": sha(body.encode()),
                   "line": sources["wifi_hal_nl80211_utils.c"].count("\n", 0, start) + 1,
                   "scope": "actual reload invokes hostapd reload before STOP_AP; over-air deauthentication not proven"})
    return checks


def callback_guard(source):
    text = source.decode()
    start, end, body = function(text, "process_ext_sta_conn_status")
    branch = re.search(r"if\s*\(sta_data->stats\.connect_status\s*==\s*wifi_connection_status_connected\)\s*\{", body)
    guarded = False
    if branch:
        branch_end = matching(body, branch.end() - 1)
        guarded = re.search(r"wifi_hal_backhaul_root_loss\s*\(\s*sta_data->stats\.vap_index\s*\)",
                            body[branch.end():branch_end]) is not None
    guarded = guarded or re.search(
        r"sta_data->stats\.connect_status\s*==\s*wifi_connection_status_connected\s*&&\s*"
        r"wifi_hal_backhaul_root_loss\s*\(\s*sta_data->stats\.vap_index\s*\)", body) is not None
    return {"name": "static.onewifi.connected-callback-quiesce", "passed": guarded,
            "line": text.count("\n", 0, start) + 1, "function_sha256": sha(body.encode()),
            "scope": "static connected-status conditional call, not full callback execution or error-propagation proof"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--onewifi-source-dir", type=Path)
    arguments = parser.parse_args()
    source_dir = arguments.source_dir.resolve(strict=True)
    source_dir = source_dir / "src" if (source_dir / "src").is_dir() else source_dir
    files = ("wifi_hal.c", "wifi_hal_hostapd.c", "wifi_hal_nl80211_utils.c", "wifi_hal_nl80211.c")
    snapshots = {name: (source_dir / name).read_bytes() for name in files}
    sources = {name: data.decode() for name, data in snapshots.items()}
    core = sources["wifi_hal.c"]
    names = re.findall(r"(?m)^(?:static\s+)?(?:bool|INT|int|void|uint64_t)\s+((?:wifi_hal_)?backhaul_root_\w+)\s*\(", core)
    if not names:
        raise ValueError("No actual rooted-admission production functions")
    metadata = []
    for name in names + ["wifi_hal_connect", "wifi_hal_disconnect"]:
        start, end, body = function(core, name)
        metadata.append({"name": name, "source": str(source_dir / "wifi_hal.c"),
                         "line": core.count("\n", 0, start) + 1, "sha256": sha(body.encode())})
    block_start = core.index("static pthread_mutex_t backhaul_root_lock")
    _, block_end, _ = function(core, "wifi_hal_connect")
    production = core[block_start:block_end] + "\n\n" + function(core, "wifi_hal_disconnect")[2]
    production = ("#define HAVE_ROOT_REVOKE " + str(int("wifi_hal_backhaul_root_revoke" in names))
                  + "\n" + production)
    interface_start, _, interface_function = function(sources["wifi_hal_nl80211.c"], "nl80211_interface_enable")
    metadata.append({"name": "nl80211_interface_enable", "source": str(source_dir / "wifi_hal_nl80211.c"),
                     "line": sources["wifi_hal_nl80211.c"].count("\n", 0, interface_start) + 1,
                     "sha256": sha(interface_function.encode())})
    fixture = Path(__file__).with_suffix(".c").resolve(strict=True)
    template = fixture.read_text()
    generated = template.replace("PRODUCTION_FUNCTIONS", production + "\n\n" + interface_function)
    if generated == template:
        raise ValueError("Missing fixture insertion marker")
    report = {"scope": "extracted actual HAL C; kernel/hostapd/RNG/maps are deterministic stubs; no live AP proof",
              "sources": [{"path": str(source_dir / name), "sha256": sha(data)} for name, data in snapshots.items()],
              "functions": metadata, "fixture": str(fixture), "fixture_sha256": sha(fixture.read_bytes()),
              "runner_sha256": sha(Path(__file__).read_bytes()), "generated_sha256": sha(generated.encode()),
              "cases": [], "static_checks": guards(sources)}
    onewifi_path = None
    onewifi_source = None
    if arguments.onewifi_source_dir:
        onewifi_path = arguments.onewifi_source_dir.resolve(strict=True) / "source/core/services/vap_svc_mesh_ext.c"
        onewifi_source = onewifi_path.read_bytes()
        report["sources"].append({"path": str(onewifi_path), "sha256": sha(onewifi_source)})
        check = callback_guard(onewifi_source)
        check["source"] = str(onewifi_path)
        report["static_checks"].append(check)
    with tempfile.TemporaryDirectory(prefix="hal-rooted-admission-") as temporary:
        source = Path(temporary) / "production-test.c"
        binary = Path(temporary) / "production-test"
        source.write_text(generated)
        command = [arguments.cc, "-std=c11", "-D_DEFAULT_SOURCE", "-O0", "-g", "-Wall", "-Wextra",
                   "-Werror", "-pthread", str(source), "-o", str(binary)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        report["compile"] = {"command": command, "exit_code": compiled.returncode,
                             "stdout": compiled.stdout, "stderr": compiled.stderr}
        if compiled.returncode == 0:
            listed = subprocess.run([str(binary), "--list"], capture_output=True, text=True, timeout=5, check=True)
            for case in listed.stdout.splitlines():
                result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=5, check=False)
                report["cases"].append({"name": case, "passed": result.returncode == 0,
                                        "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    report["sources_unchanged"] = all((source_dir / name).read_bytes() == content for name, content in snapshots.items())
    if onewifi_path is not None:
        report["sources_unchanged"] = report["sources_unchanged"] and onewifi_path.read_bytes() == onewifi_source
    report["passed"] = sum(case["passed"] for case in report["cases"])
    report["total"] = len(report["cases"])
    report["status"] = "PASS" if (report["compile"]["exit_code"] == 0 and report["total"] > 0
        and report["passed"] == report["total"] and report["sources_unchanged"]
        and all(check["passed"] for check in report["static_checks"])) else "FAIL"
    with arguments.output.open("x") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(f'{report["status"]}: {report["passed"]}/{report["total"]} actual-body cases; '
          f'sources unchanged={report["sources_unchanged"]}')
    if report["compile"]["exit_code"]:
        print(report["compile"]["stderr"])
    for case in report["cases"]:
        if not case["passed"]:
            print(case["name"], case["stdout"], case["stderr"])
    for check in report["static_checks"]:
        if not check["passed"]:
            print("FAIL", check["name"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
