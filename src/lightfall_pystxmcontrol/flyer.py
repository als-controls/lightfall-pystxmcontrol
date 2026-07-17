"""EPICS line flyer driving the spec-#2 FLY PVGroup (classic ophyd).

Per row: prepare() writes the line config and ARMs (validated IOC-side);
kickoff() dispatches the GO put (put-completion = line done); complete()
returns that put's Status; collect() verifies the INDEX increment (the IOC's
write-then-increment contract guarantees the waveforms are fresh once INDEX
moved) and emits ONE event with the same keys/shapes as the pre-EPICS flyer,
so contract.py, plans, and viz are untouched.
"""
import threading
import time as _time
from collections.abc import Iterator

import numpy as np
from bluesky.protocols import Collectable, Flyable, Preparable

from . import epics_env

epics_env.ensure_caproto_layer()  # before any ophyd import

from ophyd import Component as Cpt  # noqa: E402
from ophyd import Device, EpicsSignal, EpicsSignalRO  # noqa: E402
from ophyd.status import InvalidState, Status  # noqa: E402

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


class StxmLineFlyer(Device, Flyable, Collectable, Preparable):
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
        # Monotonic prepare() generation: incremented synchronously at the
        # top of every prepare() so a still-in-flight worker from a
        # superseded call can detect it has been overtaken and no-op instead
        # of clobbering the newer call's _row/_index0 (lost-update guard for
        # callers that don't honor bps.prepare(wait=True) -- interactive or
        # future direct use).
        self._prepare_epoch = 0
        # Guards the epoch bump + state reset in prepare() against the
        # epoch-check + state write in its worker thread, so the two are
        # atomic w.r.t. each other (a bare check-then-write would leave a
        # few-bytecode window in which a superseded worker could still
        # clobber the newer call's _row/_index0).
        self._prepare_lock = threading.Lock()
        # complete()'s STATE/ERROR failure path uses ONE persistent
        # subscription for the object's lifetime (rather than
        # subscribing/unsubscribing per complete() call): rapid subscribe/
        # unsubscribe churn on :STATE was observed to destabilize the
        # underlying CA client (RemoteProtocolError / dropped circuits)
        # under the full test suite. complete() just points
        # ``_active_complete_status`` at its Status while it's live.
        self._active_complete_status = None
        self.state.subscribe(self._on_state_change, run=False)

    # -- per-row protocol ---------------------------------------------------
    def prepare(self, *, y: float, x_start: float, x_stop: float,
                nx: int, dwell: float) -> Status:
        """Configure + ARM the line, off the RE thread.

        The 4 config puts + ARM (up to 40s of blocking CA round-trips) run on
        a background daemon thread so the RunEngine thread stays responsive
        to pause/abort while this is in flight; the caller awaits the
        returned Status (bps.prepare(..., wait=True)) instead of blocking
        in-line.
        """
        # Invalidate synchronously at entry: any failure below (or any call
        # to kickoff()/complete() while this prepare() is still running on
        # the background thread) must observe an un-prepared flyer rather
        # than stale state from a previous row. Bump the generation under the
        # lock and capture it in this call's worker; if a newer prepare()
        # runs before this worker finishes, the captured epoch will no longer
        # match and the worker no-ops instead of clobbering the newer call's
        # _row/_index0 (lost-update guard).
        with self._prepare_lock:
            self._row = None
            self._index0 = None
            self._go_status = None
            self._prepare_epoch += 1
            epoch = self._prepare_epoch

        st = Status(timeout=60)

        def _worker():
            try:
                for sig, value in ((self.x_start, float(x_start)),
                                   (self.x_stop, float(x_stop)),
                                   (self.npoints, int(nx)),
                                   (self.dwell, float(dwell))):
                    sig.set(value).wait(timeout=10)
                self.arm.set(1).wait(timeout=30)
                state = self.state.get()
                if state != "ARMED":
                    raise RuntimeError(
                        f"{self.name}: ARM failed (STATE={state}): "
                        f"{_as_text(self.error.get())}")
                index0 = int(self.index.get())
                # Epoch-check + state write must be atomic w.r.t. a
                # concurrent prepare()'s bump + reset (hence the lock): a
                # superseded worker must not write _row/_index0 over the
                # newer call's state, nor report success against it.
                with self._prepare_lock:
                    if epoch != self._prepare_epoch:
                        raise RuntimeError(
                            f"{self.name}: prepare() superseded by a newer call")
                    self._row = {"y": float(y), "nx": int(nx),
                                 "dwell_ms": float(dwell)}
                    self._index0 = index0
            except Exception as exc:  # noqa: BLE001 - surfaced via Status
                try:
                    st.set_exception(exc)
                except InvalidState:
                    pass
            else:
                try:
                    st.set_finished()
                except InvalidState:
                    pass

        threading.Thread(target=_worker, daemon=True,
                          name=f"{self.name}-prepare").start()
        return st

    def kickoff(self) -> Status:
        if self._row is None:
            raise RuntimeError(f"{self.name}: kickoff() before prepare()")
        self._go_status = self.go.set(1)  # put-completion == line done
        return _null_status()

    def _on_state_change(self, value=None, **kwargs):
        """Persistent :STATE monitor callback (subscribed once in __init__).

        Only acts if a complete() Status is currently outstanding, and only
        on the ERROR transition -- this also fires on every other
        transition (ARMED, FLYING, ...) for a healthy line, which are not
        failures.
        """
        if _as_text(value) != "ERROR":
            return
        st = self._active_complete_status
        if st is None:
            return
        # `value` is whatever this particular monitor event carried, which
        # can be a *stale, queued* notification: complete() re-establishes
        # `_active_complete_status` on every call, and under back-to-back
        # prepare()/kickoff()/complete() cycles (e.g. this test suite's
        # sub-10ms sim lines) an ERROR notification from an EARLIER cycle
        # can still be working through the CA client's dispatch pipeline
        # when a NEWER cycle's complete() has already taken over the slot.
        # Reconfirm against a fresh, synchronous read of the *current* PV
        # value before failing -- this answers the question we actually
        # care about ("is the line this Status tracks failing *now*?")
        # instead of trusting a payload that may already be out of date.
        # (Residual gap: STATE could flip ERROR->non-ERROR between this
        # callback firing and the reread; the sim IOC never leaves ERROR
        # without a fresh ARM, so in practice this only trims false
        # positives, never introduces false negatives.)
        if _as_text(self.state.get()) != "ERROR":
            return
        try:
            st.set_exception(RuntimeError(
                f"{self.name}: line failed (STATE=ERROR): "
                f"{_as_text(self.error.get())}"))
        except InvalidState:
            pass  # already resolved (race with the GO-done callback)

    def complete(self) -> Status:
        """Bounded Status for the in-flight line.

        Resolves when the GO put's Status finishes (chained via callback),
        but fails early if :STATE transitions to ERROR (IOC-side line
        failure, delivered via the persistent ``_on_state_change`` monitor),
        and auto-times-out (StatusTimeoutError) if neither happens -- e.g.
        the IOC died mid-line and the GO put itself never completes.
        """
        if self._go_status is None:
            raise RuntimeError(f"{self.name}: complete() before kickoff()")
        row = self._row
        nx = row["nx"]
        dwell_ms = row["dwell_ms"]
        timeout = max(30.0, nx * (dwell_ms / 1000.0) + 10.0)
        st = Status(timeout=timeout)
        self._active_complete_status = st

        def _on_go_done(go_status):
            exc = go_status.exception()
            try:
                if exc is not None:
                    st.set_exception(exc)
                else:
                    st.set_finished()
            except InvalidState:
                pass  # already resolved (e.g. STATE=ERROR beat us here)

        # Catch an already-ERROR state synchronously: the persistent
        # subscription above only reacts to *future* transitions delivered
        # by the CA monitor, so an ERROR that happened before this call (and
        # thus before ``_active_complete_status`` pointed at ``st``) needs an
        # explicit check here. (_on_state_change() re-confirms with its own
        # fresh read, so passing the raw value through is enough.)
        self._on_state_change(value=self.state.get())

        self._go_status.add_callback(_on_go_done)

        def _clear_active(_):
            if self._active_complete_status is st:
                self._active_complete_status = None

        st.add_callback(_clear_active)
        return st

    # -- collection ----------------------------------------------------------
    def describe_collect(self) -> dict:
        if self._row is None:
            raise RuntimeError(f"{self.name}: describe_collect() before prepare()")
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
