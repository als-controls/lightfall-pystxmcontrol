"""Run the sim raster and print a tiny ASCII heatmap of counts."""
import bluesky.plans as bp
from bluesky import RunEngine
from ophyd_async.core import init_devices

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmAxis, PystxmCounter

RE = RunEngine()
with init_devices():
    x = PystxmAxis(config.DEFAULT_AXES["SampleX"], name="SampleX")
    y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")
    det = PystxmCounter(config.DEFAULT_COUNTER, dwell=1.0, name="Counter1")

counts = []
RE(bp.grid_scan([det], x, -5, 5, 5, y, -5, 5, 5),
   lambda n, d: counts.append(d["data"]["Counter1"]) if n == "event" else None)
print(f"collected {len(counts)} points; min={min(counts)} max={max(counts)}")
