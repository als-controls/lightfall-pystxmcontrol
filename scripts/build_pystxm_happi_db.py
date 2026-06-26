"""Generate the packaged pystxm_happi.json from config.DEFAULT_* dicts.

Run after changing config.py; commit the resulting JSON.
    <lightfall-venv>/python scripts/build_pystxm_happi_db.py
"""
import json
from pathlib import Path

import happi
from happi.backends.json_db import JSONBackend

from lightfall_pystxmcontrol import config

OUT = (Path(__file__).resolve().parents[1]
       / "src" / "lightfall_pystxmcontrol" / "pystxm_happi.json")


def build() -> None:
    OUT.write_text(json.dumps({}))
    client = happi.Client(database=JSONBackend(str(OUT)))

    for axis_name, axis_cfg in config.DEFAULT_AXES.items():
        client.add_item(happi.OphydItem(
            name=axis_name,
            device_class="lightfall_pystxmcontrol.devices.PystxmAxis",
            args=[], prefix="",
            kwargs={"name": "{{name}}", "axis_config": axis_cfg},
            active=True,
        ))

    client.add_item(happi.OphydItem(
        name="Counter1",
        device_class="lightfall_pystxmcontrol.devices.PystxmCounter",
        args=[], prefix="",
        kwargs={"name": "{{name}}", "daq_config": config.DEFAULT_COUNTER, "dwell": 1.0},
        active=True,
    ))

    client.add_item(happi.OphydItem(
        name="STXMLineFlyer",
        device_class="lightfall_pystxmcontrol.flyer.PystxmLineFlyer",
        args=[], prefix="",
        kwargs={"name": "{{name}}", "daq_config": config.DEFAULT_COUNTER,
                "x_axis_config": config.DEFAULT_AXES["SampleX"]},
        active=True,
    ))

    print(f"Wrote {OUT} ({len(client.search())} devices)")


if __name__ == "__main__":
    build()
