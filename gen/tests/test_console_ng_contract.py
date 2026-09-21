from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
OBSERVER = ROOT / "gen/wmediumd/observer"


def load_module(filename):
    spec = importlib.util.spec_from_file_location(filename.replace("-", "_"), OBSERVER / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConsoleNGContractTests(unittest.TestCase):
    def test_embedded_rf_guide_matches_source(self):
        renderer = load_module("build-manual.py")
        source = (ROOT / "doc/easymesh/reference/radio/console-rf-properties.md").read_text()
        rendered = (OBSERVER / "web/ng/rf-properties.html").read_text()
        self.assertIn(renderer.render(source), rendered)
        for anchor in ("directed-snr", "noise-reference-and-cca", "channel-utilization",
                       "advertised-beacon-bss-load", "room-exclusion-and-fronthaul-availability"):
            self.assertIn(f'id="{anchor}"', rendered)
        self.assertIn('href="/ng/manual.html"', rendered)

    def test_readiness_requires_matching_sources(self):
        readiness = load_module("check-ready.py")
        stamp = datetime.now(timezone.utc).isoformat()

        def report(data):
            return {"available": True, "observed_at": stamp, "data": data}

        document = {
            "daemon": {"instance_id": "one", "capabilities": ["explorer_details"]},
            "summary": {"available": True}, "identity_inventory": {"matched": "105"},
            "service": report({"airtime_profile": "legacy20"}),
            "room": report({"live": True, "instance_id": "one", "roles": [{"role": "station_1"}]}),
            "survey": report({"instance_id": "one", "reader_monotonic_ns": "1000001",
                              "recorded_monotonic_ns": "1000000", "written": [{"radio": "radio"}]}),
        }
        self.assertEqual(readiness.missing_sources(document, True, True), [])
        document["room"]["data"]["instance_id"] = "old"
        document["survey"]["data"]["reader_monotonic_ns"] = "5000000000"
        self.assertEqual(len(readiness.missing_sources(document, True, True)), 2)
        document["service"]["data"].clear()
        self.assertIn("live RF model/service telemetry", readiness.missing_sources(document))


if __name__ == "__main__":
    unittest.main()
