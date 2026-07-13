"""Classic-ophyd EPICS devices for the spec-#2 pystxmcontrol IOC layer.

Axes need no wrapper: they are stock ``ophyd.EpicsMotor`` instances created
straight from happi entries (the IOC motor record's .VAL put-completion makes
``move()`` block until the move is done).
"""
from . import epics_env

epics_env.ensure_caproto_layer()  # before any ophyd import

from ophyd import Component as Cpt  # noqa: E402
from ophyd import Device, EpicsSignal, EpicsSignalRO  # noqa: E402


class StxmCounter(Device):
    """Point-mode counter over the spec-#2 DAQ IOC group.

    ``trigger()`` puts 1 to :ACQUIRE with put-completion — the returned Status
    finishes when the IOC has completed the acquisition and updated :COUNTS.
    """

    dwell = Cpt(EpicsSignal, ":DWELL", kind="config")
    acquire = Cpt(EpicsSignal, ":ACQUIRE", put_complete=True, kind="omitted")
    counts = Cpt(EpicsSignalRO, ":COUNTS", kind="hinted")
    rate = Cpt(EpicsSignalRO, ":RATE", kind="normal")

    def __init__(self, prefix, *, name, **kwargs):
        super().__init__(prefix, name=name, **kwargs)
        # Read/describe key on the bare device name (matches the pre-EPICS
        # PystxmCounter behavior and the plans/viz expectations).
        self.counts.name = self.name

    def trigger(self):
        return self.acquire.set(1)
