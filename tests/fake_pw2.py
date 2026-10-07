"""Synthetic TCP peer with its own RSA key. No vendor login or device secrets."""

import asyncio
import hashlib
from contextlib import asynccontextmanager

from cryptography.hazmat.primitives.asymmetric import padding, rsa

from openpw2.wire import Frame, read_frame


def status_body():
    body = bytearray(132)
    body[0:5] = bytes.fromhex("01 01 00 0a 00")
    body[8:12] = (112).to_bytes(4, "little")
    body[14] = 2
    body[16] = 0x3F
    body[30] = 0x11
    body[33:39] = b"14.210"
    body[50] = 0x21
    body[66:69] = bytes.fromhex("e1 00 51")
    return body


class FakePW2:
    def __init__(self, *, reject=False, key_ack=True, confirm=True, silent=False, off=False):
        self.status = status_body()
        if off:
            self.status[0] = 2
        self.reject, self.key_ack, self.confirm, self.silent = reject, key_ack, confirm, silent
        self.frames, self.tasks, self.errors = [], [], []
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        self.writer = None

    async def push(self):
        if self.writer and not self.writer.is_closing():
            self.writer.write(Frame(1, bytes(self.status)).encode())
            await self.writer.drain()

    async def serve(self, reader, writer):
        self.tasks.append(asyncio.current_task())
        self.writer = writer
        ticker = None
        try:
            hello = await read_frame(reader)
            self.frames.append(hello)
            assert hello.channel == 0 and hello.body == bytes(4) + b"4109"
            pub = self.private.public_key().public_numbers()
            challenge = (
                b"\x01\0\0\0" + b"A" * 108 + pub.n.to_bytes(128, "big") + pub.e.to_bytes(3, "big") + b"\x01\0"
            )
            packet = Frame(0, challenge).encode()
            for a, b in ((0, 3), (3, 19), (19, len(packet))):
                writer.write(packet[a:b])
                await writer.drain()
                await asyncio.sleep(0.002)
            login = await read_frame(reader)
            self.frames.append(login)
            assert login.body[:20] == b"\x02\0\0\0testuser        "
            assert (
                self.private.decrypt(login.body[20:], padding.PKCS1v15())
                == hashlib.sha256(b"A" * 108 + b"4109testpass        ").digest()
            )
            writer.write(
                Frame(0, b"\x03\0\0\0" + bytes([self.reject])).encode()
                + (b"" if self.reject or self.silent else Frame(1, bytes(self.status)).encode())
            )
            await writer.drain()
            if self.reject:
                return

            async def tick():
                while True:
                    await asyncio.sleep(0.04)
                    if self.status[0] == 1:
                        await self.push()

            if not self.silent:
                ticker = asyncio.create_task(tick())
            while True:
                frame = await read_frame(reader)
                self.frames.append(frame)
                if frame.channel == 4:
                    self.status[0] = 1 if frame.body[1] else 2
                    writer.write(Frame(4, b"\x01\0").encode())
                    await self.push()
                if frame.channel == 2 and self.key_ack:
                    event, kind = frame.body[:2]
                    key = frame.body[2] if kind == 0 else None
                    follow = kind == 1 or key in (1, 4, 5)
                    if event == 1:
                        ack = (
                            "0101010100000000"
                            if kind == 1
                            else "01010101010001f4"
                            if follow
                            else "0101000000000000"
                        )
                        writer.write(Frame(3, bytes.fromhex(ack)).encode())
                    if event == 3 and key == 1 and self.confirm:
                        self.status[2] |= 0x80
                    elif self.confirm and ((event == 1 and not follow) or (event == 2 and follow)):
                        if kind == 1:
                            assert frame.body[2:] == bytes.fromhex("00f6009f")
                            self.status[50] ^= 0x30
                        elif key == 2:
                            self.status[2] ^= 0x10
                        elif key == 1:
                            self.status[2] ^= 0x40
                        elif key in (4, 5):
                            self.status[3:5] = bytes.fromhex("0a00" if key == 4 else "0402")
                        elif 10 <= key <= 15:
                            ant = key - 10
                            self.status[3] &= 7
                            self.status[4] &= 0xFE
                            self.status[3 if ant < 5 else 4] |= 1 << (ant + 3 if ant < 5 else 0)
                        elif 16 <= key <= 21:
                            self.status[4] = (self.status[4] & 0x81) | (1 << (key - 15))
                    await self.push()
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        except Exception as exc:
            from openpw2.errors import ConnectionLost

            if not isinstance(exc, ConnectionLost):
                self.errors.append(exc)
        finally:
            if ticker:
                ticker.cancel()
                await asyncio.gather(ticker, return_exceptions=True)
            writer.close()
            await writer.wait_closed()


@asynccontextmanager
async def fake_pw2(**kwargs):
    peer = FakePW2(**kwargs)
    server = await asyncio.start_server(peer.serve, "127.0.0.1", 0)
    peer.port = server.sockets[0].getsockname()[1]
    try:
        yield peer
    finally:
        server.close()
        for task in peer.tasks:
            task.cancel()
        await asyncio.gather(*peer.tasks, return_exceptions=True)
        await server.wait_closed()
        assert not peer.errors
