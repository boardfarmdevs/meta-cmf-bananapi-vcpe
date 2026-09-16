from copy import deepcopy

import pytest

from metric_freshness_analysis import client_read_window, summarize_action, summarize_native, summarize_run


def mark(seconds):
    return {"at": 1000 + seconds, "monotonic_ns": int(seconds * 1e9)}


def evidence():
    target = {"bssid": "target", "device_id": "agent", "band": "2.4"}
    action = {"decision": {"sta_mac": "station"}, "freshness_requirements": {"target": target},
              "timings": {"verification": {"finished": mark(0)}},
              "post_verify_freshness": {"target_metrics": None, "complete_snapshot": None}}
    cycle = {"cycle_index": 1, "timings": {
        "cycle": {"started": mark(1), "finished": mark(4), "elapsed_ms": 3000},
        "observer": {"started": mark(1), "finished": mark(3.9), "elapsed_ms": 2900},
        "candidates": {"started": mark(1.5), "finished": mark(3.9), "elapsed_ms": 2400}},
        "raw": {"clients": {}}, "snapshot": {"clients": [
            {"sta_mac": "station", "connected_bssid": "target", "connected_device_id": "agent",
             "band": "2.4", "rcpi": None, "metric_observed_at": None}]}}
    return action, cycle


def test_legacy_evidence_only_bounds_passive_reads_and_retains_missing_metrics():
    action, cycle = evidence()
    result = summarize_action(action, [cycle])
    row = result["post_verification_cycles"][0]
    assert row["client_read_after_verification_seconds"] == {"started": 1, "finished": 1.5}
    assert row["client_read_scope"] == "legacy-passive-stage-bound-only"
    assert row["client_read_to_cycle_finish_seconds"] == 2.5
    assert row["rcpi"] is None
    assert result["milestones_after_verification_seconds"]["complete_snapshot"] is None
    assert result["native_arrival_after_verification_seconds"] is None


def test_precise_reads_and_backdated_samples_do_not_invent_native_arrival():
    action, cycle = evidence()
    cycle["raw"]["api_timings"] = {"clients": {"started": mark(1.1), "finished": mark(1.2)}}
    cycle["snapshot"]["clients"][0].update(rcpi=144, metric_observed_at="1970-01-01T00:16:39Z")
    row = summarize_action(action, [cycle])["post_verification_cycles"][0]
    assert row["client_read_after_verification_seconds"] == {"started": 1.1, "finished": 1.2}
    assert row["reported_sample_after_verification_seconds"] == -1
    assert row["metric_observed_at"] == "1970-01-01T00:16:39Z"
    assert row["rcpi"] == 144


@pytest.mark.parametrize("change", ["owner", "duplicate", "missing"])
def test_ambiguous_or_wrong_owner_rows_cannot_supply_target_metrics(change):
    action, cycle = evidence()
    client = cycle["snapshot"]["clients"][0]
    client.update(rcpi=144, metric_observed_at="1970-01-01T00:16:41Z")
    if change == "owner":
        client["connected_bssid"] = "old"
    elif change == "duplicate":
        cycle["snapshot"]["clients"].append(deepcopy(client))
    else:
        cycle["snapshot"]["clients"] = []
    row = summarize_action(action, [cycle])["post_verification_cycles"][0]
    assert not row["same_target_owner"]
    assert row["rcpi"] is None


def test_failed_cycle_never_reuses_a_legacy_read_boundary():
    action, cycle = evidence()
    cycle["error"] = "controller offline"
    cycle.pop("snapshot")
    assert client_read_window(cycle) is None
    result = summarize_run({"actions": [action]}, [cycle])
    assert result["failed_cycles"] == 1
    assert result["actions"][0]["post_verification_cycles"][0]["error"] == "controller offline"


def test_source_rejection_is_preserved_as_a_missing_candidate():
    action, cycle = evidence()
    source = {"bssid": "source", "device_id": "old-agent", "band": "2.4"}
    action["freshness_requirements"]["candidates"] = [source]
    rejection = {"sta": "station", "error_code": 1, "received_at_ms": 1001000}
    cycle["candidate_transactions"] = [{"response": {"rejected": [rejection]}}]
    row = summarize_action(action, [cycle])["post_verification_cycles"][0]
    assert row["required_candidates_without_metrics"] == [source]
    assert row["candidate_rejections"] == [rejection]


def trace():
    profile = {"id": "fixture", "instructions": [[1, "aa"]]}
    profiles = {"rdk": {"fixture-sha": profile}}
    events = [{"kind": "identity", "stack": "rdk", "sha256": "fixture-sha", "profile": profile,
               "clock": "guest-monotonic", "boundary": "native-model-association-commit",
               "metric_boundary": "native-model-rcpi-store"}, {"kind": "ready"}]
    events.extend({"kind": "metric", "sta": "station", "bssid": "target", "associated": True,
                   "rcpi": 144, "monotonic_ns": seconds * 1000000000} for seconds in (1, 6, 11))
    events.append({"kind": "end", "records": 3, "emitted": 3, "lost": 0})
    return events, profiles


def test_unchanged_rcpi_writes_count_as_native_updates():
    events, profiles = trace()
    result = summarize_native(events, profiles)
    assert result["metric_records"] == 3
    assert result["metric_gap_seconds"] == {"count": 2, "minimum": 5, "median": 5, "maximum": 5}
    assert result["native_arrival_after_verification_seconds"] is None


def test_native_gaps_do_not_cross_reassociation_epochs():
    events, profiles = trace()
    events.insert(-1, {"kind": "commit", "sta": "station", "bssid": "target", "associated": False,
                       "monotonic_ns": 8000000000})
    events.insert(-1, {"kind": "commit", "sta": "station", "bssid": "target", "associated": True,
                       "monotonic_ns": 9000000000})
    events[-1].update(records=5, emitted=5)
    assert summarize_native(events, profiles)["metric_gap_seconds"]["count"] == 1


def test_native_handoff_matches_exact_owner_and_keeps_unobserved_store_missing():
    events, profiles = trace()
    events.insert(-1, {"kind": "commit", "sta": "station", "bssid": "other", "associated": True,
                       "monotonic_ns": 7000000000})
    events[-1].update(records=4, emitted=4)
    result = summarize_native(events, profiles)
    assert result["metric_records"] == 2
    assert result["association_to_first_store"][0]["first_target_rcpi_store_after_commit_ms"] is None
    events.insert(-1, {"kind": "metric", "sta": "station", "bssid": "other", "associated": True,
                       "rcpi": 144, "monotonic_ns": 12000000000})
    events[-1].update(records=5, emitted=5)
    result = summarize_native(events, profiles)
    assert result["association_to_first_store"][0]["first_target_rcpi_store_after_commit_ms"] == 5000


@pytest.mark.parametrize("failure", ["lost", "truncated", "count", "sha", "profile", "boundary"])
def test_native_analysis_rejects_unqualified_or_incomplete_traces(failure):
    events, profiles = trace()
    if failure == "lost":
        events[-1]["lost"] = 1
    elif failure == "truncated":
        events.pop()
    elif failure == "count":
        events[-1]["emitted"] = 4
    elif failure == "sha":
        events[0]["sha256"] = "unknown"
    elif failure == "profile":
        events[0]["profile"] = {"id": "other"}
    else:
        events[0]["metric_boundary"] = None
    with pytest.raises(ValueError):
        summarize_native(events, profiles)


def test_handler_residual_is_not_labeled_as_native_cadence():
    _action, cycle = evidence()
    cycle["candidate_transactions"] = [{"elapsed_ms": 405, "response": {"coordination": {
        "native_service_ms": 190, "native_queue_ms": 1, "elapsed_ms": 400}}}]
    result = summarize_run({}, [cycle])
    assert result["candidate_handler_other_ms"]["median"] == 209
    assert result["candidate_request_elapsed_ms"]["count"] == 0


def test_previous_candidates_on_failed_passive_cycle_are_not_current_evidence():
    _action, cycle = evidence()
    cycle["timings"].pop("candidates")
    cycle["error"] = "passive read failed"
    cycle["candidate_transactions"] = [{"elapsed_ms": 405}]
    result = summarize_run({}, [cycle])
    assert result["candidate_transactions_per_cycle"]["maximum"] == 0
    assert result["unattributed_candidate_transactions"] == 1
