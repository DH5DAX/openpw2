# Measurements and uncertainty

The LAN status is a representation of the PW2 display. It is not a packet of
physical sensor measurements. Keep raw display position, an estimated physical
value and the source/quality of that value separate in integrations.

## Available quantities

| API field | Meaning / quality | Missing-value behavior |
|---|---|---|
| `out_w` | Approximate forward watts, 10 W rounding | null outside scale, nonzero RX decay, hidden/non-bar page |
| `pa_a` | Approximate drain current, 1 A rounding | null outside scale, nonzero RX decay, hidden/non-bar page |
| `pa_v` | Approximate drain voltage, 1 V rounding | null for empty bar, standby, invalid range/non-bar page |
| `swr_ant` | Approximate displayed SWR, one decimal | null in RX or outside measured interval |
| `alc` | Relative ALC position 0…1 | null when absent; not an ALC voltage |
| `temps.intake` | Numeric intake air temperature in °C | absent when hidden/off/unrecognized page |
| `humidity` | Numeric intake air relative humidity, percent | null when hidden/off/unrecognized page |
| `meter_display.values.temp.percent` | Relative PA COOL–HOT position | not a Celsius value or a protection threshold |

`measurement_sources` names display estimates explicitly. Raw segment counts
and their relative percentages remain in `meter_display.values`. An empty
numeric field is not zero. Lost links are visibly disconnected; applications
must not treat a retained last snapshot as current data.

## Scale approximation

Linear interpolation between approximate **segment** positions of the original
display's labels (original artwork is not redistributed):

| Meter | (segment, physical value) anchors |
|---|---|
| Po | (0,0), (21,100), (41,250), (55,500), (69,1000), (83,1500) W |
| Id | (0,0), (16,10), (32,20), (48,30), (64,40), (80,50) A |
| Vd | `30 + 30*(3*raw - 1)/104` V for raw 1…35, only in Operate |
| SWR | (1,1.1), (10,1.5), (20.5,2.0), (40.5,3.0); raw 41 also maps to 3.0 |

Do not extrapolate these curves. The artwork's 1.5 kW endpoint is an instrument
label, not a supported output-power setting. Po is nonlinear; fitting a single
line from zero to 1 kW is wrong. SWR interpolation is limited to measured
references rather than inventing a value near the infinity end of the scale.

## Hardware reference observations, 2026-10-07

The operator compared the PW2 power display with an external wattmeter before
these tests and reported that they agreed. Values below were approximately
read by the operator; they are not precision calibration standards.

| Operator reference | Observed settled LAN segments | Decoder estimate |
|---|---|---|
| 500 W, around 20 A | Po 55, Id 31–32 | 500 W, 19–20 A |
| 1,000 W, around 28 A | Po 68–69, Id 43–44 | 960–1,000 W, 27–28 A |
| SWR 1.1 / 1.5 / 2.0 / 3.0 | 1 / 10 / 20–21 / 40–41 | respective reference values |
| Around 50 V | Vd 25 | 51 V |
| ALC around half scale | ALC 42 | 49.8% |
| Intake air 28 °C / 40% | bytes `e1 00 51` | exact numeric decode 28 °C / 40% |

Po/Id readings were repeated. Tests compare those examples within 50 W / 2 A;
these tolerances are **not accuracy specifications** for the full scale.
Vd has only an approximate operator reading, not an independent voltmeter
calibration. PA temperature near COOL has no Celsius calibration.

## CI-V comparison

The [Icom CI-V guide, page 4](https://icomuk.co.uk/files/icom/PDF/productAdditionalFile/IC-PW2_ENG_CI-V_2.pdf)
has Po 161=500 W and 201=1 kW; Id 96=20 A and 144=30 A. This is roughly
three CI-V units per LAN segment at the observed points, but not an exact
shared encoding. SWR 1.5/2/3 maps to CI-V 40/80/120, incompatible with one
universal multiplier. Vd also has a different origin (CI-V 120=30 V,
241=60 V; the LAN bar starts at 30 V). Do not feed LAN counts into a CI-V table.
