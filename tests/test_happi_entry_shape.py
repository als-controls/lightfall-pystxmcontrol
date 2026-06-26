"""Verify a pystxm ophyd-async device can be constructed from a happi entry."""
import asyncio
import json

import happi
from happi.backends.json_db import JSONBackend

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmAxis


def _client(tmp_path):
    db = tmp_path / "one.json"
    db.write_text(json.dumps({}))
    return happi.Client(database=JSONBackend(str(db)))


def test_happi_constructs_pystxm_axis_with_config(tmp_path):
    client = _client(tmp_path)
    client.add_item(happi.OphydItem(
        name="SampleX",
        device_class="lightfall_pystxmcontrol.devices.PystxmAxis",
        args=[],
        prefix="",
        kwargs={"name": "{{name}}", "axis_config": config.DEFAULT_AXES["SampleX"]},
        active=True,
    ))
    result = client.search()[0]
    dev = result.get()
    assert isinstance(dev, PystxmAxis)
    assert dev.name == "SampleX"
    # The config survived as a dict and connect() can build the sim motor.
    asyncio.run(dev.connect(mock=False))
    assert dev._axis_config["axis"] == "X"
