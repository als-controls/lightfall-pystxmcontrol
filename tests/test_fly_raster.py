# tests/test_fly_raster.py
import asyncio

import numpy as np
import pytest
from bluesky import RunEngine

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmAxis
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
from lightfall_pystxmcontrol.plans import stxm_fly_raster


def test_fly_raster_emits_one_event_per_line():
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"],
                            name="Counter1")
    y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")
    asyncio.run(_connect(flyer, y))

    nx, ny = 8, 4
    docs = []
    RE = RunEngine()
    RE(stxm_fly_raster(flyer, y, y_start=-2, y_stop=2, ny=ny,
                       x_start=-4, x_stop=4, nx=nx, dwell=1.0),
       lambda n, d: docs.append((n, d)))

    names = [n for n, _ in docs]
    assert names[0] == "start"
    assert names[-1] == "stop"
    assert names.count("event_page") == ny          # bluesky 1.14.6 paginates collect → event_page
    ev = next(d for n, d in docs if n == "event_page")
    assert len(ev["data"]["Counter1"][0]) == nx      # event_page: data[key] is a list of per-event arrays
    assert len(ev["data"]["SampleX"][0]) == nx
    assert (np.asarray(ev["data"]["Counter1"][0]) > 0).all()


async def _connect(flyer, y):
    await flyer.connect(mock=False)
    await y.connect(mock=False)
