"""One background asyncio loop; Qt signals are the only cross-thread state channel."""

import asyncio
import concurrent.futures

from PySide6.QtCore import QThread, Signal

from openpw2.client import Client
from openpw2.demo import DemoClient


class Bridge(QThread):
    state_changed = Signal(dict)
    message = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.client = None
        self.closing = False
        self.start()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        self.loop.close()

    def _submit(self, coroutine):
        if self.closing:
            coroutine.close()
            return
        self.busy_changed.emit(True)
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)

        def finished(f):
            if not self.closing:
                try:
                    result = f.result()
                    if result:
                        self.message.emit(result)
                except (concurrent.futures.CancelledError, asyncio.CancelledError):
                    pass
                except Exception as exc:
                    self.message.emit(str(exc) or "Connection timed out")
                self.busy_changed.emit(False)

        future.add_done_callback(finished)

    def connect_to(self, config=None, demo=False):
        async def connect():
            if self.client:
                await self.client.disconnect()
            self.client = (
                DemoClient(self.state_changed.emit) if demo else Client(config, self.state_changed.emit)
            )
            await self.client.connect()
            return "Demo connected · no hardware" if demo else "Connected to PW2"

        self._submit(connect())

    def disconnect_from(self):
        async def disconnect():
            if self.client:
                await self.client.disconnect()
                self.client = None
            return "Disconnected"

        self._submit(disconnect())

    def command(self, name, **args):
        async def command():
            if not self.client:
                return "Connect first"
            result = await self.client.command(name, **args)
            return f"{name.capitalize()} · {result['confirmation']}"

        self._submit(command())

    def demo_tx(self, enabled):
        def change():
            if isinstance(self.client, DemoClient):
                self.client.tx_demo = enabled

        self.loop.call_soon_threadsafe(change)

    def shutdown(self):
        if self.closing:
            return
        self.closing = True

        async def stop():
            current = asyncio.current_task()
            others = [task for task in asyncio.all_tasks() if task is not current]
            for task in others:
                task.cancel()
            await asyncio.gather(*others, return_exceptions=True)
            if self.client:
                await self.client.disconnect()

        future = asyncio.run_coroutine_threadsafe(stop(), self.loop)
        future.result(timeout=5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.wait(5000)
