"""Local-only simulator. Shares the public client interface, never opens a socket."""

import asyncio
import copy
import math
import time

from .client import block_reason
from .errors import CommandBlocked


class DemoClient:
    def __init__(self, on_state=None):
        self.on_state = on_state
        self.connected = False
        self.task = None
        self.tx_demo = False
        self.state = dict(
            power="on",
            operate=False,
            tx=False,
            tuning=False,
            atu="off",
            input=1,
            tx_ant=1,
            antenna_by_input=[1, 2],
            level="1k",
            band="20m",
            frequency_hz=14210000,
            input_frequencies_hz=[14210000, 7074000],
            protection_lamp=False,
            protect=0,
            temps={"intake": 28},
            humidity=40,
            device_clock="12:00:00",
            measurement_sources={},
        )

    @property
    def snapshot(self):
        return {**copy.deepcopy(self.state), "connected": self.connected, "age_s": 0, "demo": True}

    def publish(self):
        if self.on_state:
            self.on_state(self.snapshot)

    async def connect(self):
        self.connected = True
        self.task = asyncio.create_task(self._tick())
        self.publish()

    async def disconnect(self):
        self.connected = False
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        self.publish()

    async def _tick(self):
        while True:
            on = self.state["power"] == "on"
            tx = on and self.state["operate"] and self.tx_demo
            self.state["tx"] = tx or self.state["tuning"]
            watts = (
                round((480 if self.state["level"] == "500" else 950) + 20 * math.sin(time.monotonic() * 2))
                if tx
                else 0
            )
            current = 20 if self.state["level"] == "500" else 28
            self.state.update(
                out_w=watts if on else None,
                pa_a=current if tx else 0,
                pa_v=51 if on and self.state["operate"] else None,
                swr_ant=1.5 if tx else None,
                alc=0.5 if tx else 0,
                device_clock=time.strftime("%H:%M:%S"),
            )
            percents = dict(
                po=watts / 1500 * 100,
                id=current / 50 * 100 if tx else 0,
                vd=71 if self.state["pa_v"] else 0,
                swr=12 if tx else 0,
                alc=50 if tx else 0,
                temp=18,
            )
            self.state["meter_display"] = (
                dict(
                    mode="bars",
                    values={
                        name: {"percent": value, "raw": round(value * 0.83)}
                        for name, value in percents.items()
                    },
                )
                if on
                else None
            )
            self.publish()
            await asyncio.sleep(0.1)

    async def command(self, name, **args):
        reason = block_reason(self.snapshot, name, args, 230)
        if reason:
            raise CommandBlocked(reason)
        await asyncio.sleep(0.08)
        if name == "power":
            self.state["power"] = args["value"]
            if args["value"] == "off":
                self.state.update(operate=False, tuning=False, tx=False)
                self.tx_demo = False
        elif name == "operate":
            self.state["operate"] = args["value"]
        elif name == "tuner":
            self.state["atu"] = args["value"]
        elif name == "input":
            self.state["input"] = args["n"]
            self.state["tx_ant"] = self.state["antenna_by_input"][args["n"] - 1]
            self.state["frequency_hz"] = self.state["input_frequencies_hz"][args["n"] - 1]
            self.state["band"] = "20m" if args["n"] == 1 else "40m"
        elif name == "antenna":
            self.state["tx_ant"] = args["n"]
            self.state["antenna_by_input"][self.state["input"] - 1] = args["n"]
        elif name == "level":
            self.state["level"] = args["id"]
        elif name == "tune":
            self.state.update(tuning=True, atu="tune", tx=True)
            self.publish()
            await asyncio.sleep(1.2)
            self.state.update(tuning=False, atu="on", tx=False)
        self.publish()
        return {"confirmation": "simulated"}
