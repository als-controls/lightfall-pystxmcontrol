"""Spike: pin (a) getLine line acquisition and (b) the inline-Flyable collect path."""
import asyncio
import time as _time

import numpy as np
import bluesky.plan_stubs as bps
from bluesky import RunEngine
from bluesky.protocols import Collectable, Flyable
from ophyd_async.core import AsyncStatus

from lightfall_pystxmcontrol import config


def pin_getline():
    d = config.make_sim_counter(config.DEFAULT_COUNTER)  # build + meta.update + start
    nx = 5
    d.config(dwell=1.0, count=nx, samples=1)             # line config (concrete signature)
    data = asyncio.run(d.getLine())
    print("getLine type:", type(data), "len:", len(data), "sample:", repr(data)[:60])
    assert len(data) == nx, (len(data), nx)
    return type(data).__name__, len(data)


class _TrivialLineFlyer(Flyable, Collectable):
    """Minimal inline flyer with an ARRAY data key, to de-risk the collect path."""
    name = "Counter1"

    def __init__(self, nx):
        self._nx = nx
        self._counts = None

    @AsyncStatus.wrap
    async def kickoff(self):
        await asyncio.sleep(0)

    @AsyncStatus.wrap
    async def complete(self):
        self._counts = np.arange(self._nx, dtype=float) + 1.0

    def describe_collect(self):
        return {"primary": {
            "SampleX": {"source": "sim", "dtype": "array", "shape": [self._nx]},
            "SampleY": {"source": "sim", "dtype": "number", "shape": []},
            "Counter1": {"source": "sim", "dtype": "array", "shape": [self._nx]},
        }}

    def collect(self):
        ts = _time.time()
        yield {"time": ts,
               "data": {"SampleX": np.linspace(-1, 1, self._nx),
                        "SampleY": 0.0, "Counter1": self._counts},
               "timestamps": {"SampleX": ts, "SampleY": ts, "Counter1": ts}}


def pin_flyable():
    nx = 5
    flyer = _TrivialLineFlyer(nx)

    def fly_one_line(fl):
        yield from bps.open_run()
        yield from bps.kickoff(fl, wait=True)
        yield from bps.complete(fl, wait=True)
        yield from bps.collect(fl)
        yield from bps.close_run()

    docs = []
    RunEngine()(fly_one_line(flyer), lambda n, d: docs.append((n, d)))
    names = [n for n, _ in docs]
    # bluesky 1.14.6: bps.collect emits event_page (not event).
    # event_page["data"][key] is a list of per-event arrays; [0] is the first event's array.
    ep = next(d for n, d in docs if n == "event_page")
    print("flyable doc names:", names)
    print("event_page Counter1 len:", len(ep["data"]["Counter1"][0]),
          "SampleX len:", len(ep["data"]["SampleX"][0]))
    assert names[0] == "start" and names[-1] == "stop"
    assert names.count("event_page") == 1
    assert len(ep["data"]["Counter1"][0]) == nx


if __name__ == "__main__":
    t, n = pin_getline()
    print(f"--- getLine pinned: {t} len {n} ---")
    pin_flyable()
    print("--- inline Flyable collect path OK ---")
