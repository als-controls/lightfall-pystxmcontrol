import bluesky.plans as bp
from bluesky import RunEngine
from ophyd_async.core import init_devices

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmAxis, PystxmCounter


def test_grid_scan_emits_full_document_stream():
    RE = RunEngine()
    with init_devices():  # connects on the RE-compatible loop
        x = PystxmAxis(config.DEFAULT_AXES["SampleX"], name="SampleX")
        y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")
        det = PystxmCounter(config.DEFAULT_COUNTER, dwell=1.0, name="Counter1")

    docs = []
    nx, ny = 3, 4
    RE(bp.grid_scan([det], x, -1, 1, nx, y, -2, 2, ny),
       lambda name, doc: docs.append((name, doc)))

    names = [n for n, _ in docs]
    assert names[0] == "start"
    assert names[-1] == "stop"
    assert names.count("event") == nx * ny
    event = next(d for n, d in docs if n == "event")
    assert {"SampleX", "SampleY", "Counter1"} <= event["data"].keys()
    assert event["data"]["Counter1"] > 0
