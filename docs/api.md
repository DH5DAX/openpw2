# Python API

Install without GUI dependencies for scripts: `python -m pip install -e .`.
Everything in `openpw2.client`, `wire`, `auth` and `display` works without Qt.
Python 3.11+ supplies asyncio timeouts. See `examples/read_status.py`.

```python
from openpw2 import Client, ConnectionConfig

config = ConnectionConfig(
    host="192.0.2.10",
    port=50200,
    username="YOUR_USER_ID",
    password="YOUR_PASSWORD",
    mains_v=230,
    timeout=5,
)

async with Client(config, on_state=handle_snapshot) as pw2:
    status = pw2.snapshot
    # Explicit changes; application/operator decides when these are appropriate:
    # await pw2.command("operate", value=True)
    # await pw2.command("antenna", n=2)
```

`connect()` waits for authentication and the first status. `disconnect()`
closes the socket and reader; it never powers off the amplifier. There is no
automatic reconnect. After a failed session, call `disconnect()` before
explicitly reconnecting, or create a new Client.

## Commands

| Name | Keyword arguments | Confirmation |
|---|---|---|
| `power` | `value="on"` or `"off"` | `accepted`: receipt ACK, final power state comes from telemetry |
| `operate` | `value=True` or `False` | `state`: fresh status matches target |
| `tuner` | `value="on"` or `"off"` | `state`: fresh status matches target |
| `tune` | none | `started`: busy status observed, not successful-match completion |
| `input` | `n=1` or `2` | `state` |
| `antenna` | `n=1…6` | `state`, for the current active input |
| `level` | `id="500"` or `"1k"` | `state`; 1 kW requires configured high AC supply |

For an already selected setting (except power), result is `{"confirmation":"unchanged"}`
and no event is sent. Other successful results have the same shape with the
confirmation value from the table. The demo uses `simulated`.

Exceptions: `ValueError` for invalid configuration/arguments; `CommandBlocked`
for unavailable state/interlock or explicit power rejection; `AuthenticationError`
for rejected credentials; `ProtocolError` for bad login/framing;
`ConnectionLost` for a lost session or uncertain command outcome. Socket open
errors and connection/initial-status timeouts can also raise `OSError`/`TimeoutError`.
Do not blindly retry `ConnectionLost`: the action may already have happened.

## State

`snapshot` returns a deep copy. Fields include:

- `connected` and monotonic `age_s` (null until first status).
- `power`, `operate`, `tx`, `tuning`, `atu` (`on`, `off`, `tune`), `level`.
- `input`, `tx_ant`, `antenna_by_input`, `frequency_hz`, `input_frequencies_hz`, `band`.
- `protection_lamp`; `protect` is 0 or `active`, not a numeric protection reason.
- `out_w`, `pa_a`, `pa_v`, `swr_ant`, `alc`, `temps`, `humidity`, `device_clock`.
- `meter_display`: `mode`, visible meter `values` with raw/percent or needle angle.
- `measurement_sources`: quality labels for estimates/relative readings.
- `error` when a reader failure ends the connection.

Unknown fields are null/absent as described in [measurements](measurements.md).
An on-device normal page can become a menu at any time: do not carry old meter
readings forward yourself. Clock zone is the device's display setting; the API
does not claim UTC from the digits alone.

`on_state` is a synchronous callable on the **client's asyncio loop**. It
receives copied snapshots on status/link changes. Keep it short; queue work
or marshal to the UI thread. Callback exceptions are logged independently of
the connection. Credentials are not part of snapshots and config repr hides
the password. Avoid logging raw config dictionaries in your own application.

Commands are serialized within one client. The internal reader alone consumes
the stream, resolving ACK waiters and advancing a revision/event for status
confirmation. `block_reason()` is exported from `client` for UI previews, but
the actual command always rechecks its own current state before sending.
