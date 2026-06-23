"""ophyd-async device wrappers for pystxmcontrol hardware."""

import asyncio

from bluesky.protocols import Movable, Stoppable
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
