"""EPICS line flyer driving the spec-#2 FLY PVGroup (classic ophyd).

Per row: prepare() writes the line config and ARMs (validated IOC-side);
kickoff() dispatches the GO put (put-completion = line done); complete()
returns that put's Status; collect() verifies the INDEX increment (the IOC's
write-then-increment contract guarantees the waveforms are fresh once INDEX
moved) and emits ONE event with the same keys/shapes as the pre-EPICS flyer,
so contract.py, plans, and viz are untouched.
"""
import time as _time
from collections.abc import Iterator

import numpy as np
from bluesky.protocols import Collectable, Flyable

from . import epics_env

epics_env.ensure_caproto_layer()  # before any ophyd import

from ophyd import Component as Cpt  # noqa: E402
from ophyd import Device, EpicsSignal, EpicsSignalRO  # noqa: E402
from ophyd.status import Status  # noqa: E402

_DAQ_KEY = "default"  # sim_daq.json key; FLY data waveform is :DATA:{key}


def _null_status() -> Status:
    st = Status()
    st.set_finished()
    return st


def _as_text(value) -> str:
    """Normalize the :ERROR char-waveform-as-string read (may come back as bytes)."""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


class StxmLineFlyer(Device, Flyable, Collectable):
    X_DATA_KEY = "SampleX"
    Y_DATA_KEY = "SampleY"

    x_start = Cpt(EpicsSignal, ":START", kind="config")
    x_stop = Cpt(EpicsSignal, ":STOP", kind="config")
    npoints = Cpt(EpicsSignal, ":NPOINTS", kind="config")
    dwell = Cpt(EpicsSignal, ":DWELL", kind="config")
    arm = Cpt(EpicsSignal, ":ARM", put_complete=True, kind="omitted")
    go = Cpt(EpicsSignal, ":GO", put_complete=True, kind="omitted")
    abort = Cpt(EpicsSignal, ":ABORT", kind="omitted")
    state = Cpt(EpicsSignalRO, ":STATE", string=True, kind="omitted")
    error = Cpt(EpicsSignalRO, ":ERROR", string=True, kind="omitted")
    index = Cpt(EpicsSignalRO, ":INDEX", kind="omitted")
    pos = Cpt(EpicsSignalRO, ":POS", kind="omitted")
    data = Cpt(EpicsSignalRO, f":DATA:{_DAQ_KEY}", kind="omitted")

    def __init__(self, prefix, *, name="STXMLineFlyer", **kwargs):
        super().__init__(prefix, name=name, **kwargs)
        self._row = None
        self._index0 = None
        self._go_status = None

    # -- per-row protocol ---------------------------------------------------
    def prepare(self, *, y: float, x_start: float, x_stop: float,
                nx: int, dwell: float) -> None:
        for sig, value in ((self.x_start, float(x_start)),
                           (self.x_stop, float(x_stop)),
                           (self.npoints, int(nx)),
                           (self.dwell, float(dwell))):
            sig.set(value).wait(timeout=10)
        self.arm.set(1).wait(timeout=30)
        state = self.state.get()
        if state != "ARMED":
            raise RuntimeError(
                f"{self.name}: ARM failed (STATE={state}): {_as_text(self.error.get())}")
        self._row = {"y": float(y), "nx": int(nx)}
        self._index0 = int(self.index.get())
        self._go_status = None

    def kickoff(self) -> Status:
        if self._row is None:
            raise RuntimeError(f"{self.name}: kickoff() before prepare()")
        self._go_status = self.go.set(1)  # put-completion == line done
        return _null_status()

    def complete(self) -> Status:
        if self._go_status is None:
            raise RuntimeError(f"{self.name}: complete() before kickoff()")
        return self._go_status

    # -- collection ----------------------------------------------------------
    def describe_collect(self) -> dict:
        nx = self._row["nx"]
        return {"primary": {
            self.X_DATA_KEY: {"source": f"epics:{self.prefix}:POS",
                              "dtype": "array", "shape": [nx]},
            self.Y_DATA_KEY: {"source": "epics:y-setpoint",
                              "dtype": "number", "shape": []},
            self.name: {"source": f"epics:{self.prefix}:DATA:{_DAQ_KEY}",
                        "dtype": "array", "shape": [nx]},
        }}

    def collect(self) -> Iterator[dict]:
        r = self._row
        idx = int(self.index.get())
        state = self.state.get()
        if idx != self._index0 + 1 or state != "ARMED":
            raise RuntimeError(
                f"{self.name}: line failed (INDEX {self._index0}->{idx}, "
                f"STATE={state}): {_as_text(self.error.get())}")
        x = np.asarray(self.pos.get(), dtype=float)[: r["nx"]]
        counts = np.asarray(self.data.get(), dtype=float)[: r["nx"]]
        ts = _time.time()
        yield {
            "time": ts,
            "data": {self.X_DATA_KEY: x, self.Y_DATA_KEY: r["y"],
                     self.name: counts},
            "timestamps": {self.X_DATA_KEY: ts, self.Y_DATA_KEY: ts,
                           self.name: ts},
        }
