from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Callable, Iterable
from urllib.request import urlopen

from .model import (
    CandidateObservation,
    ClientObservation,
    MeshHealth,
    Snapshot,
    format_time,
    normalize_band,
    normalize_mac,
    sorted_candidates,
    sorted_clients,
)


JsonFetcher = Callable[[str], dict[str, Any]]
CandidateProvider = Callable[
    [tuple[ClientObservation, ...], str], Iterable[CandidateObservation]
]


def _default_fetch(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=5) as response:  # nosec: operator-supplied lab endpoint
        return json.load(response)


def _topology_client_context(topology: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for node in topology.get("nodes", []):
        for sta in node.get("STAList", []) or []:
            mac = sta.get("staMAC")
            if not mac:
                continue
            result[mac.lower()] = {
                "device_id": (node.get("id") or "").lower(),
                "device_name": node.get("name") or "",
                "band": normalize_band(sta.get("band")),
                "ssid": sta.get("ssid") or "",
            }
    return result


def _topology_bsses(topology: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in topology.get("nodes", []):
        for haul in node.get("haulTypes", []) or []:
            if (haul.get("name") or "").lower() != "fronthaul":
                continue
            for bss in haul.get("BSSList", []) or []:
                bssid = bss.get("BSSID")
                if bssid:
                    result.append(
                        {
                            "bssid": bssid.lower(),
                            "device_id": (node.get("id") or "").lower(),
                            "device_name": node.get("name") or "",
                            "band": normalize_band(bss.get("Band")),
                            "ssid": bss.get("ssid") or haul.get("ssid") or "",
                        }
                    )
    return result


class ControllerObserver:
    """Read and normalize controller APIs without consulting simulator truth."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8888",
        *,
        fetcher: JsonFetcher | None = None,
        candidate_provider: CandidateProvider | None = None,
        trust_api_metric_timestamp: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.fetcher = fetcher or _default_fetch
        self.candidate_provider = candidate_provider
        self.trust_api_metric_timestamp = trust_api_metric_timestamp
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sequence = 0
        self.last_raw: dict[str, Any] | None = None

    def _get(self, path: str) -> dict[str, Any]:
        return self.fetcher(f"{self.base_url}{path}")

    def observe(self) -> Snapshot:
        observed_at = format_time(self.clock())
        topology = self._get("/api/v1/topology")
        clients_payload = self._get("/api/v1/clients")
        devices_payload = self._get("/api/v1/devices")
        self.last_raw = {
            "sampled_at": observed_at,
            "topology": topology,
            "clients": clients_payload,
            "devices": devices_payload,
        }
        context = _topology_client_context(topology)
        bsses = _topology_bsses(topology)

        clients: list[ClientObservation] = []
        for item in clients_payload.get("clients", []):
            mac = normalize_mac(item["mac"])
            placement = context.get(mac, {})
            metrics = item.get("client_metrics") or {}
            raw_rcpi = metrics.get("rcpi")
            rcpi = int(raw_rcpi) if raw_rcpi not in (None, 0) else None
            raw_metric_time = metrics.get("last_updated")
            metric_time = (
                raw_metric_time
                if self.trust_api_metric_timestamp
                and raw_metric_time
                and not raw_metric_time.startswith("0001-")
                else None
            )
            clients.append(
                ClientObservation(
                    sta_mac=mac,
                    connected_device_id=(
                        item.get("connected_ap_mac")
                        or placement.get("device_id")
                        or ""
                    ).lower(),
                    connected_device_name=placement.get("device_name") or "",
                    connected_bssid=normalize_mac(item["connected_bssid"]),
                    rcpi=rcpi,
                    association_uptime_seconds=int(
                        metrics.get("association_uptime_seconds") or 0
                    ),
                    metric_observed_at=metric_time,
                    measurement_source="associated_sta_link_metrics",
                    band=placement.get("band"),
                )
            )
        normalized_clients = sorted_clients(clients)

        candidates: list[CandidateObservation] = []
        for client in normalized_clients:
            placement = context.get(client.sta_mac, {})
            for bss in bsses:
                if bss["bssid"] == client.connected_bssid:
                    continue
                if placement and bss["ssid"] != placement.get("ssid"):
                    continue
                candidates.append(
                    CandidateObservation(
                        sta_mac=client.sta_mac,
                        bssid=bss["bssid"],
                        device_id=bss["device_id"],
                        device_name=bss["device_name"],
                        rcpi=None,
                        metric_observed_at=None,
                        measurement_source="topology_inventory_only",
                        band=bss["band"],
                    )
                )
        if self.candidate_provider is not None:
            measured = list(self.candidate_provider(normalized_clients, observed_at))
            measured_keys = {(item.sta_mac, item.bssid) for item in measured}
            candidates = [
                item
                for item in candidates
                if (item.sta_mac, item.bssid) not in measured_keys
            ] + measured

        devices = devices_payload.get("devices", [])
        mesh_devices = sum(
            1 for item in devices if (item.get("role") or "").lower() != "controller"
        )
        snapshot = Snapshot(
            schema_version=1,
            sequence=self.sequence,
            observed_at=observed_at,
            controller_url=self.base_url,
            health=MeshHealth(
                devices=mesh_devices,
                clients=len(normalized_clients),
                radios=None,
                bsses=len(bsses) if bsses else None,
            ),
            clients=normalized_clients,
            candidates=sorted_candidates(candidates),
        )
        self.sequence += 1
        return snapshot
