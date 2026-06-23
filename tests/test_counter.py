# tests/test_counter.py
import pytest
from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmCounter


@pytest.fixture
async def counter():
    det = PystxmCounter(config.DEFAULT_COUNTER, dwell=1.0, name="Counter1")
    await det.connect(mock=False)
    return det


async def test_trigger_then_read_gives_positive_count(counter):
    await counter.trigger()
    reading = await counter.read()
    assert reading["Counter1"]["value"] > 0


async def test_describe_reports_number(counter):
    desc = await counter.describe()
    assert desc["Counter1"]["dtype"] == "number"
