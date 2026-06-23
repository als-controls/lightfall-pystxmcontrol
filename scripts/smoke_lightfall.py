"""Run the sim STXM raster through Lightfall's real BlueskyEngine."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # headless-safe; harmless with a display

import bluesky.plans as bp
from PySide6.QtWidgets import QApplication

from lightfall.acquire.engine import get_engine
from lightfall_pystxmcontrol.plugin import PystxmBackendPlugin

app = QApplication.instance() or QApplication([])
engine = get_engine("bluesky")

# RE is created lazily on a worker thread — wait for it
re = None
for _ in range(100):
    re = engine.RE
    if re is not None:
        break
    app.processEvents()
    time.sleep(0.05)
assert re is not None, "BlueskyEngine RE never became available"

be = PystxmBackendPlugin().create_backend()
be.connect()
x = be.get_device_by_name("SampleX")._ophyd_device
y = be.get_device_by_name("SampleY")._ophyd_device
det = be.get_device_by_name("Counter1")._ophyd_device

docs = []
re.subscribe(lambda n, d: docs.append((n, d)))   # collect directly off the RE
engine(bp.grid_scan([det], x, -5, 5, 5, y, -5, 5, 5))  # ENQUEUE (worker thread runs it)

deadline = time.time() + 60
while time.time() < deadline:
    if "stop" in [n for n, _ in docs] and engine.is_idle:
        break
    app.processEvents()
    time.sleep(0.05)

names = [n for n, _ in docs]
counts = [d["data"]["Counter1"] for n, d in docs if n == "event"]
assert names[:1] == ["start"] and names[-1:] == ["stop"], names[:3]
assert len(counts) == 25, f"expected 25 points, got {len(counts)}"
print(
    f"grid_scan ran via Lightfall BlueskyEngine: {len(counts)} points; "
    f"min={min(counts)} max={max(counts)}"
)
