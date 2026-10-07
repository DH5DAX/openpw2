"""Observed RS-PW2 display layout, including numeric temperature/humidity.

Body offsets and artwork selectors: RS-PW2 1.0.4, see docs/protocol.md.
Unknown pages/indications clear values instead of retaining stale measurements.
"""

import re
from decimal import Decimal

METER_NAMES = ("po", "id", "temp", "vd", "swr", "alc")
SEGMENTS = {"po": 83, "id": 83, "temp": 35, "vd": 35, "swr": 83, "alc": 84}
# Operator-referenced settled bar readings, 2026-10-07. Never extrapolate
# past the calibrated interval; a large SWR must not be clipped to 3.0.
SWR_REFERENCES = ((1, 1.1), (10, 1.5), (20.5, 2.0), (40.5, 3.0))
# Approximate segment positions of labels in RS-PW2's original scale artwork.
# Interpolation reproduces the displayed scale, not a calibrated sensor value.
# RF checks: Po 55 ~= 500 W, 68/69 ~= 1 kW; Id 31/32 ~= 20 A,
# 43/44 ~= 28 A (operator's approximate readings). See docs/measurements.md.
POWER_SCALE = ((0, 0), (21, 100), (41, 250), (55, 500), (69, 1000), (83, 1500))
CURRENT_SCALE = ((0, 0), (16, 10), (32, 20), (48, 30), (64, 40), (80, 50))
BANDS = [
    (1800000, 2000000, "160m"),
    (3500000, 4000000, "80m"),
    (7000000, 7300000, "40m"),
    (10100000, 10150000, "30m"),
    (14000000, 14350000, "20m"),
    (18068000, 18168000, "17m"),
    (21000000, 21450000, "15m"),
    (24890000, 24990000, "12m"),
    (28000000, 29700000, "10m"),
    (50000000, 54000000, "6m"),
]


def _frequency(text):
    match = re.fullmatch(rb" *([0-9]{1,2}\.[0-9]{1,3}) *", text)
    return int(Decimal(match[1].decode("ascii")) * 1000000) if match else None


def _interpolate(raw, points):
    for (low, a), (high, b) in zip(points, points[1:]):
        if low <= raw <= high:
            return a + (raw - low) * (b - a) / (high - low)
    return None


def swr_from_display(raw):
    value = _interpolate(raw, SWR_REFERENCES)
    if value is not None:
        return round(value, 1)
    # Quantization straddles the top reference (observed 40/41).
    return 3.0 if raw == 41 else None


def decode_status(body: bytes) -> dict:
    if len(body) < 20:
        raise ValueError("Truncated PW2 telemetry")
    size = int.from_bytes(body[8:12], "little")
    if size > len(body) - 12:
        raise ValueError("Truncated PW2 display data")
    result = dict(
        power={1: "on", 2: "off"}.get(body[0]),
        frequency_hz=None,
        band=None,
        operate=None,
        protect=None,
        input=None,
        tx_ant=None,
        atu=None,
        tuning=None,
        tx=None,
        meter_display=None,
        input_frequencies_hz=[None, None],
        antenna_by_input=[None, None],
        protection_lamp=None,
        tx_display_codes=None,
        temps={},
        humidity=None,
        level=None,
        device_clock=None,
        tuner_lamp=None,
        swr_ant=None,
        alc=None,
        out_w=None,
        pa_a=None,
        pa_v=None,
        measurement_sources={},
    )
    if result["power"] != "on":
        return result

    def bit(pos, n):
        return bool(body[pos] & (1 << n))

    left = 1 if bit(3, 1) else 2 if bit(2, 2) else 0
    right = 1 if bit(3, 2) else 2 if bit(2, 3) else 0
    # Only the single-active-input case has been observed. Ambiguity blocks writes.
    active = 1 if (left, right) == (1, 0) else 2 if (left, right) == (0, 1) else None
    antennas = []
    for lamps in (
        [bit(3, 3 + i) if i < 5 else bit(4, 0) for i in range(6)],
        [bit(4, 1 + i) for i in range(6)],
    ):
        antennas.append(lamps.index(True) + 1 if sum(lamps) == 1 else None)
    tuner = 2 if bit(2, 7) else int(bit(2, 6))
    result.update(
        operate=bit(2, 4),
        input=active,
        antenna_by_input=antennas,
        tx_ant=antennas[active - 1] if active else None,
        atu={0: "off", 1: "on", 2: "tune"}[tuner],
        tuning=tuner == 2,
        tuner_lamp=tuner,
        protection_lamp=bit(2, 5),
        protect="active" if bit(2, 5) else 0,
    )
    if size != 112 or body[5] != 0:
        return result
    d = body[12:124]
    if body[5] == 0:
        freqs = [_frequency(body[33:39]), _frequency(body[43:49])]
        hz = freqs[active - 1] if active else None
        # 1ca calls the bit-reversing extractor a5: wire bits 4..6, NOT 1..3.
        # Artwork 0=transparent, 1=tx_off, 2=tx_on, 3=tx_hot, 4=tx_out.
        # Hardware capture confirms 1 -> 2 -> 1 during RF transmission.
        tx_codes = [(body[p] & 0x70) >> 4 for p in (30, 40)]
        tx = (
            True
            if any(c in (2, 3, 4) for c in tx_codes)
            else False
            if all(c in (0, 1) for c in tx_codes)
            else None
        )
        result.update(
            frequency_hz=hz,
            input_frequencies_hz=freqs,
            tx=tx,
            tx_display_codes=tx_codes,
            band=next((name for low, high, name in BANDS if hz is not None and low <= hz <= high), None),
        )
        # Footer starts at body[50]. RS-PW2 methods 1e2..1e7: visibility,
        # Fahrenheit/sign flags, a 10-bit temperature magnitude and humidity.
        # The footer is INTAKE AIR (Icom manual p. 1-5), not the PA
        # temperature represented by the separate COOL/HOT bar.
        if body[66] & 1:
            temperature = (body[66] >> 3) | ((body[67] & 0x1F) << 5)
            if body[66] & 4:
                temperature = -temperature
            if body[66] & 2:
                temperature = round((temperature - 32) * 5 / 9, 1)
            result["temps"] = {"intake": temperature}
        if body[68] & 1 and body[68] >> 1 <= 100:
            result["humidity"] = body[68] >> 1
        result["level"] = {1: "500", 2: "1k"}.get((body[50] >> 4) & 3)
        if body[52] & 1 and re.fullmatch(rb"[0-2][0-9][0-5][0-9][0-5][0-9]", body[53:59]):
            clock = body[53:59].decode("ascii")
            if int(clock[:2]) < 24:
                result["device_clock"] = f"{clock[:2]}:{clock[2:4]}:{clock[4:]}"
    meters = {}
    if d[2] == 2:
        for index, (name, pos) in enumerate(
            (("po", 5), ("alc", 7), ("swr", 9), ("id", 11), ("vd", 13), ("temp", 14))
        ):
            if not d[4] & (1 << index):
                continue
            limit = SEGMENTS[name]
            meters[name] = {
                "raw": d[pos],
                "max_segments": limit,
                "percent": round(100 * max(0, min(3 * d[pos] - 1, 3 * limit - 1)) / (3 * limit - 1), 1),
            }
        result["meter_display"] = {"mode": "bars", "values": meters, "physical_units": False}
        for name, key, scale, step in (("po", "out_w", POWER_SCALE, 10), ("id", "pa_a", CURRENT_SCALE, 1)):
            raw = meters.get(name, {}).get("raw")
            # Nonzero bars in RX may be animation/decay, not current RF/Id.
            if raw is not None and (result["tx"] is True or raw == 0):
                value = _interpolate(raw, scale)
                if value is not None:
                    result[key] = int(step * round(value / step))
                    result["measurement_sources"][key] = "display_estimate_from_scale_artwork"
        raw_vd = meters.get("vd", {}).get("raw")
        # An empty/standby Vd bar does not mean 30 V. Never extrapolate.
        if result["operate"] and raw_vd is not None and 0 < raw_vd <= SEGMENTS["vd"]:
            result["pa_v"] = round(30 + 30 * (3 * raw_vd - 1) / (3 * SEGMENTS["vd"] - 1))
            result["measurement_sources"]["pa_v"] = "display_estimate_from_scale_artwork"
        if "alc" in meters:
            result["alc"] = meters["alc"]["percent"] / 100
            result["measurement_sources"]["alc"] = "relative_display_bar"
        if result["tx"] is True and "swr" in meters:
            result["swr_ant"] = swr_from_display(meters["swr"]["raw"])
            if result["swr_ant"] is not None:
                result["measurement_sources"]["swr_ant"] = "display_estimate_from_operator_references"
    elif d[2] == 1:
        for pos in (4, 10):
            if d[pos] == 1 and d[pos + 1] < len(METER_NAMES):
                meters[METER_NAMES[d[pos + 1]]] = {
                    "angle_raw": int.from_bytes(d[pos + 2 : pos + 4], "little")
                }
        result["meter_display"] = {"mode": "needles", "values": meters, "physical_units": False}
    return result
