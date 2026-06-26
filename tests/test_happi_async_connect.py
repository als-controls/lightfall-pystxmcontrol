"""A happi-built pystxm device connects via check_connection (async path)."""
import asyncio
import threading
from importlib.resources import files

import pytest

from lightfall.devices import async_connect
from lightfall.devices.backends.happi import HappiBackend


class _RunningLoop:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._t = threading.Thread(target=self.loop.run_forever, daemon=True)
        self._t.start()
        while not self.loop.is_running():
            pass

    @property
    def event_loop(self):
        return self.loop

    def close(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._t.join(timeout=2.0)
        self.loop.close()


@pytest.fixture
def running_engine(monkeypatch):
    eng = _RunningLoop()
    monkeypatch.setattr(async_connect, "get_engine", lambda: eng)
    yield eng
    eng.close()


def _backend():
    db = str(files("lightfall_pystxmcontrol").joinpath("pystxm_happi.json"))
    be = HappiBackend(path=db, instantiate="background")
    be.connect()
    return be


def test_axis_connects_and_reads_via_pipeline(running_engine):
    be = _backend()
    info = next(d for d in be.list_devices(active_only=False) if d.name == "SampleX")
    obj = be.instantiate(info)              # constructs (not connected yet)
    assert obj._motor is None               # sim motor not built until connect()
    ok = be.check_connection(obj, timeout=5.0)  # async path drives connect()
    assert ok is True
    assert obj._motor is not None           # sim motor built; device is connected
    # functional: readback reads a real value from the sim motor
    reading = asyncio.run_coroutine_threadsafe(obj.read(), running_engine.loop).result(5.0)
    assert "SampleX" in reading
