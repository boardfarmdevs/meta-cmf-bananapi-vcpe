"""em_cli's candidate query treats the controller's Error_Not_Ready as transient: a radio of the
agent busy with another command refuses it at once (series 0207), as on the K8's soak (10 October
02:32Z, a topology round in progress). submitCandidate (candidate_coordination.go) submits again
after 250 ms, then 500 ms, within the request's deadline, each counted as not_ready_retries; any
other refusal, or the third, is returned.

candidate_coordination.go as installed, with stubs for the few symbols it takes from em_cli's
cgo files, and TestNotReadyIsResubmittedTwiceWithinTheDeadline from candidate_coordination_test.go,
compiled and run with go test."""
from pathlib import Path
import os
import re
import shutil
import subprocess

import pytest

SOURCES = Path(__file__).resolve().parents[2] / "recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh"
STUBS = '''package main

type candidateLinkMetric struct{}
type candidateLinkError struct{}
type candidateCompletion struct{}

func loadCandidateLinkState() ([]candidateLinkMetric, []candidateLinkError, []candidateCompletion, error) {
	return nil, nil, nil, nil
}

func nativeSteeringAvailable() bool { return false }
'''


def go_test_function(source, name):
    start = source.index(f"func {name}(")
    return source[start:source.index("\n}\n", start) + 3]


@pytest.mark.skipif(shutil.which("go") is None, reason="Go toolchain required")
def test_not_ready_is_resubmitted_twice_within_the_deadline(tmp_path):
    (tmp_path / "candidate_coordination.go").write_text((SOURCES / "candidate_coordination.go").read_text())
    (tmp_path / "stubs.go").write_text(STUBS)
    test = go_test_function((SOURCES / "candidate_coordination_test.go").read_text(),
                            "TestNotReadyIsResubmittedTwiceWithinTheDeadline")
    (tmp_path / "retry_test.go").write_text(
        'package main\n\nimport (\n\t"fmt"\n\t"testing"\n\t"time"\n)\n\n' + test)
    environment = dict(os.environ, GO111MODULE="off", GOWORK="off", GOCACHE=str(tmp_path / "cache"))
    result = subprocess.run(["go", "test", "-run", "TestNotReadyIsResubmittedTwiceWithinTheDeadline", "-count=1", "."],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_handler_submits_through_the_retry_and_reports_it():
    coordination = (SOURCES / "candidate_coordination.go").read_text()
    assert 'NotReadyRetries     int     `json:"not_ready_retries"`' in coordination
    assert re.search(r"candidateNotReadyBackoff = \[\]time\.Duration\{250 \* time\.Millisecond, "
                     r"500 \* time\.Millisecond\}", coordination)
