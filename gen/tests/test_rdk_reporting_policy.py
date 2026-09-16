import importlib.util
from pathlib import Path
import struct

from optimizer.load_capture import NativeLoadDecoder


SPEC = importlib.util.spec_from_file_location(
    "rdk_reporting_policy", Path(__file__).with_name("rdk-reporting-policy-acceptance.py"))
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)
SOURCE = "02:00:00:00:00:01"
TARGET = "02:00:00:00:00:02"


def test_query_encoding_preserves_bssid_and_message_id():
    payload = bytes.fromhex("93000701aabbccddeeff")
    frame = DRIVER.frame_for(SOURCE, TARGET, 0x800B, 0x1234, payload)
    assert frame == bytes.fromhex(
        "020000000002020000000001893a0000800b1234008093000701aabbccddeeff000000")
    decoded = DRIVER.decode_frame(frame)
    assert decoded["message_id"] == 0x1234
    assert decoded["type"] == 0x800B
    assert decoded["source"] == SOURCE and decoded["destination"] == TARGET


def test_wire_policy_threshold_is_separate_from_rcpi_and_inclusion():
    radio = bytes.fromhex("aabbccddeeff000580c0")
    payload = bytes.fromhex("8a000c7801") + radio
    record = DRIVER.decode_frame(DRIVER.frame_for(SOURCE, TARGET, 0x8003, 77, payload))
    assert record["policy"] == {"interval": 120, "radios": [
        {"ruid": "aa:bb:cc:dd:ee:ff", "rcpi": 0, "hysteresis": 5,
         "utilization": 128, "inclusion": 192}]}


def test_truncated_or_count_mismatched_policy_cannot_prove_delivery():
    for payload in (bytes.fromhex("8a000c7801"), bytes.fromhex("8a00027801")):
        assert DRIVER.decode_frame(DRIVER.frame_for(SOURCE, TARGET, 0x8003, 77, payload)) is None


def test_periodic_response_cannot_match_a_query_by_bssid_alone():
    load = bytes.fromhex("aabbccddeeff") + struct.pack("!BHB", 32, 2, 0)
    payload = struct.pack("!BH", 0x94, len(load)) + load
    frame = DRIVER.frame_for(TARGET, SOURCE, 0x800C, 99, payload)
    record = DRIVER.decode_frame(frame)
    decoded = NativeLoadDecoder().feed(frame, 1)
    assert record["message_id"] == decoded["message_id"] == 99
    assert record["message_id"] != 77
    assert decoded["loads"] == [{"bssid": "aa:bb:cc:dd:ee:ff", "utilization": 32, "station_count": 2}]
    record["report"] = decoded
    assert not DRIVER.query_matches(record, 77, "aa:bb:cc:dd:ee:ff", 32)
    assert not DRIVER.query_matches(record, 99, "aa:bb:cc:dd:ee:ff", 224)
    assert DRIVER.query_matches(record, 99, "aa:bb:cc:dd:ee:ff", 32)
    decoded["loads"].append({"bssid": "aa:bb:cc:dd:ee:00", "utilization": 32})
    assert not DRIVER.query_matches(record, 99, "aa:bb:cc:dd:ee:ff", 32)
