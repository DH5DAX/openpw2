# Feature status and validation

As of 2026-10-08. "Captured" means an operator action in the original
RS-PW2 application was recorded with resulting PW2 state; it does not mean
the new openpw2 client has completed that exact action on the physical device.

| Feature | openpw2 | Evidence / limitation |
|---|---|---|
| Login / display stream | implemented, TCP tested | earlier client verified on real PW2; current challenge used |
| Power on/off | implemented, ACK tested | earlier client's power-on observed; direct openpw2 off/on acceptance pending |
| Operate / Standby | implemented | original-app captures + synthetic TCP confirmation test |
| Tuner on/off / explicit TUNE | implemented | short/long-press captures; successful and failed tune observations |
| Tune completion | busy and final tuner state | no distinct success/failure reason decoded |
| Input / antenna / level | implemented | captures + tests; only known single-active-input configurations |
| TX/RX | decoded | actual RF tests; independent of Po and display decay |
| Frequencies / band | read-only | normal-page ASCII, selected by input lamps |
| Numeric intake temperature / humidity | decoded | exact 28 °C / 40% reference; Fahrenheit/sign flags tested |
| Clock | displayed digits | zone not inferred |
| Po / Id / Vd | approximate | scale interpretation; repeated Po/Id references, approximate Vd reading |
| SWR | estimate 1.1…3.0 | four operator references; no extrapolation |
| ALC / PA temperature | relative | display position only |
| Protection lamp | decoded, interlock | no detailed reason code; never report "all clear" from absent data |
| Needle view | raw angles only | physical conversion and all-meter coverage pending |
| Display page change | not implemented | change view on PW2; app detects unavailable meters |
| Band writes / protection reset | not implemented | need verified LAN command and outcome |
| SO2R / dual receive / RX antenna | not implemented | ambiguous routing remains unknown |
| DPD / menus / antenna memories | not implemented | further mapping needed |
| USB / serial CI-V | outside initial scope | this repo is the LAN reference; serial work existed separately |
| Windows GUI / portable build | local tests | Linux/macOS source portability not hardware/desktop validation |

## Automated tests

- Synthetic RSA peer verifies the constructed digest, padded ID, fragmentation
  and coalescing. No real password or captured encrypted login is used.
- Real sanitized channel-1 bodies exercise frequency, TX, footer, levels and
  SWR; repeated Po/Id references cross-check scale estimates.
- Explicit commands, absolute-setter deduplication, press/release/hold,
  missing ACKs/results, TX/unknown/protected states and 1 kW AC-supply guard.
- Off-state silence, competing session, invalid frame sizes, EOF and shutdown.
- Demo GUI clicks and real GUI-to-TCP login/commands against the synthetic peer,
  TX interlocks, tune state, preference privacy and thread exit.
- Cancellation during a pending TUNE and status expiry despite unrelated frames.

Local validation on Windows / Python 3.12.14 / PySide6 6.11.2: 27 tests passed;
Ruff lint and formatting passed. Portable startup/demo shutdown and Python wheel /
source-distribution builds were checked. The CI matrix is provided for later runs;
Linux and other Python versions have not been run locally.

Run `python -m pytest -q` with the `gui,dev` extras. Set
`QT_QPA_PLATFORM=offscreen` on headless machines. `tools/render_demo.py` produces
the README screenshot from actual widgets without contacting an amplifier.

## Hardware acceptance still to perform for this standalone app

1. Stop other PW2 LAN clients explicitly. Connect with the amplifier in a
   known state. Check that login/disconnect do not operate power or tuner.
2. Compare selected input, antennas, level, RX, tuner and intake air readouts
   with the front panel. Change a setting at the panel and confirm it updates.
3. In RX, request Standby/Operate, both inputs, representative antennas,
   tuner off/on and both power limits with the matching AC supply configured.
4. Repeat absolute requests and verify there is no extra toggle. Disconnect
   the network after a request and verify it is not replayed on reconnect.
5. With an operator controlling the transmitter/load, check TX lockouts,
   tuning start/busy/final state, and independently measured meter references.
6. Check explicit power off/on, silence while off and replacing a LAN session.

Record firmware/app versions, initial state, exact action and observed outcome.
Do not put whole packet captures into this repository. Add only reviewed
channel-1 vectors or synthetic event sequences; omit credentials, key material,
serial numbers and unrelated network traffic. More precision requires several
independently measured points across each scale, not just a two-point fit.
