# Architecture

```text
Qt widgets (main thread)
       │ commands                  ▲ copied snapshots / result messages
       ▼                           │ Qt queued signals
gui/bridge.py ── dedicated asyncio thread
       │
       ├── client.py ── wire.py ── TCP / IC-PW2
       │      │           └── auth.py
       │      └── display.py
       └── demo.py (local-only, same public interface)
```

| Module | Responsibility |
|---|---|
| `auth.py` | Pure credential fields, SHA-256 digest and challenge-key RSA login body |
| `wire.py` | Pure Frame, bounded stream parser, TCP lifecycle and handshake |
| `display.py` | Pure display decoder, visibility, numeric footer and estimated meter scales |
| `client.py` | One reader, serialized absolute commands, state confirmation, interlocks and tuning blink |
| `demo.py` | Interactive local model, no sockets or imported hardware settings |
| `gui/bridge.py` | Event-loop thread and signal boundary; orderly cancellation/shutdown |
| `gui/window.py` | Confirmed-state dashboard, connection form and sanitized reference view |
| `gui/theme.py`, `gui/theme.qss` | HamRig tokens, component styles and semantic status colours |
| `gui/settings.py` | Atomic preference save; password explicitly excluded |

No Qt types occur in the protocol layer. State uses plain dictionaries so it
can be serialized and ported readily. Display fields retain the earlier HamRig
names where useful (`out_w`, `pa_a`, `pa_v`); there is no runtime HamRig import.

## Lifecycle and failure handling

1. User chooses Connect or Demo. Normal startup does not connect automatically.
2. TCP framing and authentication complete, then the first status arrives.
3. The reader publishes snapshots. GUI updates are signals on the Qt thread;
   networking, RSA and waits never run on the widget thread.
4. Commands take the operation lock, wait for a fresh snapshot, apply guards,
   send one control sequence and await the proper confirmation.
5. Unknown outcomes close the session. Explicit Disconnect or window close
   cancels tasks and closes sockets, with no power/tune operation.

The source has no automatic service installer, portal integration, background
autostart or telemetry collection. JSON export contains only the current
decoded display snapshot. The raw reference view means raw *meter* fields,
not authentication packets or TCP dumps.

## Extending the implementation

Add a protocol feature first as a pure decoder/encoder or a client command;
provide independent test vectors and evidence in `docs/status.md`. Then expose
it in Qt. Do not infer a new command from a similarly numbered CI-V command.
Do not introduce optimistic widget state for commands that can time out.

To support another UI, use `Client` and bridge its callback to that toolkit.
To port to another language, reproduce `wire.py` and `auth.py` first, validate
login against a synthetic RSA peer, then replay the sanitized status fixtures.
Finally validate explicit controls on hardware with an operator present.
