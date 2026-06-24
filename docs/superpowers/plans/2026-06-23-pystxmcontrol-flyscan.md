# pystxmcontrol → Lightfall Simulated Fly-Scan (Phase 2a) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a simulated STXM line-by-line *fly* raster in Lightfall — a custom bluesky `Flyable` sweeps the fast axis and emits one event per line via `daq.getLine()` — on a bare `RunEngine` and through Lightfall's `BlueskyEngine`.

**Architecture:** Additive to the existing `lightfall-pystxmcontrol` package (Phase-1 devices/backend/plugin untouched). A `PystxmLineFlyer` implements bluesky's `Flyable` + `Collectable` protocols over a pystxmcontrol `daq` (sim) configured for a line (`config(dwell, count=nx, samples=1)` → `getLine()` returns `nx` Poisson counts) plus the fast-axis `PystxmAxis`. A `stxm_fly_raster` plan steps the slow axis (Y) and flies the fast axis (X) per row, emitting one event per line (count array + scalar Y + derived X array).

**Tech Stack:** Python, ophyd-async (`AsyncStatus`), bluesky (`Flyable`/`Collectable`, `plan_stubs`), pystxmcontrol (sim drivers), Lightfall (`BlueskyEngine`), pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-23-pystxmcontrol-flyscan-design.md`

## Global Constraints

- **Sim source:** devices connect with `mock=False`; pystxmcontrol's own `simulation=True` path MUST run (we test David's drivers, not ophyd-async's mock).
- **`getLine` is a coroutine** → `await` directly; never wrap in a new event loop. **`moveTo` is blocking sync** → call via `await asyncio.to_thread(...)` (reuse `PystxmAxis.set`).
- **Line config (concrete, verified):** `keysight53230A.config(self, dwell, count=1, samples=1, trigger='BUS', output='OFF')`. A line of `nx` counts = `config(dwell=dwell, count=nx, samples=1)`; `getLine()` then returns a 1-D `numpy.ndarray` of length `count*samples == nx`. (Confirm empirically in Task 1.)
- **Reuse, don't duplicate:** the flyer builds its daq via the existing `config.make_sim_counter` (Phase 1) — there is NO separate `make_sim_line_daq` (it would be identical; line vs point is only `count` + calling `getLine` vs `getPoint`). Reuse `config.DEFAULT_COUNTER` and `config.DEFAULT_AXES`.
- **Event contract:** **one event per line** — `data = {"SampleX": <ndarray[nx]>, "SampleY": <float>, "Counter1": <ndarray[nx]>}`. X positions are **derived** `numpy.linspace(x_start, x_stop, nx)` (sim has no per-point encoder readback).
- **Flyer protocol:** custom `Flyable` (`kickoff`/`complete`/`name`) + `Collectable` (`describe_collect`); legacy inline `collect` (yields `{"time","data","timestamps"}` events), modeled on `ophyd.sim.MockFlyer`. No `Writer`/`StreamResource`, no `declare_stream`. `kickoff`/`complete` return `AsyncStatus` (the Phase-1 async pattern, proven through both a bare `RunEngine` and Lightfall's `BlueskyEngine`).
- **Additive only:** do NOT modify `devices.py`, `backend.py`, `plugin.py`, `manifest.py`, or any Lightfall-core file.
- **Interpreter / tests:** run in **Lightfall's 3.14 venv** via `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest` — never bare `pytest`. `pystxmcontrol` is already installed there from the pinned als-controls fork; `ophyd-async`/`bluesky`/`numpy`/`pytest`/`pytest-asyncio` present (`asyncio_mode = "auto"`). Importing the package prints ~6 upstream "X not available" lines — expected noise, not a failure.
- **No `git add -A`:** stage explicit paths only.
- **Package repo:** `~/PycharmProjects/ncs/lightfall-pystxmcontrol/`.
- **Commit trailers** (every commit):
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo
  ```

---

### Task 1: Spike — pin `getLine` line acquisition + the inline-`Flyable` collect path

Prove the two unknowns before wrapping: (a) the exact line `config` call makes `getLine()` return `nx` counts, and (b) a minimal inline `Flyable` (with an **array-valued** data key) drives a bare `RunEngine` and emits one event per line. **This is a spike, not TDD.**

**Files:**
- Create: `scripts/smoke_getline.py`
- Modify: `NOTES-environment.md` (append a "Phase 2a — fly-scan spike" section)

**Interfaces:**
- Produces: recorded facts — the working line-`config` call + that `len(getLine()) == nx`; the working `describe_collect`/`collect`/`kickoff`/`complete` shapes for an array-valued inline `Flyable` through a bare `RunEngine`. Steers Task 2.

- [ ] **Step 1: Write `scripts/smoke_getline.py`**

```python
"""Spike: pin (a) getLine line acquisition and (b) the inline-Flyable collect path."""
import asyncio
import time as _time

import numpy as np
import bluesky.plan_stubs as bps
from bluesky import RunEngine
from bluesky.protocols import Collectable, Flyable
from ophyd_async.core import AsyncStatus

from lightfall_pystxmcontrol import config


def pin_getline():
    d = config.make_sim_counter(config.DEFAULT_COUNTER)  # build + meta.update + start
    nx = 5
    d.config(dwell=1.0, count=nx, samples=1)             # line config (concrete signature)
    data = asyncio.run(d.getLine())
    print("getLine type:", type(data), "len:", len(data), "sample:", repr(data)[:60])
    assert len(data) == nx, (len(data), nx)
    return type(data).__name__, len(data)


class _TrivialLineFlyer(Flyable, Collectable):
    """Minimal inline flyer with an ARRAY data key, to de-risk the collect path."""
    name = "Counter1"

    def __init__(self, nx):
        self._nx = nx
        self._counts = None

    @AsyncStatus.wrap
    async def kickoff(self):
        await asyncio.sleep(0)

    @AsyncStatus.wrap
    async def complete(self):
        self._counts = np.arange(self._nx, dtype=float) + 1.0

    def describe_collect(self):
        return {"primary": {
            "SampleX": {"source": "sim", "dtype": "array", "shape": [self._nx]},
            "SampleY": {"source": "sim", "dtype": "number", "shape": []},
            "Counter1": {"source": "sim", "dtype": "array", "shape": [self._nx]},
        }}

    def collect(self):
        ts = _time.time()
        yield {"time": ts,
               "data": {"SampleX": np.linspace(-1, 1, self._nx),
                        "SampleY": 0.0, "Counter1": self._counts},
               "timestamps": {"SampleX": ts, "SampleY": ts, "Counter1": ts}}


def pin_flyable():
    nx = 5
    flyer = _TrivialLineFlyer(nx)

    def fly_one_line(fl):
        yield from bps.open_run()
        yield from bps.kickoff(fl, wait=True)
        yield from bps.complete(fl, wait=True)
        yield from bps.collect(fl)
        yield from bps.close_run()

    docs = []
    RunEngine()(fly_one_line(flyer), lambda n, d: docs.append((n, d)))
    names = [n for n, _ in docs]
    ev = next(d for n, d in docs if n == "event")
    print("flyable doc names:", names)
    print("event Counter1 len:", len(ev["data"]["Counter1"]),
          "SampleX len:", len(ev["data"]["SampleX"]))
    assert names[0] == "start" and names[-1] == "stop"
    assert names.count("event") == 1
    assert len(ev["data"]["Counter1"]) == nx


if __name__ == "__main__":
    t, n = pin_getline()
    print(f"--- getLine pinned: {t} len {n} ---")
    pin_flyable()
    print("--- inline Flyable collect path OK ---")
```

- [ ] **Step 2: Run the spike**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/smoke_getline.py`
Expected: `getLine type: <class 'numpy.ndarray'> len: 5 ...`, `--- getLine pinned: ndarray len 5 ---`, `flyable doc names: ['start', 'descriptor', 'event', 'stop']` (order may interleave a `descriptor`), `event Counter1 len: 5 SampleX len: 5`, `--- inline Flyable collect path OK ---`.
If the array-valued `describe_collect` is rejected (e.g. `dtype`/`shape` validation), record the working descriptor form (e.g. an added `dtype_numpy`, or a different dtype spelling) — Task 2 depends on it. If `bps.collect`/`kickoff`/`complete` need a different call form, record it.

- [ ] **Step 3: Record findings in `NOTES-environment.md`**

Append a "## Phase 2a — fly-scan spike" section recording: the exact line-`config` call (`config(dwell=…, count=nx, samples=1)`) and that `len(getLine()) == nx`; the working `describe_collect` descriptor shape for array keys; the working `kickoff`/`complete`/`collect` forms; and the bare-`RunEngine` document-stream names observed.

- [ ] **Step 4: Commit**

```bash
cd ~/PycharmProjects/ncs/lightfall-pystxmcontrol
git add scripts/smoke_getline.py NOTES-environment.md
git commit -m "spike: pin getLine line acquisition + inline-Flyable collect path

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

### Task 2: `PystxmLineFlyer` (bluesky `Flyable` + `Collectable`)

**Files:**
- Create: `src/lightfall_pystxmcontrol/flyer.py`
- Test: `tests/test_flyer.py`

**Interfaces:**
- Consumes: `config.make_sim_counter`, `config.DEFAULT_COUNTER`, `config.DEFAULT_AXES`; `devices.PystxmAxis`.
- Produces: `class PystxmLineFlyer(Flyable, Collectable)` with `__init__(self, daq_config: dict, x_axis_config: dict, name: str = "Counter1")`, async `connect(self, mock=False)`, `prepare(self, *, y, x_start, x_stop, nx, dwell)`, `kickoff() -> AsyncStatus`, `complete() -> AsyncStatus`, `describe_collect() -> dict`, `collect() -> Iterator[dict]`, and a `name` property. One `collect()` yields exactly one event for the prepared row.

- [ ] **Step 1: Write the failing test**

```python
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
    assert desc["SampleY"]["dtype"] == "number"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_flyer.py -v`
Expected: FAIL (`ImportError: cannot import name 'PystxmLineFlyer'`).

- [ ] **Step 3: Implement `PystxmLineFlyer`**

```python
# src/lightfall_pystxmcontrol/flyer.py
import asyncio
import time as _time
from collections.abc import Iterator

import numpy as np
from bluesky.protocols import Collectable, Flyable
from ophyd_async.core import AsyncStatus

from . import config
from .devices import PystxmAxis


class PystxmLineFlyer(Flyable, Collectable):
    """bluesky Flyable wrapping a pystxmcontrol daq (sim) for one raster line.

    Per row: kickoff() moves the fast axis (X) to the row start and configures the
    daq for `nx` counts; complete() awaits getLine() (the row's Poisson counts);
    collect() emits one event with the count array, derived X positions, and Y.
    """

    def __init__(self, daq_config: dict, x_axis_config: dict, name: str = "Counter1"):
        self._daq_config = daq_config
        self._x_axis_config = x_axis_config
        self._name = name
        self._daq = None          # built in connect()
        self._x = None            # PystxmAxis, built in connect()
        self._row = None          # set by prepare()
        self._counts = None       # set by complete()

    @property
    def name(self) -> str:
        return self._name

    async def connect(self, mock: bool = False) -> None:
        if self._daq is None:
            self._daq = config.make_sim_counter(self._daq_config)
            self._x = PystxmAxis(self._x_axis_config, name="fast_x")
            await self._x.connect(mock=mock)

    def prepare(self, *, y: float, x_start: float, x_stop: float,
                nx: int, dwell: float) -> None:
        self._row = {"y": y, "x_start": x_start, "x_stop": x_stop,
                     "nx": nx, "dwell": dwell}
        self._counts = None

    @AsyncStatus.wrap
    async def kickoff(self) -> None:
        r = self._row
        await self._x.set(r["x_start"])                         # moveTo off-thread (PystxmAxis.set)
        self._daq.config(dwell=r["dwell"], count=r["nx"], samples=1)

    @AsyncStatus.wrap
    async def complete(self) -> None:
        data = await self._daq.getLine()                        # coroutine — await directly
        counts = np.asarray(data, dtype=float).ravel()
        if counts.size != self._row["nx"]:
            raise ValueError(f"getLine returned {counts.size} values, expected {self._row['nx']}")
        self._counts = counts

    def describe_collect(self) -> dict:
        nx = self._row["nx"]
        return {"primary": {
            "SampleX": {"source": "sim:linspace", "dtype": "array", "shape": [nx]},
            "SampleY": {"source": "sim:y", "dtype": "number", "shape": []},
            self._name: {"source": "sim:getLine", "dtype": "array", "shape": [nx]},
        }}

    def collect(self) -> Iterator[dict]:
        r = self._row
        x = np.linspace(r["x_start"], r["x_stop"], r["nx"])
        ts = _time.time()
        yield {
            "time": ts,
            "data": {"SampleX": x, "SampleY": r["y"], self._name: self._counts},
            "timestamps": {"SampleX": ts, "SampleY": ts, self._name: ts},
        }
```

If Task 1 recorded a different array-descriptor form or `config`/`getLine` call, match it here — the contract (one event per line; `SampleX[nx]`/`SampleY`/`Counter1[nx]`; `mock=False` sim path) is fixed.

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_flyer.py -v`
Expected: PASS (both tests). Then run the full suite once: `... -m pytest tests/ -q` → all prior Phase-1 tests + these pass.

- [ ] **Step 5: Commit**

```bash
git add src/lightfall_pystxmcontrol/flyer.py tests/test_flyer.py
git commit -m "feat: PystxmLineFlyer Flyable over pystxmcontrol getLine (sim line acquisition)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

### Task 3: `stxm_fly_raster` plan + bare-`RunEngine` proof

**Files:**
- Create: `src/lightfall_pystxmcontrol/plans.py`
- Test: `tests/test_fly_raster.py`

**Interfaces:**
- Consumes: `PystxmLineFlyer`, `devices.PystxmAxis`, `config`.
- Produces: `stxm_fly_raster(flyer, y_axis, *, y_start, y_stop, ny, x_start, x_stop, nx, dwell, md=None)` — a bluesky plan emitting `start → descriptor → ny events → stop`, one event per line.

- [ ] **Step 1: Write the failing integration test**

```python
# tests/test_fly_raster.py
import asyncio

import numpy as np
import pytest
from bluesky import RunEngine

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmAxis
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
from lightfall_pystxmcontrol.plans import stxm_fly_raster


def test_fly_raster_emits_one_event_per_line():
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"],
                            name="Counter1")
    y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")
    asyncio.run(_connect(flyer, y))

    nx, ny = 8, 4
    docs = []
    RE = RunEngine()
    RE(stxm_fly_raster(flyer, y, y_start=-2, y_stop=2, ny=ny,
                       x_start=-4, x_stop=4, nx=nx, dwell=1.0),
       lambda n, d: docs.append((n, d)))

    names = [n for n, _ in docs]
    assert names[0] == "start"
    assert names[-1] == "stop"
    assert names.count("event") == ny
    ev = next(d for n, d in docs if n == "event")
    assert len(ev["data"]["Counter1"]) == nx
    assert len(ev["data"]["SampleX"]) == nx
    assert (np.asarray(ev["data"]["Counter1"]) > 0).all()


async def _connect(flyer, y):
    await flyer.connect(mock=False)
    await y.connect(mock=False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_fly_raster.py -v`
Expected: FAIL (`ImportError: cannot import name 'stxm_fly_raster'`).

- [ ] **Step 3: Implement the plan**

```python
# src/lightfall_pystxmcontrol/plans.py
import numpy as np
import bluesky.plan_stubs as bps


def stxm_fly_raster(flyer, y_axis, *, y_start, y_stop, ny,
                    x_start, x_stop, nx, dwell, md=None):
    """Step the slow axis (Y), fly the fast axis (X) per row.

    Emits one event per line (the flyer's collect): SampleX[nx], SampleY, Counter1[nx].
    """
    _md = {"plan_name": "stxm_fly_raster", "shape": [ny, nx],
           "motors": [y_axis.name], "detectors": [flyer.name]}
    if md:
        _md.update(md)

    @bps.run_decorator(md=_md)
    def _inner():
        for y in np.linspace(y_start, y_stop, ny):
            yield from bps.mv(y_axis, y)
            flyer.prepare(y=float(y), x_start=x_start, x_stop=x_stop,
                          nx=nx, dwell=dwell)
            yield from bps.kickoff(flyer, wait=True)
            yield from bps.complete(flyer, wait=True)
            yield from bps.collect(flyer)

    return (yield from _inner())
```

If Task 1 recorded that `bps.collect` needs `name=` or a `declare_stream` precursor, add it here per the recorded form; the contract (`ny` events, one per line) is fixed.

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_fly_raster.py -v`
Expected: PASS. Then full suite: `... -m pytest tests/ -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/lightfall_pystxmcontrol/plans.py tests/test_fly_raster.py
git commit -m "feat: stxm_fly_raster plan (step Y, fly X) + bare-RunEngine proof

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

### Task 4: Run the fly raster via Lightfall's `BlueskyEngine` (Phase 2a done)

**Files:**
- Create: `scripts/smoke_flyscan_lightfall.py`

**Interfaces:**
- Consumes: `PystxmLineFlyer`, `devices.PystxmAxis`, `plans.stxm_fly_raster`; Lightfall's `get_engine`.
- Produces: proof that the sim fly raster runs through Lightfall's real `BlueskyEngine`. **Done = a STXM-style fly raster runs in Lightfall in simulation.**

- [ ] **Step 1: Write the smoke script (real `BlueskyEngine`, headless)**

Uses the Phase-1-proven headless pattern: offscreen Qt + `get_engine("bluesky")` + wait for `engine.RE` + connect devices + `re.subscribe(...)` + `engine(plan)` (enqueue — the RE runs on a worker thread) + wait for idle.

```python
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
rows = [d["data"]["Counter1"] for n, d in docs if n == "event"]
assert names[:1] == ["start"] and names[-1:] == ["stop"], names[:3]
assert len(rows) == ny, f"expected {ny} lines, got {len(rows)}"
allcounts = np.concatenate([np.asarray(r) for r in rows])
print(f"fly raster ran via Lightfall BlueskyEngine: {ny} lines x {nx} pts; "
      f"min={allcounts.min():.0f} max={allcounts.max():.0f}")
```

- [ ] **Step 2: Run the smoke script**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/smoke_flyscan_lightfall.py`
Expected: a line like `fly raster ran via Lightfall BlueskyEngine: 6 lines x 10 pts; min=… max=…`. If `engine(plan)` cannot drive the flyer (loop/thread issue), record the exact error; the Phase-1 finding is that ophyd-async async devices drive `BlueskyEngine` without a loop fix.

- [ ] **Step 3: Run the full suite once more**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ -q`
Expected: all Phase-1 + Phase-2a tests pass.

- [ ] **Step 4: Commit (Phase 2a done)**

```bash
git add scripts/smoke_flyscan_lightfall.py
git commit -m "feat: sim STXM fly raster runs via Lightfall BlueskyEngine (Phase 2a done)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

## Self-Review

**Spec coverage:**
- Custom bluesky `Flyable` over `getLine`, one event per line → Tasks 2, 3. ✓
- `kickoff`/`complete` via `AsyncStatus`; `getLine` awaited; `moveTo` off-thread (via `PystxmAxis.set`) → Task 2. ✓
- Derived `linspace` X positions; scalar Y; `Counter1[nx]` array → Tasks 2, 3 (asserted). ✓
- Step-Y / fly-X hybrid plan → Task 3. ✓
- Prove on bare `RunEngine` (Task 3) and Lightfall `BlueskyEngine` (Task 4). ✓
- Spike pins `getLine` line config + the array-`Flyable` collect path → Task 1. ✓
- `make_sim_line_daq` reconciled: reuse `make_sim_counter` (no mode distinction; line = `count=nx` + `getLine`) — recorded in Global Constraints. ✓
- Additive (no Phase-1/Lightfall-core edits); sim source `mock=False`; 3.14 venv tests → Global Constraints. ✓
- Out-of-scope (live Tiled, trajectory, encoder positions, derived motors, externalized config, catalog exposure, real hardware) → not planned. ✓

**Placeholder scan:** No TBD/TODO. Every code step shows complete code; commands have expected output. The "match Task 1's recorded form" notes are spike-pinning instructions (the array-descriptor schema and `collect` stub form are the genuine version-sensitive unknowns), not placeholders — the contracts are concrete.

**Type consistency:** `PystxmLineFlyer(daq_config, x_axis_config, name="Counter1")`, `prepare(y, x_start, x_stop, nx, dwell)`, `kickoff`/`complete` (`AsyncStatus`), `describe_collect()["primary"]`, `collect()` one event with keys `SampleX`/`SampleY`/`Counter1`, and `stxm_fly_raster(flyer, y_axis, *, y_start, y_stop, ny, x_start, x_stop, nx, dwell, md=None)` are used consistently across Tasks 1–4. Event keys (`SampleX`/`SampleY`/`Counter1`) and array length `nx` are asserted consistently in Tasks 1, 2, 3, 4.
