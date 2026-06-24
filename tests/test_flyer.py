# tests/test_flyer.py
import numpy as np
import pytest

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer


@pytest.fixture
async def flyer():
    fl = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"],
                         name="Counter1")
    await fl.connect(mock=False)
    return fl


async def test_one_cycle_yields_one_line_event(flyer):
    nx = 6
    flyer.prepare(y=2.0, x_start=-3.0, x_stop=3.0, nx=nx, dwell=1.0)
    await flyer.kickoff()
    await flyer.complete()
    events = list(flyer.collect())
    assert len(events) == 1
    data = events[0]["data"]
    assert len(data["Counter1"]) == nx
    assert (np.asarray(data["Counter1"]) > 0).all()
    assert len(data["SampleX"]) == nx
    assert data["SampleX"][0] == pytest.approx(-3.0)
    assert data["SampleX"][-1] == pytest.approx(3.0)
    assert data["SampleY"] == pytest.approx(2.0)


async def test_describe_collect_reports_arrays(flyer):
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0)
    desc = flyer.describe_collect()["primary"]
    assert desc["Counter1"]["dtype"] == "array"
    assert desc["Counter1"]["shape"] == [4]
    assert desc["SampleX"]["dtype"] == "array"
    assert desc["SampleX"]["shape"] == [4]
    assert desc["SampleY"]["dtype"] == "number"
