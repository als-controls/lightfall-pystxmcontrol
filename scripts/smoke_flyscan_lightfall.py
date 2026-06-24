# scripts/smoke_flyscan_lightfall.py
"""Run the sim STXM fly raster through Lightfall's real BlueskyEngine."""
import os, time, asyncio
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication
from lightfall.acquire.engine import get_engine

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmAxis
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
from lightfall_pystxmcontrol.plans import stxm_fly_raster

app = QApplication.instance() or QApplication([])
engine = get_engine("bluesky")
re = None
for _ in range(100):
    re = engine.RE
    if re is not None:
        break
    app.processEvents(); time.sleep(0.05)
assert re is not None, "BlueskyEngine RE never became available"

async def _connect_all(fl, yax):
    await fl.connect(mock=False)
    await yax.connect(mock=False)


flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"], name="Counter1")
y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")
asyncio.run(_connect_all(flyer, y))

docs = []
re.subscribe(lambda n, d: docs.append((n, d)))
nx, ny = 10, 6
engine(stxm_fly_raster(flyer, y, y_start=-5, y_stop=5, ny=ny,
                       x_start=-5, x_stop=5, nx=nx, dwell=1.0))

deadline = time.time() + 60
while time.time() < deadline:
    if "stop" in [n for n, _ in docs] and engine.is_idle:
        break
    app.processEvents(); time.sleep(0.05)

names = [n for n, _ in docs]
rows = [d["data"]["Counter1"][0] for n, d in docs if n == "event_page"]   # event_page: unwrap [0]
assert names[:1] == ["start"] and names[-1:] == ["stop"], names[:3]
assert len(rows) == ny, f"expected {ny} lines, got {len(rows)}"
allcounts = np.concatenate([np.asarray(r) for r in rows])
print(f"fly raster ran via Lightfall BlueskyEngine: {ny} lines x {nx} pts; "
      f"min={allcounts.min():.0f} max={allcounts.max():.0f}")
