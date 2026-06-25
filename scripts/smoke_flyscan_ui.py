"""Run the sim STXM fly raster through Lightfall's plan-surfacing + device-binding path."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from lightfall_pystxmcontrol.backend import PystxmStxmBackend
from lightfall_pystxmcontrol.plan_plugin import StxmFlyRasterPlanPlugin

backend = PystxmStxmBackend()
assert backend.connect(), "backend failed to connect"

# Bind devices the way the UI resolver does: by name, to the backend's connected instances.
flyer = backend.get_device_by_name("STXMLineFlyer")._ophyd_device
y_axis = backend.get_device_by_name("SampleY")._ophyd_device
assert flyer is not None and y_axis is not None

plan_func = StxmFlyRasterPlanPlugin().get_plan_function()
nx, ny = 10, 6

# Bare RunEngine proves the same launch contract as the UI path
# (plan/engine path is plan-agnostic — Phase 1/2a finding).
from bluesky import RunEngine
docs = []
RE = RunEngine()
RE(plan_func(flyer, y_axis, y_start=-5, y_stop=5, ny=ny,
             x_start=-5, x_stop=5, nx=nx, dwell=1.0),
   lambda n, d: docs.append((n, d)))

names = [n for n, _ in docs]
# The count data key is "STXMLineFlyer" — the flyer keys collect() on its own .name.
rows = [d["data"]["STXMLineFlyer"][0] for n, d in docs if n == "event_page"]
assert names[:1] == ["start"] and names[-1:] == ["stop"], names[:3]
assert len(rows) == ny, f"expected {ny} lines, got {len(rows)}"
allcounts = np.concatenate([np.asarray(r) for r in rows])
assert allcounts.shape == (ny * nx,), f"expected {ny*nx} pixels, got {allcounts.shape}"
print(f"fly raster launchable via Lightfall (backend+plan plugin): {ny} lines x {nx} pts; "
      f"min={allcounts.min():.0f} max={allcounts.max():.0f}")
