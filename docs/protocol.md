# RS-PW2 LAN protocol reference

Status: independently implemented from RS-PW2 1.0.4 behavior and IC-PW2
observations, 2026-10-07. This is not an official specification. Numeric
offsets are zero-based; slices use Python's exclusive upper bound. Hexadecimal
bytes are shown with spaces. No captured login or vendor binary is required.

## Transport and framing

TCP port 50200. This is **not CI-V over TCP** and is not the radio RS-BA1 UDP
protocol. A receiver must reassemble the byte stream; packet boundaries do not
define frames. Header (`struct.Struct(">4sHIHI")`), then exactly `body_length` bytes:

| Offset | Bytes | Meaning |
|---|---:|---|
| 0 | 4 | Magic `44 11 00 99` |
| 4 | 2 | Channel, big endian |
| 6 | 4 | Body length, big endian |
| 10 | 2 | Per-direction sequence, big endian, wraps at 65536 |
| 12 | 4 | Reserved, zero |

The client starts sequence zero and increments per outbound frame. Sequence
numbers are not used as command-result IDs. Channel 0 is login/control, 1 is
display status, 2 is front-panel input, 3 is input acknowledgement, 4 is power
and session notification. Limit bodies to 2 MiB; observed menu frames reach
165,048 bytes. Invalid magic/reserved fields, oversized bodies, truncation and
EOF terminate the session. Non-normal display pages are not normal telemetry.

## Login

1. Send channel 0 body `00 00 00 00 34 31 30 39` (`4109` is ASCII).
2. Read channel 0 challenge with prefix `01 00 00 00`.
3. Read raw token `challenge[4:112]` (108 bytes), modulus `[112:240]`
   (128 bytes, big endian), exponent `[240:243]` (3 bytes, big endian).
   Trailing bytes carry capabilities; at least 244 body bytes are required.
4. `password_field = ASCII(password)[:16].ljust(16, b" ")`.
   Compute `SHA256(token_raw + b"4109" + password_field)`.
   **Do not base64-decode the token and do not hex-encode the digest.**
5. Encrypt the 32 digest bytes using the challenge's RSA-1024 public key and
   PKCS#1 v1.5 encryption padding. The observed exponent is 65537.
6. Send channel 0 body `02 00 00 00` + 16-byte space-padded ASCII user ID +
   128-byte ciphertext. Body length is 148.
7. Channel 0 prefix `03 00 00 00` followed by status 0 accepts the login.
   A nonzero status rejects it. Wait for the first channel-1 status.

The low-level encoder matches the original ASCII replacement/truncation.
The public API rejects non-ASCII, empty or overlong credentials instead of
silently altering user input. RSA ciphertext changes because PKCS#1 padding
is randomized. Captured sessions reused token/key values, but this is an
observation, not a universal guarantee. Always consume the current challenge.

There is no TLS transport here; RSA applies to the login digest, not the
subsequent controls/status. The application does not log authentication frames.
Opening/closing a connection sends no channel-4 power request.

## Power and session notification

Channel 4: body `00 01` requests on; `00 00` requests off. `01 00` accepts the
request; nonzero second byte rejects it. This acknowledgement confirms receipt,
not that the requested final state has already been observed. Status byte 0
is the source of power state. Channel-4 body `03` means another LAN client
replaced this session. Disconnect and report it; do not fight for ownership.

An off unit can send one status and then stay silent. Keep its authenticated
socket for explicit power-on, with OS TCP keepalive. An on unit that sends no
fresh status for the configured timeout is considered disconnected.

## Front-panel events

Channel 2, body `event target`. Key target: `00 key_id`.
Touch target: `01 x_hi x_lo y_hi y_lo`.

| Action | Key / target | Sequence |
|---|---|---|
| Operate/Standby | Key 2 | event 1, immediate acknowledgement |
| Tuner enable/bypass | Key 1 | event 1, acknowledgement, event 2 |
| Start tuning | Key 1 | event 1, acknowledgement, event 3 after 500 ms |
| Input 1 / 2 | Key 4 / 5 | event 1, acknowledgement, event 2 |
| Input-1 antenna 1…6 | Keys 10…15 | event 1, immediate acknowledgement |
| Input-2 antenna 1…6 | Keys 16…21 | event 1, immediate acknowledgement |
| 500 W / 1 kW | Touch (246,159) | event 1, acknowledgement, event 2 |

Key numbers above are decimal. Example ANT2 on input 1: body `01 00 0b`.
Example level touch: `01 01 00 f6 00 9f` then `02 01 00 f6 00 9f`.

Only channel-3 notification type 1 is a key acknowledgement. Its eight bytes:

| Offset | Meaning |
|---|---|
| 0 | Notification type, 1 |
| 1 | Accepted, 1 in observed successful replies |
| 2 | Follow-up handshake: 0 immediate / 1 follow-up |
| 3 | Short-press branch enabled when 1 |
| 4 | Long-press branch enabled when 1 |
| 5 | Unassigned |
| 6:8 | Long-press threshold in milliseconds, big endian |

Observed immediate ACK: `01 01 00 00 00 00 00 00`.
Tuner/input ACK: `01 01 01 01 01 00 01 f4` (500 ms).
Level-touch ACK: `01 01 01 01 00 00 00 00` (no hold; zero threshold is valid).
Short presses release around 80 ms, before the offered hold threshold. Explicit
TUNE uses event 3 after 500 ms and has no subsequent event 2. Event 0 cancels a
pending follow-up in the tested control path. Unknown ACK branches fail closed.

Read fresh state (at most 300 ms old) before a mutation. Require known RX,
no protection and a non-busy tuner; release to Standby is allowed separately.
Absolute setters compare desired with current state, skip duplicates, and wait
for **new status** confirming the result. Antenna writes also confirm the same
active input. A key ACK alone is not success. Serialize all commands: replies
have no reliable request correlation. On missing ACK/result, disconnect and
report uncertainty; never automatically repeat a potentially applied toggle.

Tuning lamp values 2/0 blink approximately every 250 ms. Keep `tuning=True`
through dark phases until RX and at least 600 ms since the last busy lamp.
Observed successful attempts ended with tuner on; an operator-labelled failure
ended off. No distinct completion/error code has been identified.

## Channel-1 display status

Normal observed body length 132. Header bytes:

| Body offset | Meaning |
|---|---|
| 0 | Power: 1 on, 2 off, other unknown |
| 2 bit 4 | Operate lamp |
| 2 bit 5 | Protection lamp (reason unknown) |
| 2 bit 6 / bit 7 | Tuner enabled / tuning (busy takes priority) |
| 5 | Display page, 0 normal |
| 8:12 | Display payload size, **little endian**; normal size 112 |
| 12:124 | Display payload, called `D` below |

Input lamp decoding: left selector is 1 if body[3] bit1, else 2 if body[2]
bit2, else 0. Right selector is 1 if body[3] bit2, else 2 if body[2] bit3,
else 0. Only left/right `(1,0)` → input 1 and `(0,1)` → input 2 are currently
mapped. Ambiguous SO2R combinations remain unknown and block routing writes.
Input-1 antenna lamps: body[3] bits3…7 and body[4] bit0. Input-2 antenna lamps:
body[4] bits1…6. Require exactly one lit lamp per side.

Normal-page fields (all **body** offsets):

| Offset | Encoding |
|---|---|
| 33:39, 43:49 | Six ASCII characters, frequency in MHz for input 1/2 |
| 30, 40 bits4…6 | TX artwork selector: 0 absent, 1 RX, 2 TX, 3 TX hot, 4 TX out |
| 50 bits4…5 | Level: 1 = 500 W, 2 = 1 kW |
| 52 bit0, 53:59 | Clock visibility and ASCII HHMMSS |
| 66 bit0 | Intake temperature visible |
| 66 bit1 / bit2 | Fahrenheit / negative |
| 66 bits3…7 + 67 bits0…4 | Magnitude: `(body[66]>>3) \| ((body[67]&31)<<5)` |
| 68 bit0 / bits1…7 | Humidity visible / relative humidity percent |

Unknown TX selectors must not mean RX. Any known transmitting selector implies
TX; otherwise only all 0/1 selectors imply RX. Normalize Fahrenheit to Celsius.
Frequency follows the active input; the preceding byte is a status byte, not
part of the ASCII text. Numeric temperature is **intake air**, not the PA meter.

`D[2]=2` is bar mode. `D[4]` bits0…5 select visible Po/ALC/SWR/Id/Vd/Temp.
Current segment values are `D[5]`, `D[7]`, `D[9]`, `D[11]`, `D[13]`, `D[14]`.
Peak-hold display bytes are adjacent to the first four current values but are
not used as current measurements. Render width is `clamp(3*raw-1, 0, 3*limit-1)`;
limits are 83 segments except ALC 84 and Vd/Temp 35.

`D[2]=1` is needle mode: two six-byte records at D[4] and D[10]. Each begins
with visibility=1, meter kind (0 Po,1 Id,2 Temp,3 Vd,4 SWR,5 ALC), and a little-
endian uint16 needle angle. Physical conversions remain unimplemented.

See [measurements.md](measurements.md) for physical-unit estimates. Unrecognized
pages, hidden instruments and power-off clear unavailable readings, rather than
retaining misleading old values. See `tests/fixtures/status.json` for selected,
sanitized channel-1 bodies and their expected decode results.

## Sources

- Original-app RS-PW2 1.0.4 behavior and independently written HamRig PW2 work,
  extracted into this standalone implementation with no HamRig dependency.
- [Icom IC-PW2 CI-V reference, page 4](https://icomuk.co.uk/files/icom/PDF/productAdditionalFile/IC-PW2_ENG_CI-V_2.pdf):
  comparison of meter scales, not a specification for these LAN packets.
- [Icom IC-PW2 manual, page 1-5](https://icomuk.co.uk/files/icom/PDF/productManual/IC-PW2_ENG_IM_2.pdf):
  identifies the numeric temperature/humidity readout as intake air.
