"""Bounded RS-PW2 framing and authenticated TCP session. No hardware controls."""

from __future__ import annotations

import asyncio
import socket
import struct
from dataclasses import dataclass

from .auth import login_body
from .errors import AuthenticationError, ConnectionLost, ProtocolError

MAGIC = bytes.fromhex("44110099")
HEADER = struct.Struct(">4sHIHI")
MAX_BODY = 2 * 1024 * 1024


@dataclass(frozen=True)
class Frame:
    channel: int
    body: bytes
    sequence: int = 0

    def encode(self) -> bytes:
        if len(self.body) > MAX_BODY:
            raise ProtocolError("Frame body exceeds 2 MiB")
        return HEADER.pack(MAGIC, self.channel, len(self.body), self.sequence & 0xFFFF, 0) + self.body


async def read_frame(reader: asyncio.StreamReader) -> Frame:
    try:
        magic, channel, size, sequence, reserved = HEADER.unpack(await reader.readexactly(HEADER.size))
        if magic != MAGIC or reserved != 0 or size > MAX_BODY:
            raise ProtocolError("Invalid RS-PW2 frame header")
        return Frame(channel, await reader.readexactly(size), sequence)
    except (OSError, asyncio.IncompleteReadError) as exc:
        raise ConnectionLost("PW2 closed the connection") from exc


class Session:
    def __init__(self, timeout: float = 5):
        self.timeout = timeout
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.sequence = 0

    async def open(self, host: str, port: int, username: str, password: str) -> None:
        try:
            async with asyncio.timeout(self.timeout):
                self.reader, self.writer = await asyncio.open_connection(host, port)
                sock = self.writer.get_extra_info("socket")
                if sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    for option, value in (("TCP_KEEPIDLE", 10), ("TCP_KEEPINTVL", 5), ("TCP_KEEPCNT", 3)):
                        if hasattr(socket, option):
                            try:
                                sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, option), value)
                            except OSError:
                                pass
                await self.send(0, bytes(4) + b"4109")
                challenge = await self.receive()
                if challenge.channel != 0:
                    raise ProtocolError("Expected login challenge")
                try:
                    response = login_body(username, password, challenge.body)
                except ValueError as exc:
                    raise ProtocolError("Invalid login challenge") from exc
                await self.send(0, response)
                reply = await self.receive()
                if reply.channel != 0 or len(reply.body) < 5 or reply.body[:4] != b"\x03\0\0\0":
                    raise ProtocolError("Invalid login acknowledgement")
                if reply.body[4] != 0:
                    raise AuthenticationError("PW2 rejected the user ID or password")
        except BaseException:
            await self.close()
            raise

    async def send(self, channel: int, body: bytes) -> None:
        if self.writer is None or self.writer.is_closing():
            raise ConnectionLost("No connection to the PW2")
        try:
            self.writer.write(Frame(channel, body, self.sequence).encode())
            self.sequence = (self.sequence + 1) & 0xFFFF
            await asyncio.wait_for(self.writer.drain(), self.timeout)
        except (OSError, TimeoutError) as exc:
            raise ConnectionLost("PW2 write failed") from exc

    async def receive(self) -> Frame:
        if self.reader is None:
            raise ConnectionLost("No connection to the PW2")
        return await read_frame(self.reader)

    async def close(self) -> None:
        writer, self.writer = self.writer, None
        self.reader = None
        if writer:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (OSError, TimeoutError):
                pass
