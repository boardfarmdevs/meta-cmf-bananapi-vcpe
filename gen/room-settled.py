#!/usr/bin/env python3
"""Whether the default room is settled, from the room service's current state.

    curl -fsS "$ROOM/api/demo/current" | python3 gen/room-settled.py [EXPECTED_CLIENTS]

Settled: the lab healthy with every expected client online (EXPECTED_CLIENTS, 20 by default),
and the optimizer converged with every client's measurement complete. One line on stdout,
`settled SCENARIO API_TOTAL CLIENTS_CHECKED CONVERGED`, exit 0; else the same with `waiting`,
exit 1.

One known gap is settled too, said by its own name: a client associated to an OpenSync pod
whose current link metric is missing (the optimizer's reason `current_metric_missing`). The
lab's pods publish no telemetry, so the controller has no associated link metric for their
clients (AP metrics are a documented limit); such a client is never checked, and the room
otherwise converged would wait for it forever (rdk-1010, 16 and 20 October). It is settled
only when every client not checked is one of those and nothing else holds the optimizer: the
roster complete, no client outside the policy margin, no load measurement missing for another
client. The same reason for a client on the gateway or an extender, or any other reason, still
waits. The line then ends `with the pods' known metric gap: ROLE on POD, ...`.
"""

from __future__ import annotations

import json
import re
import sys

POD = re.compile(r"pod_\d+$")  # the room's roles for the OpenSync pods' access points


def pod_metric_gap(decision: dict) -> bool:
    return decision.get("reason") == "current_metric_missing" and bool(
        POD.match(decision.get("source_role") or "")
    )


def verdict(current: dict, expected: int = 20) -> tuple[bool, str]:
    health = current.get("health") or {}
    optimizer = current.get("optimizer") or {}
    fleet = optimizer.get("fleet") or {}
    counts = " ".join(
        str(x)
        for x in (
            current.get("scenario"),
            health.get("api_total"),
            fleet.get("clients_checked"),
            fleet.get("converged"),
        )
    )
    lab = (
        health.get("healthy") is True
        and health.get("api_total") == expected
        and health.get("expected_online_clients") == expected
    )
    if (
        lab
        and fleet.get("converged")
        and fleet.get("measurement_complete")
        and fleet.get("clients_checked") == expected
    ):
        return True, f"settled {counts}"
    gap = [d for d in optimizer.get("client_decisions") or [] if pod_metric_gap(d)]
    gap_macs = {d.get("sta_mac") for d in gap}
    unavailable = set(fleet.get("load_measurements_unavailable") or ())
    if (
        lab
        and gap
        and fleet.get("roster_complete") is True
        and fleet.get("clients_evaluated") == expected
        and fleet.get("clients_checked") == expected - len(gap)
        and fleet.get("clients_outside_policy_margin") == 0
        and unavailable <= gap_macs
    ):
        named = ", ".join(f"{d.get('role')} on {d.get('source_role')}" for d in gap)
        return True, f"settled {counts} with the pods' known metric gap: {named}"
    return False, f"waiting {counts}"


def main(argv: list[str]) -> int:
    expected = int(argv[1]) if len(argv) > 1 else 20
    try:
        current = json.load(sys.stdin)
    except ValueError:
        print("waiting no answer")
        return 1
    ok, line = verdict(current, expected)
    print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
