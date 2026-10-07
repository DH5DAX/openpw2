"""Async LAN client. All mutations are explicit, serialized and never retried.

Use ``await client.command('antenna', n=2)`` for an absolute setter.
Callbacks run on the client's event loop; GUI adapters must marshal threads.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import math
import struct
import time
from dataclasses import dataclass, field
from typing import Callable

from .display import decode_status
from .errors import CommandBlocked, ConnectionLost, ProtocolError, PW2Error
from .wire import Session

log = logging.getLogger(__name__)
COMMANDS = ("power", "operate", "tuner", "tune", "input", "antenna", "level")
FRESH_SECONDS = 0.3


@dataclass(frozen=True)
class ConnectionConfig:
    host: str
    username: str
    password: str = field(repr=False)
    port: int = 50200
    mains_v: int | None = None
    timeout: float = 5

    def __post_init__(self):
        if not self.host.strip() or not 1 <= self.port <= 65535:
            raise ValueError("Enter a host and TCP port from 1 to 65535")
        for name, value in (("User ID", self.username), ("Password", self.password)):
            if (
                not value
                or len(value) > 16
                or not value.isascii()
                or any(not 32 <= ord(c) <= 126 for c in value)
            ):
                raise ValueError(f"{name} must contain 1–16 printable ASCII characters")
        if not math.isfinite(self.timeout) or not 0.1 <= self.timeout <= 60:
            raise ValueError("Timeout must be between 0.1 and 60 seconds")
        if self.mains_v is not None and not (90 <= self.mains_v <= 132 or 180 <= self.mains_v <= 264):
            raise ValueError("AC supply must be unknown, 90–132 V or 180–264 V")


def block_reason(state: dict, name: str, args: dict, mains_v: int | None) -> str | None:
    """Shared with the UI; the client always checks again immediately before writing."""
    if not state.get("connected"):
        return "Connect to the amplifier first"
    if name == "power":
        return None
    if state.get("age_s") is None or state["age_s"] > FRESH_SECONDS:
        return "Waiting for fresh status"
    if state.get("power") != "on":
        return "Power on the amplifier first"
    if name == "operate" and args.get("value") is False and state.get("operate") is not None:
        return None
    if state.get("protection_lamp") is not False:
        return "Protection is active or unknown"
    if state.get("tx") is not False:
        return "Wait for RX before switching"
    if state.get("atu") not in ("on", "off") or state.get("tuning"):
        return "Tuner is busy or its state is unknown"
    if name == "level" and args.get("id") == "1k" and not (mains_v and 180 <= mains_v <= 264):
        return "1 kW requires a configured 180–264 V AC supply"
    return None


class Client:
    def __init__(self, config: ConnectionConfig, on_state: Callable[[dict], None] | None = None):
        self.config = config
        self.on_state = on_state
        self.session = Session(config.timeout)
        self._state: dict = {}
        self._connected = False
        self._reader: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._event = asyncio.Event()
        self._revision = 0
        self._last_status = 0.0
        self._key_ack: asyncio.Future | None = None
        self._power_ack: asyncio.Future | None = None
        self._tune_seen: float | None = None

    @property
    def snapshot(self) -> dict:
        result = copy.deepcopy(self._state)
        result.update(
            connected=self._connected,
            age_s=time.monotonic() - self._last_status if self._last_status else None,
        )
        return result

    def _publish(self):
        if self.on_state:
            try:
                self.on_state(self.snapshot)
            except Exception:
                log.exception("State callback failed")

    async def connect(self) -> None:
        async with self._lock:
            if self._reader is not None:
                raise CommandBlocked("Disconnect before opening another session")
            self._state = {}
            self._last_status = 0
            self._revision = 0
            self._tune_seen = None
            self.session = Session(self.config.timeout)
            try:
                await self.session.open(
                    self.config.host, self.config.port, self.config.username, self.config.password
                )
                self._connected = True
                self._reader = asyncio.create_task(self._read(), name="openpw2-status")
                await self._wait(lambda: self._revision > 0)
            except BaseException:
                await self.disconnect()
                raise

    async def disconnect(self) -> None:
        self._connected = False
        task, self._reader = self._reader, None
        if task and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self.session.close()
        self._event.set()
        self._publish()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.disconnect()

    def _track_tuning(self, values, now):
        if values["power"] != "on":
            self._tune_seen = None
        elif values["tuner_lamp"] == 2:
            self._tune_seen = now
        if self._tune_seen is not None:
            if now - self._tune_seen < 0.6 or values["tx"] is not False:
                values.update(atu="tune", tuning=True)
            else:
                self._tune_seen = None

    async def _read(self):
        started = time.monotonic()
        try:
            while True:
                # Off units can remain silent; TCP keepalive detects a dead peer.
                timeout = (
                    None
                    if self._state.get("power") == "off"
                    else max(0, self.config.timeout - (time.monotonic() - (self._last_status or started)))
                )
                frame = await asyncio.wait_for(self.session.receive(), timeout)
                if frame.channel == 1:
                    values = decode_status(frame.body)
                    self._last_status = time.monotonic()
                    self._track_tuning(values, self._last_status)
                    self._state = values
                    self._revision += 1
                    self._event.set()
                    self._publish()
                elif frame.channel == 3 and frame.body[:1] == b"\x01":
                    if len(frame.body) < 8:
                        raise ProtocolError("Truncated key acknowledgement")
                    if self._key_ack and not self._key_ack.done():
                        self._key_ack.set_result(frame.body)
                elif frame.channel == 4:
                    if frame.body == b"\x03":
                        raise ConnectionLost("Another LAN client took over this PW2 session")
                    if frame.body[:1] == b"\x01":
                        if len(frame.body) < 2:
                            raise ProtocolError("Truncated power acknowledgement")
                        if self._power_ack and not self._power_ack.done():
                            self._power_ack.set_result(frame.body[1] == 0)
        except asyncio.CancelledError:
            raise
        except (PW2Error, ValueError, OSError, TimeoutError) as exc:
            self._state["error"] = str(exc) or "PW2 status timed out"
        finally:
            self._connected = False
            for waiter in (self._key_ack, self._power_ack):
                if waiter and not waiter.done():
                    waiter.set_exception(ConnectionLost("PW2 reader stopped"))
            await self.session.close()
            self._event.set()
            self._publish()

    async def _wait(self, predicate):
        async with asyncio.timeout(self.config.timeout):
            while not predicate():
                if not self._connected:
                    raise ConnectionLost(self._state.get("error", "PW2 disconnected"))
                self._event.clear()
                await self._event.wait()

    def _guard(self, name, args):
        reason = block_reason(self.snapshot, name, args, self.config.mains_v)
        if reason:
            raise CommandBlocked(reason)

    async def _press(self, target: bytes, hold: bool = False):
        self._key_ack = asyncio.get_running_loop().create_future()
        start = time.monotonic()
        try:
            await self.session.send(2, b"\x01" + target)
            ack = await asyncio.wait_for(self._key_ack, self.config.timeout)
            if ack[1] != 1:
                raise ProtocolError("Key request rejected")
            if ack[2] == 0 and not hold:
                return
            if ack[2:4] != b"\x01\x01" or ack[4] not in (0, 1):
                raise ProtocolError("Unsupported key acknowledgement")
            threshold = int.from_bytes(ack[6:8], "big") / 1000
            if hold:
                if target != b"\0\x01" or ack[4] != 1 or threshold != 0.5:
                    raise ProtocolError("Unsupported TUNE long-press acknowledgement")
                await asyncio.sleep(max(0, threshold - (time.monotonic() - start)))
                await self._wait(lambda: time.monotonic() - self._last_status <= FRESH_SECONDS)
                try:
                    self._guard("tune", {})
                except CommandBlocked:
                    await self.session.send(2, b"\0" + target)
                    raise ConnectionLost("TUNE cancelled because operating state changed")
                await self.session.send(2, b"\x03" + target)
            else:
                has_hold = ack[4] == 1
                if has_hold and (threshold <= 0 or time.monotonic() - start >= threshold - 0.02):
                    await self.session.send(2, b"\0" + target)
                    raise ConnectionLost("Short-press window expired")
                await asyncio.sleep(
                    max(0, (min(0.08, threshold / 2) if has_hold else 0.08) - (time.monotonic() - start))
                )
                if has_hold and time.monotonic() - start >= threshold - 0.01:
                    await self.session.send(2, b"\0" + target)
                    raise ConnectionLost("Short-press window expired")
                await self.session.send(2, b"\x02" + target)
        finally:
            self._key_ack = None

    async def command(self, name: str, **args) -> dict:
        """Return receipt for power, confirmed target state for setters, start for TUNE.

        Raises CommandBlocked before sending; uncertain requests close the session.
        See docs/api.md for argument names and confirmation semantics.
        """
        valid = (
            (name in ("power", "tuner") and args.get("value") in ("on", "off"))
            or (name == "operate" and type(args.get("value")) is bool)
            or (name == "level" and args.get("id") in ("500", "1k"))
            or (
                name in ("input", "antenna")
                and type(args.get("n")) is int
                and 1 <= args["n"] <= (2 if name == "input" else 6)
            )
            or (name == "tune" and not args)
        )
        if name not in COMMANDS or not valid:
            raise ValueError("Unsupported command or invalid arguments")
        async with self._lock:
            try:
                if name != "power":
                    await self._wait(
                        lambda: (
                            bool(self._last_status) and time.monotonic() - self._last_status <= FRESH_SECONDS
                        )
                    )
                self._guard(name, args)
                if name == "power":
                    self._power_ack = asyncio.get_running_loop().create_future()
                    try:
                        await self.session.send(4, bytes([0, args["value"] == "on"]))
                        if not await asyncio.wait_for(self._power_ack, self.config.timeout):
                            raise CommandBlocked("PW2 rejected the power request")
                    finally:
                        self._power_ack = None
                    return {"confirmation": "accepted"}
                revision = self._revision
                if name == "tune":
                    await self._press(b"\0\x01", hold=True)
                    await self._wait(lambda: self._revision > revision and self._state.get("tuning") is True)
                    return {"confirmation": "started"}
                field_name = {
                    "operate": "operate",
                    "tuner": "atu",
                    "input": "input",
                    "antenna": "tx_ant",
                    "level": "level",
                }[name]
                desired = (
                    args["id"]
                    if name == "level"
                    else args.get("value")
                    if name in ("operate", "tuner")
                    else args["n"]
                )
                current = self._state.get(field_name)
                if current is None:
                    raise CommandBlocked("Current state unknown; refusing a blind key press")
                if current == desired:
                    return {"confirmation": "unchanged"}
                selected = self._state.get("input")
                if name == "antenna" and selected not in (1, 2):
                    raise CommandBlocked("Active input is unknown")
                if name == "level":
                    target = b"\x01" + struct.pack(">HH", 246, 159)
                else:
                    key = {"operate": 2, "tuner": 1}.get(name)
                    if name == "input":
                        key = 3 + desired
                    elif name == "antenna":
                        key = (10 if selected == 1 else 16) + desired - 1
                    target = bytes([0, key])
                await self._press(target)
                await self._wait(
                    lambda: (
                        self._revision > revision
                        and self._state.get(field_name) == desired
                        and (name != "antenna" or self._state.get("input") == selected)
                    )
                )
                return {"confirmation": "state"}
            except (ProtocolError, ConnectionLost, OSError, TimeoutError) as exc:
                await self.disconnect()
                raise ConnectionLost(
                    str(exc) or "Command result not confirmed; reconnect to inspect state"
                ) from exc
            except asyncio.CancelledError:
                await self.disconnect()
                raise
