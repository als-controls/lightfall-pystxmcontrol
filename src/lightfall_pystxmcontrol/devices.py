"""ophyd-async device wrappers for pystxmcontrol hardware."""

import asyncio

from bluesky.protocols import Movable, Stoppable, Triggerable
from ophyd_async.core import (
    AsyncStatus,
    StandardReadable,
    StandardReadableFormat as Format,
    soft_signal_rw,
)

from . import config


class PystxmAxis(StandardReadable, Movable, Stoppable):
    """ophyd-async positioner wrapping a pystxmcontrol `motor` (sim mode)."""

    def __init__(self, axis_config: dict, name: str = ""):
        self._axis_config = axis_config
        self._motor = None  # built in connect()
        with self.add_children_as_readables(Format.HINTED_SIGNAL):
            self.readback = soft_signal_rw(float, initial_value=0.0)
        super().__init__(name=name)

    def set_name(self, name: str, *, child_name_separator: str | None = None):
        super().set_name(name, child_name_separator=child_name_separator)
        # Rename readback so read()/describe() key on the device name directly.
        if name:
            self.readback.set_name(name)

    async def connect(self, mock=False, timeout: float = 10.0,
                      force_reconnect: bool = False) -> None:
        if self._motor is None:
            self._motor = config.make_sim_motor(self._axis_config)
        await super().connect(mock=mock, timeout=timeout,
                              force_reconnect=force_reconnect)
        await self.readback.set(float(self._motor.getPos()))

    @AsyncStatus.wrap
    async def set(self, value: float):
        await asyncio.to_thread(self._motor.moveTo, value)
        await self.readback.set(float(self._motor.getPos()))

    async def stop(self, success: bool = True) -> None:
        # Sim motors complete moveTo synchronously; best-effort no-op.
        return None


class PystxmCounter(StandardReadable, Triggerable):
    """ophyd-async detector wrapping a pystxmcontrol `daq` (sim mode)."""

    def __init__(self, daq_config: dict, dwell: float = 1.0, name: str = ""):
        self._daq_config = daq_config
        self._dwell = dwell
        self._daq = None  # built in connect()
        with self.add_children_as_readables(Format.HINTED_SIGNAL):
            self.value = soft_signal_rw(float, initial_value=0.0)
        super().__init__(name=name)

    def set_name(self, name: str, *, child_name_separator: str | None = None):
        super().set_name(name, child_name_separator=child_name_separator)
        # Rename value so read()/describe() key on the bare device name directly.
        if name:
            self.value.set_name(name)

    async def connect(self, mock=False, timeout: float = 10.0,
                      force_reconnect: bool = False) -> None:
        if self._daq is None:
            self._daq = config.make_sim_counter(self._daq_config)
            self._daq.config(dwell=self._dwell)
        await super().connect(mock=mock, timeout=timeout,
                              force_reconnect=force_reconnect)

    @AsyncStatus.wrap
    async def trigger(self):
        data = await self._daq.getPoint()
        # getPoint returns ndarray of shape (1,); unwrap to scalar.
        scalar = float(data[0]) if hasattr(data, "__len__") else float(data)
        await self.value.set(scalar)
