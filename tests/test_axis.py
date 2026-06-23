# tests/test_axis.py
import pytest
from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmAxis


@pytest.fixture
async def axis():
    ax = PystxmAxis(config.DEFAULT_AXES["SampleX"], name="SampleX")
    await ax.connect(mock=False)
    return ax


async def test_set_moves_and_readback_updates(axis):
    await axis.set(7.5)
    reading = await axis.read()
    # readback is named after the device
    val = reading["SampleX"]["value"]
    assert val == pytest.approx(7.5)


async def test_describe_reports_float(axis):
    desc = await axis.describe()
    assert desc["SampleX"]["dtype"] == "number"
