from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Callable, Iterable
import urllib.error
import urllib.request

from .model import (
    CandidateObservation,
    ClientObservation,
    format_time,
    normalize_band,
    normalize_mac,
)


JsonRequester = Callable[[str, dict[str, Any]], dict[str, Any]]

# The hwsim lab deliberately uses one fixed 20 MHz control channel per band.
# The controller's current model exposes Band but leaves Radio.Channel at zero;
# this mapping is therefore only legal behind the explicit simulated-provider
# opt-in.  A physical deployment must report its actual operating channel.
LAB_CONTROL_CHANNELS = {"2.4": 6, "5": 36, "6": 5}


class CandidateMetricsError(RuntimeError):
    """The controller could not produce a trustworthy candidate snapshot."""


def operating_class(band: str | int, channel: int) -> int:
    """Return the 20 MHz global operating class used by the lab radio."""
    normalized = normalize_band(band)
    if normalized == "2.4" and 1 <= channel <= 13:
        return 81
    if normalized == "5":
        if 36 <= channel <= 48:
            return 115
        if 52 <= channel <= 64:
            return 118
        if 100 <= channel <= 144:
            return 121
        if 149 <= channel <= 161:
            return 124
        if channel in (165, 169, 173, 177):
            return 125
    if normalized == "6" and 1 <= channel <= 233:
        return 131
    raise CandidateMetricsError(
        f"no supported 20 MHz operating class for band={normalized} channel={channel}"
    )


def _default_request(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:  # nosec B310
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error)
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = {"message": error.read().decode(errors="replace")}
        raise CandidateMetricsError(
            f"candidate query failed with HTTP {error.code}: {detail}"
        ) from error
    except (OSError, TimeoutError, json.JSONDecodeError) as error:
        raise CandidateMetricsError(f"candidate query failed: {error}") from error


def _metric_time(milliseconds: Any) -> str:
    try:
        value = int(milliseconds)
    except (TypeError, ValueError) as error:
        raise CandidateMetricsError("candidate metric has no receipt timestamp") from error
    if value <= 0:
        raise CandidateMetricsError("candidate metric has an invalid receipt timestamp")
    return format_time(datetime.fromtimestamp(value / 1000, tz=timezone.utc))


class ControllerCandidateProvider:
    """Collect active EasyMesh candidate measurements and map them to BSSIDs."""

    def __init__(
        self,
        base_url: str,
        *,
        requester: JsonRequester | None = None,
        allow_simulated: bool = False,
    ) -> None:
        self.url = base_url.rstrip("/") + "/api/v1/unassoc_sta_query"
        self.requester = requester or _default_request
        self.allow_simulated = allow_simulated
        self.last_raw: list[dict[str, Any]] = []

    def _channel(self, raw: dict[str, Any]) -> int:
        channel = int(raw.get("channel") or 0)
        if channel > 0:
            return channel
        band = normalize_band(raw.get("band"))
        if self.allow_simulated and band in LAB_CONTROL_CHANNELS:
            return LAB_CONTROL_CHANNELS[band]
        raise CandidateMetricsError(
            f"BSS {raw.get('bssid', '<unknown>')} has no operating channel; "
            "the controller must report it for a physical candidate query"
        )

    def __call__(
        self,
        clients: tuple[ClientObservation, ...],
        inventory: tuple[CandidateObservation, ...],
        bsses: list[dict[str, Any]],
        observed_at: str,
    ) -> Iterable[CandidateObservation]:
        del observed_at  # individual controller receipt times are authoritative
        clients_by_mac = {item.sta_mac: item for item in clients}
        bss_by_id = {
            normalize_mac(item["bssid"]): item
            for item in bsses
            if item.get("bssid")
        }
        targets: dict[
            tuple[str, str, str, int, int], list[CandidateObservation]
        ] = {}
        query_groups: dict[
            tuple[str, str], dict[tuple[int, int], set[str]]
        ] = {}

        for candidate in inventory:
            raw = bss_by_id.get(candidate.bssid)
            client = clients_by_mac.get(candidate.sta_mac)
            if raw is None or client is None:
                continue
            # An Unassociated STA Link Metrics Query asks a candidate radio to
            # hear the STA on the channel where it is currently transmitting.
            # It is a same-band candidate primitive, not evidence that an
            # associated STA would work on a different band.  Cross-band
            # policy needs beacon/probe/capability observations instead.
            if candidate.band != client.band:
                continue
            agent = normalize_mac(raw["device_id"])
            radio = normalize_mac(raw["radio_id"])
            channel = self._channel(raw)
            opclass = operating_class(raw.get("band"), channel)
            targets.setdefault(
                (agent, radio, candidate.sta_mac, opclass, channel), []
            ).append(candidate)
            # OneWifi routes GetNaSta through one VAP.  A single EasyMesh query
            # must therefore remain on one agent radio; combining opclasses
            # from different radios is rejected by the agent.
            query_groups.setdefault((agent, radio), {}).setdefault(
                (opclass, channel), set()
            ).add(candidate.sta_mac)

        measured: list[CandidateObservation] = []
        self.last_raw = []
        for (agent, query_radio), groups in sorted(query_groups.items()):
            by_opclass: dict[int, list[dict[str, Any]]] = {}
            for (opclass, channel), stations in sorted(groups.items()):
                by_opclass.setdefault(opclass, []).append(
                    {"channel": channel, "sta_macs": sorted(stations)}
                )
            payload = {
                "AlMac": agent,
                "UnassocStaQueryList": [
                    {"opclass": opclass, "channels": channels}
                    for opclass, channels in sorted(by_opclass.items())
                ],
            }
            response = self.requester(self.url, payload)
            self.last_raw.append({
                "request": payload,
                "query_radio": query_radio,
                "response": response,
            })
            if response.get("success") is not True:
                raise CandidateMetricsError(
                    f"candidate query for {agent} was not successful: {response}"
                )
            if response.get("simulated") is True and not self.allow_simulated:
                raise CandidateMetricsError(
                    "controller returned simulated candidate metrics; "
                    "use --allow-simulated-candidates only in the hwsim lab"
                )
            provider = str(response.get("provider") or "unknown")
            simulated = response.get("simulated") is True
            source = f"easy_mesh_unassociated_sta_link_metrics:{provider}"
            if simulated:
                source += ":simulated"

            for metric in response.get("metrics", []):
                metric_agent = normalize_mac(metric["agent_al"])
                radio = normalize_mac(metric["ruid"])
                sta = normalize_mac(metric["sta"])
                opclass = int(metric["opclass"])
                channel = int(metric["channel"])
                rcpi = int(metric["rcpi"])
                if metric_agent != agent:
                    raise CandidateMetricsError(
                        f"candidate response agent {metric_agent} does not match {agent}"
                    )
                if not 0 <= rcpi <= 220:
                    raise CandidateMetricsError(f"candidate RCPI is invalid: {rcpi}")
                mapped = targets.get((agent, radio, sta, opclass, channel), [])
                for candidate in mapped:
                    measured.append(
                        CandidateObservation(
                            sta_mac=sta,
                            bssid=candidate.bssid,
                            device_id=candidate.device_id,
                            device_name=candidate.device_name,
                            rcpi=rcpi,
                            metric_observed_at=_metric_time(metric.get("received_at_ms")),
                            measurement_source=source,
                            band=candidate.band,
                        )
                    )
        return measured
