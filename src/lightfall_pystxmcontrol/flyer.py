# src/lightfall_pystxmcontrol/flyer.py
import time as _time
from collections.abc import Iterator

import numpy as np
from bluesky.protocols import Collectable, Flyable
from ophyd_async.core import AsyncStatus

from . import config
from .devices import PystxmAxis


class PystxmLineFlyer(Flyable, Collectable):
    """bluesky Flyable wrapping a pystxmcontrol daq (sim) for one raster line.

    Per row: kickoff() moves the fast axis (X) to the row start and configures the
    daq for `nx` counts; complete() awaits getLine() (the row's Poisson counts);
    collect() emits one event with the count array, derived X positions, and Y.
    """

    def __init__(self, daq_config: dict, x_axis_config: dict, name: str = "Counter1"):
        self._daq_config = daq_config
        self._x_axis_config = x_axis_config
        self._name = name
        self._daq = None          # built in connect()
        self._x = None            # PystxmAxis, built in connect()
        self._row = None          # set by prepare()
        self._counts = None       # set by complete()

    @property
    def name(self) -> str:
        return self._name

    async def connect(self, mock: bool = False) -> None:
        if self._daq is None:
            self._daq = config.make_sim_counter(self._daq_config)
            self._x = PystxmAxis(self._x_axis_config, name="fast_x")
            await self._x.connect(mock=mock)

    def prepare(self, *, y: float, x_start: float, x_stop: float,
                nx: int, dwell: float) -> None:
        self._row = {"y": y, "x_start": x_start, "x_stop": x_stop,
                     "nx": nx, "dwell": dwell}
        self._counts = None

    @AsyncStatus.wrap
    async def kickoff(self) -> None:
        r = self._row
        await self._x.set(r["x_start"])                         # moveTo off-thread (PystxmAxis.set)
        self._daq.config(dwell=r["dwell"], count=r["nx"], samples=1)

    @AsyncStatus.wrap
    async def complete(self) -> None:
        data = await self._daq.getLine()                        # coroutine — await directly
        counts = np.asarray(data, dtype=float).ravel()
        if counts.size != self._row["nx"]:
            raise ValueError(f"getLine returned {counts.size} values, expected {self._row['nx']}")
        self._counts = counts

    def describe_collect(self) -> dict:
        nx = self._row["nx"]
        return {"primary": {
            "SampleX": {"source": "sim:linspace", "dtype": "array", "shape": [nx]},
            "SampleY": {"source": "sim:y", "dtype": "number", "shape": []},
            self._name: {"source": "sim:getLine", "dtype": "array", "shape": [nx]},
        }}

    def collect(self) -> Iterator[dict]:
        r = self._row
        x = np.linspace(r["x_start"], r["x_stop"], r["nx"])
        ts = _time.time()
        yield {
            "time": ts,
            "data": {"SampleX": x, "SampleY": r["y"], self._name: self._counts},
            "timestamps": {"SampleX": ts, "SampleY": ts, self._name: ts},
        }
