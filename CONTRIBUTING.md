# Contributing

Install `.[gui,dev]` in a virtual environment. Keep changes in the independent
protocol library where possible; GUI code must not become a second protocol
implementation. Run:

```text
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m build
```

Synthetic TCP tests must not connect to hardware. Public fixtures may contain
only reviewed display bodies and fictitious credentials. Never check in a
working password, whole pcap, vendor binary, original vendor artwork or private
RSA key. Regenerate simulator keys at runtime.

Document whether a change has static, captured, simulated or direct hardware
evidence. Unknown values should remain unknown; an estimate must have a source
and uncertainty description. Use fresh peer state for command guards and
confirmation. Do not retry unconfirmed front-panel events.

For GUI changes, run `python tools/render_demo.py`, inspect the screenshot,
and exercise connection failure, stale/disconnected state and window close.
Tests use Qt directly; the renderer never contacts real hardware.

Build a portable desktop folder with `python tools/build_desktop.py`. This also
records dependency versions and copies license texts. Run its executable with
`--smoke-test` to exercise startup and orderly demo shutdown without hardware.
Keep the portable folder together; do not distribute just the EXE.


On Windows the build deliberately limits DLL discovery to the Python runtime
and Windows paths. An unrelated tool's `icuuc.dll` on PATH can otherwise be
bundled instead of the Windows ICU API expected by Qt. The script performs a
clean dependency analysis; keep this isolation when adapting the build.
