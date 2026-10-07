import asyncio

import pytest

from openpw2 import AuthenticationError, Client, CommandBlocked, ConnectionConfig, ConnectionLost
from openpw2.client import block_reason
from openpw2.errors import ProtocolError
from openpw2.wire import HEADER, MAGIC, MAX_BODY, Frame, read_frame

from .fake_pw2 import fake_pw2


def client(peer, mains=230):
    return Client(
        ConnectionConfig("127.0.0.1", "testuser", "testpass", port=peer.port, mains_v=mains, timeout=0.4)
    )


async def test_fragmented_login_and_coalesced_status_no_implicit_controls():
    async with fake_pw2() as peer:
        async with client(peer) as amp:
            assert amp.snapshot["frequency_hz"] == 14210000
            assert amp.snapshot["temps"] == {"intake": 28}
            assert [p.channel for p in peer.frames] == [0, 0]
            snapshot = amp.snapshot
            snapshot["temps"]["intake"] = 999
            assert amp.snapshot["temps"]["intake"] == 28
        assert [p.channel for p in peer.frames] == [0, 0]


async def test_absolute_controls_and_duplicate_setters():
    async with fake_pw2() as peer:
        async with client(peer) as amp:
            for name, args, packets in [
                ("operate", {"value": True}, ["010002"]),
                ("operate", {"value": False}, ["010002"]),
                ("tuner", {"value": "on"}, ["010001", "020001"]),
                ("tuner", {"value": "off"}, ["010001", "020001"]),
                ("input", {"n": 2}, ["010005", "020005"]),
                ("antenna", {"n": 6}, ["010015"]),
                ("input", {"n": 1}, ["010004", "020004"]),
                ("antenna", {"n": 6}, ["01000f"]),
                ("level", {"id": "500"}, ["010100f6009f", "020100f6009f"]),
                ("level", {"id": "1k"}, ["010100f6009f", "020100f6009f"]),
            ]:
                before = len(peer.frames)
                assert (await amp.command(name, **args))["confirmation"] == "state"
                assert [p.body.hex() for p in peer.frames[before:]] == packets
                before = len(peer.frames)
                assert (await amp.command(name, **args))["confirmation"] == "unchanged"
                assert len(peer.frames) == before
            assert (await amp.command("tune"))["confirmation"] == "started"
            assert [p.body.hex() for p in peer.frames[-2:]] == ["010001", "030001"]
            with pytest.raises(CommandBlocked):
                await amp.command("antenna", n=1)


@pytest.mark.parametrize("key_ack,confirm", [(False, True), (True, False)])
async def test_no_retry_on_uncertain_toggle(key_ack, confirm):
    async with fake_pw2(key_ack=key_ack, confirm=confirm) as peer:
        async with client(peer) as amp:
            with pytest.raises(ConnectionLost):
                await amp.command("operate", value=True)
            assert not amp.snapshot["connected"]
            assert [p.body.hex() for p in peer.frames if p.channel == 2] == ["010002"]


async def test_rejected_and_silent_logins_release_socket():
    async with fake_pw2(reject=True) as peer:
        amp = client(peer)
        with pytest.raises(AuthenticationError):
            await amp.connect()
        assert amp.session.writer is None
    async with fake_pw2(silent=True) as peer:
        amp = client(peer)
        with pytest.raises((ConnectionLost, TimeoutError)):
            await amp.connect()
        assert amp.session.writer is None


async def test_silent_off_peer_explicit_power_and_replaced_session():
    async with fake_pw2(off=True) as peer:
        async with client(peer) as amp:
            await asyncio.sleep(0.5)
            assert amp.snapshot["connected"]
            assert (await amp.command("power", value="on"))["confirmation"] == "accepted"
            assert any(p.channel == 4 and p.body == b"\0\x01" for p in peer.frames)
            peer.writer.write(Frame(4, b"\x03").encode())
            await peer.writer.drain()
            await asyncio.sleep(0.05)
            assert not amp.snapshot["connected"]
            assert "Another LAN client" in amp.snapshot["error"]


async def test_guards_tx_protection_unknown_page_and_supply():
    async with fake_pw2() as peer:
        async with client(peer, mains=None) as amp:
            for offset, value in ((30, 0x21), (2, 0x20), (5, 2)):
                before = bytes(peer.status)
                peer.status[offset] = value
                await peer.push()
                await asyncio.sleep(0.02)
                with pytest.raises(CommandBlocked):
                    await amp.command("antenna", n=2)
                peer.status[:] = before
            peer.status[50] = 0x11
            await peer.push()
            await asyncio.sleep(0.02)
            with pytest.raises(CommandBlocked, match="180–264"):
                await amp.command("level", id="1k")
            assert len(peer.frames) == 2
            for name, args in (("band", {"n": 2}), ("input", {"n": True}), ("operate", {"value": 1})):
                with pytest.raises(ValueError):
                    await amp.command(name, **args)


def test_tuner_blink_and_freshness():
    amp = Client(ConnectionConfig("host", "testuser", "testpass"))
    for now, lamp, tx, busy in [
        (0, 2, False, True),
        (0.25, 0, True, True),
        (0.5, 2, True, True),
        (0.75, 0, True, True),
        (1, 0, False, True),
        (1.2, 1, False, False),
    ]:
        state = dict(power="on", tuner_lamp=lamp, tx=tx, tuning=lamp == 2, atu="on" if lamp else "off")
        amp._track_tuning(state, now)
        assert state["tuning"] == busy
    assert "fresh" in block_reason({"connected": True, "age_s": 1}, "antenna", {"n": 2}, 230)


@pytest.mark.parametrize(
    "header",
    [
        HEADER.pack(b"NOPE", 1, 0, 0, 0),
        HEADER.pack(MAGIC, 1, MAX_BODY + 1, 0, 0),
        HEADER.pack(MAGIC, 1, 132, 0, 0) + b"short",
    ],
)
async def test_invalid_or_truncated_frames(header):
    reader = asyncio.StreamReader()
    reader.feed_data(header)
    reader.feed_eof()
    with pytest.raises((ProtocolError, ConnectionLost)):
        await read_frame(reader)


def test_credentials_are_not_logged_or_silently_truncated():
    assert "testpass" not in repr(ConnectionConfig("host", "testuser", "testpass"))
    for value in ("", "p" * 17, "päss", "bad\npass"):
        with pytest.raises(ValueError):
            ConnectionConfig("host", "testuser", value)


async def test_unrelated_frames_do_not_keep_stale_status_alive():
    async with fake_pw2() as peer:
        async with client(peer) as amp:
            # Stop normal status ticks without telling the client it powered off.
            peer.status[0] = 2

            async def noise():
                for _ in range(15):
                    await asyncio.sleep(0.04)
                    if peer.writer.is_closing():
                        break
                    peer.writer.write(Frame(5, b"unrelated").encode())
                    await peer.writer.drain()

            task = asyncio.create_task(noise())
            try:
                async with asyncio.timeout(1):
                    while amp.snapshot["connected"]:
                        await asyncio.sleep(0.02)
                assert "timed out" in amp.snapshot["error"]
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def test_cancel_pending_tune_closes_session_without_retry():
    async with fake_pw2() as peer:
        async with client(peer) as amp:
            pending = asyncio.create_task(amp.command("tune"))
            await asyncio.sleep(0.1)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert not amp.snapshot["connected"]
            assert [p.body.hex() for p in peer.frames if p.channel == 2] == ["010001"]
