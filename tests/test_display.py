import json
from pathlib import Path

import pytest

from openpw2.display import decode_status

from .fake_pw2 import status_body


def test_real_sanitized_status_vectors_and_operator_references():
    for sample in json.loads((Path(__file__).parent / "fixtures/status.json").read_text()):
        state = decode_status(bytes.fromhex(sample["body_hex"]))
        assert {k: state[k] for k in sample["expected"]} == sample["expected"], sample["name"]
        for key, value in sample.get("operator_reference", {}).items():
            assert abs(state[key] - value) <= {"out_w": 50, "pa_a": 2}[key], sample["name"]


def test_unknown_pages_and_rx_decay_clear_estimates():
    body = status_body()
    body[2] |= 0x10
    body[30] = 0x21
    body[17], body[23], body[25] = 55, 32, 25
    state = decode_status(body)
    assert (state["out_w"], state["pa_a"], state["pa_v"]) == (500, 20, 51)
    for offset, value in ((0, 2), (5, 2), (14, 1)):
        other = bytearray(body)
        other[offset] = value
        assert all(decode_status(other)[key] is None for key in ("out_w", "pa_a", "pa_v"))
    body[30] = 0x11
    assert decode_status(body)["out_w"] is None
    body[2] &= ~0x10
    assert decode_status(body)["pa_v"] is None


@pytest.mark.parametrize("raw,wanted", [(1, 1.1), (10, 1.5), (20, 2), (21, 2), (40, 3), (41, 3), (60, None)])
def test_swr_calibration_interval(raw, wanted):
    body = status_body()
    body[30], body[21] = 0x21, raw
    assert decode_status(body)["swr_ant"] == wanted
    body[30] = 0x11
    assert decode_status(body)["swr_ant"] is None


def test_signed_and_fahrenheit_intake_separate_from_pa_temperature():
    body = status_body()
    body[66:68] = bytes([5 | (5 << 3), 0])
    assert decode_status(body)["temps"] == {"intake": -5}
    body[66:68] = bytes([3 | ((77 & 31) << 3), 77 >> 5])
    assert decode_status(body)["temps"] == {"intake": 25}
    body[66] = 0
    assert decode_status(body)["temps"] == {}
    body[8:12] = (1000).to_bytes(4, "little")
    with pytest.raises(ValueError):
        decode_status(body)
