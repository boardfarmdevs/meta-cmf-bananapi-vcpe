from __future__ import annotations

from datetime import datetime, timezone

from optimizer.observer import ControllerObserver


def test_controller_observer_does_not_claim_api_serialization_time_is_metric_time():
    payloads = {
        "/api/v1/topology": {
            "nodes": [
                {
                    "id": "02:00:00:00:09:20",
                    "name": "Extender-1",
                    "STAList": [
                        {
                            "staMAC": "02:00:00:00:03:00",
                            "band": 1,
                            "ssid": "private_ssid",
                        }
                    ],
                    "haulTypes": [],
                }
            ]
        },
        "/api/v1/clients": {
            "clients": [
                {
                    "mac": "02:00:00:00:03:00",
                    "connected_ap_mac": "02:00:00:00:09:20",
                    "connected_bssid": "02:00:00:aa:aa:01",
                    "client_metrics": {
                        "rcpi": 138,
                        "association_uptime_seconds": 42,
                        "last_updated": "2026-08-20T20:00:00Z",
                    },
                }
            ]
        },
        "/api/v1/devices": {
            "devices": [
                {"role": "Controller"},
                {"role": "Agent-1"},
                {"role": "Extender-1"},
                {"role": "Extender-2"},
                {"role": "Extender-3"},
                {"role": "Extender-4"},
            ]
        },
        "/api/v1/bsses": {"bsses": [], "total": 0},
    }

    def fetch(url):
        return payloads[url.removeprefix("http://controller")]

    observer = ControllerObserver(
        "http://controller",
        fetcher=fetch,
        clock=lambda: datetime(2026, 8, 20, 20, 0, tzinfo=timezone.utc),
    )
    result = observer.observe()
    assert result.health.devices == 5
    assert result.health.clients == 1
    assert result.clients[0].rcpi == 138
    assert result.clients[0].band == "5"
    assert result.clients[0].metric_observed_at is None
    assert result.candidates == ()
    assert observer.last_raw["clients"] is payloads["/api/v1/clients"]


def test_controller_inventory_keeps_cross_band_bssid_candidates():
    topology = {
        "nodes": [
            {
                "id": "02:00:00:00:09:20",
                "name": "Extender-1",
                "STAList": [{
                    "staMAC": "02:00:00:00:03:00",
                    "band": 0,
                    "ssid": "private_ssid",
                }],
                "haulTypes": [],
            }
        ]
    }
    payloads = {
        "/api/v1/topology": topology,
        "/api/v1/clients": {"clients": [{
            "mac": "02:00:00:00:03:00",
            "connected_bssid": "02:00:00:aa:aa:01",
            "client_metrics": {"rcpi": 138, "association_uptime_seconds": 42},
        }]},
        "/api/v1/devices": {"devices": [{
            "mac": "02:00:00:00:09:20", "role": "Extender-1",
        }]},
        "/api/v1/bsses": {"bsses": [
            {"bssid": "02:00:00:aa:aa:01", "device_id": "02:00:00:00:09:20",
             "radio_id": "02:00:00:00:09:00", "band": 0, "channel": 6,
             "ssid": "private_ssid", "haul_type": "Fronthaul"},
            {"bssid": "02:00:00:bb:bb:01", "device_id": "02:00:00:00:09:20",
             "radio_id": "02:00:00:00:09:00", "band": 1, "channel": 36,
             "ssid": "private_ssid", "haul_type": "Fronthaul"},
            {"bssid": "02:00:00:cc:cc:01", "device_id": "02:00:00:00:09:20",
             "radio_id": "02:00:00:00:09:00", "band": 3, "channel": 37,
             "ssid": "private_ssid", "haul_type": "Fronthaul"},
        ], "total": 3},
    }
    observer = ControllerObserver(
        "http://controller",
        fetcher=lambda url: payloads[url.removeprefix("http://controller")],
        clock=lambda: datetime(2026, 8, 20, 20, 0, tzinfo=timezone.utc),
    )
    result = observer.observe()
    assert result.clients[0].band == "2.4"
    assert [(item.bssid, item.band) for item in result.candidates] == [
        ("02:00:00:bb:bb:01", "5"),
        ("02:00:00:cc:cc:01", "6"),
    ]
    assert all(item.rcpi is None for item in result.candidates)
    assert all(
        item.measurement_source == "controller_bss_inventory_only"
        for item in result.candidates
    )
    assert all(item.device_name == "Extender-1" for item in result.candidates)
