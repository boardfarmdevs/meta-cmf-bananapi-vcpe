from __future__ import annotations

from optimizer.candidates import (
    CandidateMetricsError,
    ControllerCandidateProvider,
    operating_class,
)
from optimizer.model import CandidateObservation, ClientObservation


STA = "02:00:00:00:03:00"
AGENT = "02:00:00:00:09:20"
RADIO = "02:00:00:00:09:00"
BSSID = "02:00:00:aa:aa:01"


def client() -> ClientObservation:
    return ClientObservation(
        sta_mac=STA,
        connected_device_id="02:00:00:00:08:20",
        connected_device_name="Extender-2",
        connected_bssid="02:00:00:bb:bb:01",
        rcpi=80,
        association_uptime_seconds=120,
        metric_observed_at="2026-08-21T20:00:00.000Z",
        measurement_source="associated_sta_link_metrics",
        band="5",
    )


def inventory() -> CandidateObservation:
    return CandidateObservation(
        sta_mac=STA,
        bssid=BSSID,
        device_id=AGENT,
        device_name="Extender-1",
        rcpi=None,
        metric_observed_at=None,
        measurement_source="controller_bss_inventory_only",
        band="5",
    )


def bsses():
    return [{
        "bssid": BSSID,
        "device_id": AGENT,
        "radio_id": RADIO,
        "band": 1,
        "channel": 36,
        "ssid": "private_ssid",
        "haul_type": "Fronthaul",
    }]


def response(simulated=True):
    return {
        "success": True,
        "provider": "hwsim-wmediumd-read-only",
        "simulated": simulated,
        "metrics": [{
            "agent_al": AGENT,
            "ruid": RADIO,
            "sta": STA,
            "opclass": 115,
            "channel": 36,
            "rcpi": 136,
            "received_at_ms": 1787342400123,
            "message_id": 42,
        }],
    }


def test_lab_operating_class_mapping_is_frequency_qualified():
    assert operating_class("2.4", 6) == 81
    assert operating_class("5", 36) == 115
    assert operating_class("5", 100) == 121
    assert operating_class("6", 5) == 131


def test_provider_batches_query_and_maps_ruid_to_exact_bssid():
    calls = []

    def request(url, payload):
        calls.append((url, payload))
        return response()

    provider = ControllerCandidateProvider(
        "http://controller", requester=request, allow_simulated=True
    )
    measured = list(provider(
        (client(),), (inventory(),), bsses(), "2026-08-21T20:00:01.000Z"
    ))
    assert calls == [(
        "http://controller/api/v1/unassoc_sta_query",
        {
            "AlMac": AGENT,
            "UnassocStaQueryList": [{
                "opclass": 115,
                "channels": [{"channel": 36, "sta_macs": [STA]}],
            }],
        },
    )]
    assert len(measured) == 1
    assert measured[0].bssid == BSSID
    assert measured[0].rcpi == 136
    assert measured[0].metric_observed_at == "2026-08-21T20:00:00.123Z"
    assert measured[0].measurement_source.endswith(":simulated")
    assert provider.last_raw[0]["response"]["metrics"][0]["message_id"] == 42


def test_simulated_candidate_source_requires_explicit_lab_opt_in():
    provider = ControllerCandidateProvider(
        "http://controller", requester=lambda _url, _payload: response()
    )
    try:
        list(provider(
            (client(),), (inventory(),), bsses(), "2026-08-21T20:00:01.000Z"
        ))
    except CandidateMetricsError as error:
        assert "--allow-simulated-candidates" in str(error)
    else:
        raise AssertionError("simulated metrics were accepted without opt-in")
