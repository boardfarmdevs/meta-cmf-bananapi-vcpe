#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
path = args.source / "source/core/services/vap_svc_mesh_ext.c"
source = path.read_text()
callback = re.search(r"int process_ext_sta_conn_status\(.*?\n\}", source, re.S).group()
transition = re.search(
    r"else if \(\(ext->conn_state == connection_state_connected\)\) \{(.*?)\n        \}",
    callback, re.S).group(1)
scheduling = re.search(
    r"else if\(\(found_candidate == false\) && \(ext->conn_state != connection_state_connected\)\) \{(.*?)\n    \} else",
    callback, re.S).group(1)
algorithm = re.search(r"int process_ext_connect_algorithm\(.*?\n\}", source, re.S).group()
program = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#define wifi_util_dbg_print(...) ((void)0)
#define wifi_util_info_print(...) ((void)0)
typedef enum {
    connection_state_disconnected_steady, connection_state_disconnected_scan_list_none,
    connection_state_disconnected_scan_list_in_progress, connection_state_disconnected_scan_list_all,
    connection_state_connection_in_progress, connection_state_connection_to_lcb_in_progress,
    connection_state_connection_to_nb_in_progress, connection_state_connected,
    connection_state_connected_wait_for_csa, connection_state_connected_scan_list,
    connection_state_disconnection_in_progress
} connection_state_t;
typedef struct { connection_state_t conn_state; int ext_connect_algo_processor_id; } vap_svc_ext_t;
typedef struct { union { vap_svc_ext_t ext; } u; } vap_svc_t;
static int schedules, scans, connects, disconnects;
static void ext_set_conn_state(vap_svc_ext_t *ext, connection_state_t state, const char *name, int line) {
    (void)name; (void)line; ext->conn_state = state;
}
static void schedule_connect_sm(vap_svc_t *svc) { (void)svc; ++schedules; }
static void ext_start_scan(vap_svc_t *svc) { (void)svc; ++scans; }
static void ext_try_connecting(vap_svc_t *svc) { (void)svc; ++connects; }
static void ext_try_disconnecting(vap_svc_t *svc) { (void)svc; ++disconnects; }
static void ext_incomplete_scan_list(vap_svc_t *svc) { (void)svc; }
static void ext_process_scan_list(vap_svc_t *svc) { (void)svc; }
static void ext_wait_for_csa(vap_svc_t *svc) { (void)svc; }
static void ext_connected_scan(vap_svc_t *svc) { (void)svc; }
ALGORITHM
static void ordinary_disconnect_branch(vap_svc_t *svc) {
    vap_svc_ext_t *ext = &svc->u.ext;
    if (ext->conn_state == connection_state_connected) {
        TRANSITION
    }
    if (ext->conn_state != connection_state_connected) {
        SCHEDULING
    }
}
int main(void) {
    vap_svc_t service = {.u.ext = {.conn_state = connection_state_connected}};
    ordinary_disconnect_branch(&service);
    assert(service.u.ext.conn_state == connection_state_disconnected_scan_list_none && schedules == 1);
    assert(connects == 0 && scans == 0 && disconnects == 0);
    service.u.ext.ext_connect_algo_processor_id = 42;
    assert(process_ext_connect_algorithm(&service) == 0);
    assert(scans == 1 && connects == 0 && service.u.ext.ext_connect_algo_processor_id == 0);
    service.u.ext.conn_state = connection_state_connected;
    process_ext_connect_algorithm(&service);
    assert(scans == 1 && connects == 0);
    service.u.ext.conn_state = connection_state_connection_in_progress;
    process_ext_connect_algorithm(&service);
    assert(connects == 1 && scans == 1 && disconnects == 0);
    puts("PASS: actual ordinary-disconnect state/scheduling slices dispatch native scan, not fixed-parent connect");
}
'''.replace("ALGORITHM", algorithm).replace("TRANSITION", transition).replace("SCHEDULING", scheduling)
with tempfile.TemporaryDirectory(prefix="onewifi-root-recovery-") as directory:
    binary = Path(directory) / "test"
    compiled = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-x", "c", "-",
                               "-o", str(binary)], input=program, text=True, capture_output=True, timeout=30)
    executed = subprocess.run([str(binary)], text=True, capture_output=True, timeout=5) if compiled.returncode == 0 else None
    report = {"source": str(path.resolve()), "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "scope": "actual complete FSM dispatcher plus ordinary-disconnect transition/scheduling slices; scan and timers stubbed; not full callback or live recovery proof",
              "functions": {"process_ext_connect_algorithm": hashlib.sha256(algorithm.encode()).hexdigest(),
                            "process_ext_sta_conn_status": hashlib.sha256(callback.encode()).hexdigest()},
              "compile_exit": compiled.returncode, "compile_stderr": compiled.stderr,
              "run_exit": executed.returncode if executed else None,
              "stdout": executed.stdout if executed else "", "stderr": executed.stderr if executed else "",
              "passed": executed is not None and executed.returncode == 0}
    if args.output:
        with args.output.open("x") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    print(report["stdout"] or report["compile_stderr"] or report["stderr"], end="")
    raise SystemExit(0 if report["passed"] else 1)
