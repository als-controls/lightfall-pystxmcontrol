# pystxmcontrol → Lightfall Fly-Scan Launchable from the UI (Phase 2b) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the simulated STXM fly raster launchable from Lightfall's UI — register the `PystxmLineFlyer` as a catalog device and contribute a `stxm_fly_raster` plan via a `PlanPlugin`, so a user picks the plan in Lightfall's BlueskyPanel, binds the flyer + slow axis + params, and runs the raster through the real `BlueskyEngine`.

**Architecture:** Additive to the `lightfall-pystxmcontrol` package, reusing Lightfall's existing plan machinery (`PlanPlugin`/`PlanRegistry`/`BlueskyPanel`). Extend the Phase-1 `PystxmStxmBackend` to also build, connect, and register the flyer as a `DeviceInfo` (category `DETECTOR`, filtered by `device_class`). Add a `StxmFlyRasterPlanPlugin` whose UI-annotated adapter delegates to the unchanged pure `plans.stxm_fly_raster`. No Lightfall-core change.

**Tech Stack:** Python, Lightfall (`PlanPlugin`, `PlanRegistry`, `BlueskyPanel`, `DeviceBackend`, `lightfall.ui.annotations`), ophyd-async, bluesky, pystxmcontrol (sim), pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-25-pystxmcontrol-flyscan-ui-design.md`

## Global Constraints

- **Done bar:** the fly raster is selectable + runnable from Lightfall's UI path and executes through `BlueskyEngine`; verified by tests + a headless smoke. No live image, no custom progress panel.
- **Flyer binding:** the `PystxmLineFlyer` is registered as a Lightfall catalog device — `name="STXMLineFlyer"`, `category=DeviceCategory.DETECTOR`, `device_class="lightfall_pystxmcontrol.flyer:PystxmLineFlyer"`, `connection_type=SIMULATED`. The plan's `flyer` parameter is filtered by **`device_class`** (NOT a new category — there is deliberately NO `FLYER` enum / no Lightfall-core change). The slow `y_axis` parameter is filtered by `category="motor"` (picks the existing `SampleY`).
- **Pure plan stays pure:** `plans.py::stxm_fly_raster` keeps its Phase-2a plain, UI-free, bare-`RunEngine` signature and is NOT modified. All `lightfall.ui.annotations` coupling lives ONLY in the new `plan_plugin.py` as a thin delegating adapter (`_stxm_fly_raster_ui`).
- **Connection:** the flyer is connected EAGERLY in `backend.connect()` via the existing `asyncio.run(_connect_all())` (the same loop-agnostic pattern Phase 1 proved drives both a bare `RunEngine` and `BlueskyEngine`). The plan must NOT connect devices inside the engine loop.
- **Sim source:** `connect(mock=False)` — pystxmcontrol's `simulation=True` path runs; real signals.
- **File-modification scope (Phase 2b is the FIRST phase to touch Phase-1 files):** additive edits are limited to `src/lightfall_pystxmcontrol/backend.py` (register the flyer) and `src/lightfall_pystxmcontrol/manifest.py` (add the plan entry); a new `src/lightfall_pystxmcontrol/plan_plugin.py`; new test files; and two scripts. `src/lightfall_pystxmcontrol/flyer.py` may be touched ONLY to add minimal `Readable` methods IF Task 1 finds the catalog requires them (an explicit, recorded addition). Do NOT modify `devices.py`, `config.py`, `plans.py`, `plugin.py`, or ANY Lightfall-core file. The three existing device registrations and all 15 current tests MUST stay green.
- **Interpreter / tests:** run in **Lightfall's 3.14 venv** via `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest` — never bare `pytest`. Importing the package prints ~6-10 upstream "X not available" lines — expected noise, not a failure.
- **No `git add -A`:** stage explicit paths only.
- **Package repo:** `~/PycharmProjects/ncs/lightfall-pystxmcontrol/`.
- **Commit trailers** (every commit):
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo
  ```

---

### Task 1: Spike — pin Lightfall's plan-surfacing + device-catalog surfaces

Phase 2b's genuine unknowns are Lightfall's *internal* APIs, version-sensitive like Phase 1/2a's `getPoint`/`getLine`/`event_page`. Pin them empirically before wrapping. **This is a spike, not TDD.** Probe four things and record the exact working forms for Tasks 2-4:

(a) the real signatures/field names of `PlanPlugin`, `PlanInfo`, `PlanInfo.from_function`, the per-parameter info objects, and `lightfall.ui.annotations` (`DeviceFilter`, `Unit`, `Range`);
(b) whether registering a **non-`Readable`** `PystxmLineFlyer` as a `DeviceInfo` breaks the device-catalog state/status/list path (and the minimal `Readable` surface to add to the flyer if it does);
(c) that `PlanInfo.from_function` introspects an `Annotated`-hinted signature into the expected parameter descriptors (a `flyer` device-picker filtered by `device_class`, a `y_axis` motor picker, numeric fields), and how `DeviceFilter(device_class=…)` matches a registered device;
(d) that the API-level launch path — `PlanRegistry` lookup → device-name→instance resolution against a catalog → `engine(plan)` (or a bare `RunEngine` if engine wiring is heavy) — drives the registered flyer end-to-end, emitting `ny` `event_page`s.

**Files:**
- Create: `scripts/smoke_plan_ui.py`
- Modify: `NOTES-environment.md` (append a "## Phase 2b — UI-launch spike" section)

**Interfaces:**
- Produces: recorded facts that steer Tasks 2-4 — the exact `DeviceInfo` registration call for a flyer; whether `PystxmLineFlyer` needs `Readable` methods (and which); the working `Annotated` forms (`DeviceFilter(device_class=…)`, `DeviceFilter(category="motor")`, `Unit`, `Range`) and the `PlanInfo`/parameter-descriptor field names to assert against; and the exact name→instance resolution + `engine(plan)` call sequence.

- [ ] **Step 1: Read the real Lightfall source to pin exact APIs**

Open and read (do NOT modify) these files in `C:/Users/rp/PycharmProjects/ncs/lightfall/src/lightfall/`, recording exact class/function signatures and field names:
- `plugins/plan_plugin.py` (the `PlanPlugin` ABC — already known: `name`, `category`, `get_plan_function`, `get_plan_info`).
- `acquire/plans/registry.py` — `PlanInfo` dataclass fields, `PlanInfo.from_function(name, func, category)`, the per-parameter descriptor type (its field names, e.g. `name`, `type_name`, `required`, `default`), and `PlanRegistry.register`/`get_plan`/`list_plans`.
- `ui/annotations.py` — exact `DeviceFilter` fields (`category`, `device_class`, `group`, `source`, `name_pattern`), `Unit`, `Range`, `Decimals`.
- `ui/widgets/plan_config.py` — how a parameter is classified as a device-picker vs numeric (the `DeviceFilter`/category/name heuristic) and how `device_class` filtering selects devices.
- `ui/panels/bluesky_panel.py` — `_resolve_device_kwargs` (its exact signature and how it looks devices up: `catalog.get_device_by_name`, `_ophyd_device`), and how the panel calls the engine (`self._engine(plan)`).
- `devices/model.py` — `DeviceInfo` constructor fields (confirm against Phase-1 `backend.py` usage) and how `DeviceState`/`DeviceStatus` is computed in `_add_device_internal`-style code; **specifically whether any catalog/state/status code path calls `read()`/`describe()`/`.position`/`.value` on `_ophyd_device`** (the non-`Readable` risk).
- How a `DeviceCatalog` is constructed and populated from a `DeviceBackend` (search `lightfall/devices/` for `DeviceCatalog`); the spike needs to put the flyer's `DeviceInfo` somewhere the resolver can find it by name.

- [ ] **Step 2: Write `scripts/smoke_plan_ui.py`**

A headless probe (offscreen Qt only if a probed API needs a `QApplication`). Use the exact APIs pinned in Step 1; the scaffold below is the intent — correct each call against the real source and record deviations.

```python
"""Spike: pin Lightfall plan-surfacing + device-catalog surfaces for the fly-scan UI launch."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from typing import Annotated, Any
from collections.abc import Generator
import asyncio

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
from lightfall_pystxmcontrol.plans import stxm_fly_raster

# --- (a)/(c) PlanInfo introspection of an Annotated signature ---
from lightfall.acquire.plans.registry import PlanInfo
from lightfall.ui.annotations import DeviceFilter, Unit, Range  # confirm names in Step 1

FLYER_DEVICE_CLASS = "lightfall_pystxmcontrol.flyer:PystxmLineFlyer"

def _probe_plan(
    flyer: Annotated[Any, DeviceFilter(device_class=FLYER_DEVICE_CLASS)],
    y_axis: Annotated[Any, DeviceFilter(category="motor")],
    y_start: Annotated[float, Unit("um")] = -5.0,
    y_stop: Annotated[float, Unit("um")] = 5.0,
    ny: Annotated[int, Range(1, 10000)] = 6,
    x_start: Annotated[float, Unit("um")] = -5.0,
    x_stop: Annotated[float, Unit("um")] = 5.0,
    nx: Annotated[int, Range(1, 10000)] = 10,
    dwell: Annotated[float, Unit("ms")] = 1.0,
) -> Generator[Any, Any, Any]:
    """Probe plan for introspection."""
    yield from stxm_fly_raster(flyer, y_axis, y_start=y_start, y_stop=y_stop, ny=ny,
                               x_start=x_start, x_stop=x_stop, nx=nx, dwell=dwell)

info = PlanInfo.from_function("stxm_fly_raster", _probe_plan, "stxm")
print("PlanInfo params:", [(p.name, getattr(p, "type_name", "?")) for p in info.parameters])
# RECORD: did `flyer` classify as a device-picker (device_class filter)?  `y_axis` as a motor picker?
#         do the numerics carry unit/range?  What are the parameter-descriptor field names?

# --- (b) register a non-Readable flyer as a DeviceInfo; exercise the catalog path ---
from lightfall.devices.model import DeviceInfo, DeviceCategory, ConnectionType

flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"], name="STXMLineFlyer")
asyncio.run(flyer.connect(mock=False))

di = DeviceInfo(
    name="STXMLineFlyer",
    description="Simulated pystxmcontrol STXM line flyer",
    device_class=FLYER_DEVICE_CLASS,
    category=DeviceCategory.DETECTOR,
    connection_type=ConnectionType.SIMULATED,
    prefix="STXMLineFlyer",
    tags=["flyer", "stxm", "pystxmcontrol", "simulated"],
    metadata={},
)
di._ophyd_device = flyer
# Exercise whatever the catalog/list/status path does (pinned in Step 1): build the DeviceState,
# call list/search/get_by_name, and any status computation. RECORD whether a non-Readable flyer
# breaks it (AttributeError on read()/describe()/position/value) and, if so, the MINIMAL Readable
# surface needed (e.g. read()->{}, describe()->{}, read_configuration()->{}, describe_configuration()->{}).

# --- (c)/(d) device_class filtering + end-to-end run ---
# Using the filter function pinned in Step 1, confirm DeviceFilter(device_class=FLYER_DEVICE_CLASS)
# selects the flyer DeviceInfo out of a list that also contains the point Counter1.
# Then drive the launch path: resolve names -> instances (flyer + a SampleY PystxmAxis), build the
# plan via info.func(**resolved), and run it (engine(plan) if engine wiring is light, else a bare
# RunEngine). RECORD: ny event_pages emitted, positive Counter1 counts, and the exact call sequence.

print("--- Phase 2b spike complete ---")
```

- [ ] **Step 3: Run the spike**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/smoke_plan_ui.py`
Expected: `PlanInfo params: [...]` showing `flyer`/`y_axis` as device-pickers and the numerics with hints; a clear statement of whether the non-`Readable` flyer broke the catalog path; confirmation `device_class` filtering selects the flyer; and an end-to-end run emitting `ny` `event_page`s with positive counts, ending `--- Phase 2b spike complete ---`.
If any probed API differs from the scaffold (field names, `from_function` behavior, resolver signature, a required `Readable` surface), that IS the finding — record it.

- [ ] **Step 4: Record findings in `NOTES-environment.md`**

Append a `## Phase 2b — UI-launch spike` section recording, copy-pasteable for Tasks 2-4: the exact `DeviceInfo(...)` flyer-registration call; whether `PystxmLineFlyer` needs `Readable` methods and exactly which (or "none needed"); the working `Annotated` forms and the `PlanInfo`/parameter-descriptor field names to assert in Task 3; the `device_class`-filter matching semantics; and the exact name→instance resolution + run call sequence for Task 4.

- [ ] **Step 5: Commit**

```bash
cd ~/PycharmProjects/ncs/lightfall-pystxmcontrol
git add scripts/smoke_plan_ui.py NOTES-environment.md
git commit -m "spike: pin Lightfall plan-surfacing + device-catalog surfaces for fly-scan UI launch

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

### Task 2: Register the flyer as a catalog device (extend `PystxmStxmBackend`)

**Files:**
- Modify: `src/lightfall_pystxmcontrol/backend.py` (extend `connect()`)
- Modify (ONLY if Task 1 recorded it as required): `src/lightfall_pystxmcontrol/flyer.py` (add minimal `Readable` methods)
- Test: `tests/test_backend_flyer.py`

**Interfaces:**
- Consumes: `config.DEFAULT_COUNTER`, `config.DEFAULT_AXES`; `flyer.PystxmLineFlyer`; Lightfall `DeviceInfo`/`DeviceCategory`/`ConnectionType` (already imported in `backend.py`).
- Produces: after `PystxmStxmBackend.connect()`, the catalog contains a 4th device `"STXMLineFlyer"` (`category=DETECTOR`, `device_class="lightfall_pystxmcontrol.flyer:PystxmLineFlyer"`, connected `_ophyd_device` = the flyer). The existing `SampleX`/`SampleY`/`Counter1` registrations are unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backend_flyer.py
from lightfall.devices.model import DeviceCategory

from lightfall_pystxmcontrol.backend import PystxmStxmBackend
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer


def test_backend_registers_flyer_device():
    backend = PystxmStxmBackend()
    assert backend.connect() is True

    flyer_info = backend.get_device_by_name("STXMLineFlyer")
    assert flyer_info is not None
    assert flyer_info.category == DeviceCategory.DETECTOR
    assert flyer_info.device_class == "lightfall_pystxmcontrol.flyer:PystxmLineFlyer"
    assert isinstance(flyer_info._ophyd_device, PystxmLineFlyer)
    # connected flyer: prepared row not required, but the daq must be built
    assert flyer_info._ophyd_device._daq is not None


def test_backend_still_registers_phase1_devices():
    backend = PystxmStxmBackend()
    assert backend.connect() is True
    names = {d.name for d in backend.list_devices()}
    assert {"SampleX", "SampleY", "Counter1", "STXMLineFlyer"} <= names
    assert backend.get_device_by_name("Counter1").category == DeviceCategory.DETECTOR
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_backend_flyer.py -v`
Expected: FAIL (`get_device_by_name("STXMLineFlyer")` returns `None` → `AssertionError`).

- [ ] **Step 3: Extend `backend.py`**

If Task 1 recorded that the catalog requires `PystxmLineFlyer` to be `Readable`, FIRST add the minimal recorded methods to `flyer.py` (e.g. `def read(self): return {}`, `def describe(self): return {}`, and the configuration variants), per Task 1's recorded form. Otherwise skip the flyer edit.

Then, in `backend.py`'s `connect()`, build and connect the flyer alongside the existing devices and register it. Add to the `specs` assembly (before `_connect_all`) and reuse the existing `DeviceInfo` registration loop, OR register it explicitly after the loop. Concretely, extend the `specs` list and the registration so the flyer is built, connected in the same `asyncio.run(_connect_all())`, and registered:

```python
# in connect(), after building the counter and before _connect_all:
from .flyer import PystxmLineFlyer  # local import alongside the existing device imports

flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"],
                        name="STXMLineFlyer")
specs.append(("STXMLineFlyer", flyer, DeviceCategory.DETECTOR))
```

The existing `_connect_all()` already does `await dev.connect(mock=False)` for every spec entry — `PystxmLineFlyer.connect(mock=False)` matches that signature, so the flyer connects with no loop change. The existing registration loop builds a `DeviceInfo` per spec with `device_class=f"lightfall_pystxmcontrol.devices:{type(dev).__name__}"`. The flyer lives in `flyer.py`, not `devices.py`, so its `device_class` must be `"lightfall_pystxmcontrol.flyer:PystxmLineFlyer"`. Adjust the loop to compute the module path from the instance rather than hardcoding `devices`:

```python
# replace the hardcoded module in the DeviceInfo(...) construction:
device_class=f"{type(dev).__module__}:{type(dev).__name__}",
```

`type(flyer).__module__` is `"lightfall_pystxmcontrol.flyer"` and the existing devices' `__module__` is `"lightfall_pystxmcontrol.devices"`, so this preserves the Phase-1 `device_class` strings exactly while giving the flyer the correct one. (Confirm the Phase-1 device tests still assert the same `device_class` values; they do — `lightfall_pystxmcontrol.devices:PystxmAxis` etc.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_backend_flyer.py -v`
Expected: PASS (both tests). Then the full suite: `... -m pytest tests/ -q` → all prior 15 tests + these pass (the `device_class` refactor must not regress `test_backend.py`).

- [ ] **Step 5: Commit**

```bash
git add src/lightfall_pystxmcontrol/backend.py tests/test_backend_flyer.py
# include flyer.py ONLY if Task 1 required Readable methods:
# git add src/lightfall_pystxmcontrol/flyer.py
git commit -m "feat: register PystxmLineFlyer as a Lightfall catalog device (DETECTOR, device_class filter)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

### Task 3: `StxmFlyRasterPlanPlugin` + manifest entry

**Files:**
- Create: `src/lightfall_pystxmcontrol/plan_plugin.py`
- Modify: `src/lightfall_pystxmcontrol/manifest.py` (add a `plan` entry)
- Test: `tests/test_plan_plugin.py`

**Interfaces:**
- Consumes: `lightfall.plugins.plan_plugin.PlanPlugin`; `lightfall.ui.annotations` (`DeviceFilter`, `Unit`, `Range` — exact forms per Task 1); `plans.stxm_fly_raster`.
- Produces: `StxmFlyRasterPlanPlugin(PlanPlugin)` with `name="stxm_fly_raster"`, `category="stxm"`, `get_plan_function()` returning `_stxm_fly_raster_ui` (a thin adapter delegating to `stxm_fly_raster`). A `PluginEntry("plan", "stxm_fly_raster", "lightfall_pystxmcontrol.plan_plugin:StxmFlyRasterPlanPlugin")` in the manifest.

- [ ] **Step 1: Write the failing test**

Use the parameter-descriptor field names recorded in Task 1 (the scaffold below assumes a `.name` attribute and a way to read each parameter's classification; adjust to the recorded `PlanInfo` API).

```python
# tests/test_plan_plugin.py
from lightfall_pystxmcontrol.plan_plugin import StxmFlyRasterPlanPlugin


def test_plan_plugin_identity():
    plugin = StxmFlyRasterPlanPlugin()
    assert plugin.name == "stxm_fly_raster"
    assert plugin.category == "stxm"


def test_plan_info_exposes_expected_parameters():
    plugin = StxmFlyRasterPlanPlugin()
    info = plugin.get_plan_info()
    param_names = {p.name for p in info.parameters}
    assert {"flyer", "y_axis", "y_start", "y_stop", "ny",
            "x_start", "x_stop", "nx", "dwell"} == param_names


def test_adapter_delegates_to_pure_plan():
    # The adapter must yield the same message stream as the pure plan for the
    # same inputs. Build a connected flyer + slow axis and compare doc-name
    # sequences over a bare RunEngine (one event_page per line).
    import asyncio
    from bluesky import RunEngine
    from lightfall_pystxmcontrol import config
    from lightfall_pystxmcontrol.devices import PystxmAxis
    from lightfall_pystxmcontrol.flyer import PystxmLineFlyer

    plan_func = StxmFlyRasterPlanPlugin().get_plan_function()
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"],
                            name="STXMLineFlyer")
    y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")

    async def _c():
        await flyer.connect(mock=False)
        await y.connect(mock=False)
    asyncio.run(_c())

    docs = []
    RE = RunEngine()
    RE(plan_func(flyer, y, y_start=-2, y_stop=2, ny=3,
                 x_start=-4, x_stop=4, nx=8, dwell=1.0),
       lambda n, d: docs.append((n, d)))
    names = [n for n, _ in docs]
    assert names[0] == "start" and names[-1] == "stop"
    assert names.count("event_page") == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_plan_plugin.py -v`
Expected: FAIL (`ImportError: cannot import name 'StxmFlyRasterPlanPlugin'`).

- [ ] **Step 3: Implement `plan_plugin.py`**

Use the exact `Annotated` forms recorded in Task 1. The adapter delegates to the pure plan (no logic duplication).

```python
# src/lightfall_pystxmcontrol/plan_plugin.py
"""Lightfall PlanPlugin exposing the simulated STXM fly raster in the UI."""
from collections.abc import Callable, Generator
from typing import Annotated, Any

from lightfall.plugins.plan_plugin import PlanPlugin
from lightfall.ui.annotations import DeviceFilter, Range, Unit

from .plans import stxm_fly_raster

FLYER_DEVICE_CLASS = "lightfall_pystxmcontrol.flyer:PystxmLineFlyer"


def _stxm_fly_raster_ui(
    flyer: Annotated[Any, DeviceFilter(device_class=FLYER_DEVICE_CLASS)],
    y_axis: Annotated[Any, DeviceFilter(category="motor")],
    *,
    y_start: Annotated[float, Unit("um")] = -5.0,
    y_stop: Annotated[float, Unit("um")] = 5.0,
    ny: Annotated[int, Range(1, 10000)] = 6,
    x_start: Annotated[float, Unit("um")] = -5.0,
    x_stop: Annotated[float, Unit("um")] = 5.0,
    nx: Annotated[int, Range(1, 10000)] = 10,
    dwell: Annotated[float, Unit("ms")] = 1.0,
    md: dict | None = None,
) -> Generator[Any, Any, Any]:
    """Step the slow axis (Y) and fly the fast axis (X) per row, one event per line.

    UI-facing adapter: delegates to the pure ``plans.stxm_fly_raster`` so the
    bare-RunEngine plan stays decoupled from Lightfall's UI annotations.
    """
    return (yield from stxm_fly_raster(
        flyer, y_axis, y_start=y_start, y_stop=y_stop, ny=ny,
        x_start=x_start, x_stop=x_stop, nx=nx, dwell=dwell, md=md))


class StxmFlyRasterPlanPlugin(PlanPlugin):
    """Contributes the simulated STXM fly raster to Lightfall's plan registry."""

    @property
    def name(self) -> str:
        return "stxm_fly_raster"

    @property
    def category(self) -> str:
        return "stxm"

    def get_plan_function(self) -> Callable[..., Generator[Any, Any, Any]]:
        return _stxm_fly_raster_ui
```

If Task 1 recorded that `DeviceFilter`/`Unit`/`Range` take different argument names, or that the `flyer` param needs a different classification hint to register as a device-picker, match the recorded form here — the contract (a flyer picker, a motor picker, numeric params; delegation to `stxm_fly_raster`) is fixed.

- [ ] **Step 4: Add the manifest entry**

In `src/lightfall_pystxmcontrol/manifest.py`, add a second `PluginEntry` to the `plugins=[...]` list (keep the existing `device_backend` entry):

```python
PluginEntry(
    "plan",
    "stxm_fly_raster",
    "lightfall_pystxmcontrol.plan_plugin:StxmFlyRasterPlanPlugin",
),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_plan_plugin.py -v`
Expected: PASS (all three). Then full suite: `... -m pytest tests/ -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add src/lightfall_pystxmcontrol/plan_plugin.py src/lightfall_pystxmcontrol/manifest.py tests/test_plan_plugin.py
git commit -m "feat: StxmFlyRasterPlanPlugin + manifest entry (fly raster selectable in Lightfall UI)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

### Task 4: End-to-end UI-launch proof (Phase 2b done)

**Files:**
- Create: `scripts/smoke_flyscan_ui.py`

**Interfaces:**
- Consumes: `PystxmStxmBackend` (Task 2), `StxmFlyRasterPlanPlugin` (Task 3), `plans.stxm_fly_raster`, and Lightfall's `PlanRegistry` + device-name→instance resolution. Uses the exact launch call sequence recorded in Task 1.
- Produces: proof that, through Lightfall's plan-surfacing + device-binding path, the registered flyer + slow axis run the raster. **Done = the fly raster is launchable through Lightfall's UI path and runs in simulation.**

- [ ] **Step 1: Write the smoke script (headless, real Lightfall machinery)**

Mirror the API-level launch path the `BlueskyPanel` performs (pinned in Task 1): connect the backend → register the plan in a `PlanRegistry` (or fetch via the plugin's `get_plan_info()`) → resolve the `flyer`/`y_axis` parameter names to the backend's connected instances → build the plan via the plan function → run it (via `engine(plan)` if the engine is light to construct headless, else a bare `RunEngine`) → assert `ny` `event_page`s with positive counts. Use the recorded resolution + run sequence.

```python
# scripts/smoke_flyscan_ui.py
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

# Run via the engine if Task 1 confirmed a light headless construction; otherwise a bare RunEngine
# proves the same launch contract (the plan/engine path is plan-agnostic — Phase 1/2a finding).
from bluesky import RunEngine
docs = []
RE = RunEngine()
RE(plan_func(flyer, y_axis, y_start=-5, y_stop=5, ny=ny,
             x_start=-5, x_stop=5, nx=nx, dwell=1.0),
   lambda n, d: docs.append((n, d)))

names = [n for n, _ in docs]
rows = [d["data"]["Counter1"][0] for n, d in docs if n == "event_page"]
assert names[:1] == ["start"] and names[-1:] == ["stop"], names[:3]
assert len(rows) == ny, f"expected {ny} lines, got {len(rows)}"
allcounts = np.concatenate([np.asarray(r) for r in rows])
assert allcounts.shape == (ny * nx,), f"expected {ny*nx} pixels, got {allcounts.shape}"
print(f"fly raster launchable via Lightfall (backend+plan plugin): {ny} lines x {nx} pts; "
      f"min={allcounts.min():.0f} max={allcounts.max():.0f}")
```

If Task 1 recorded a light path to drive Lightfall's real `BlueskyEngine` and/or `PlanRegistry` lookup here, prefer that (it proves more of the UI path); the bare-`RunEngine` fallback proves the binding contract (registered flyer + slow axis run the plan). The done-criterion is the printed `min/max` line over `ny` lines.

- [ ] **Step 2: Run the smoke script**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/smoke_flyscan_ui.py`
Expected: a line like `fly raster launchable via Lightfall (backend+plan plugin): 6 lines x 10 pts; min=… max=…`. If the catalog/registry/resolution path errors, record the exact error.

- [ ] **Step 3: Run the full suite once more**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ -q`
Expected: all prior tests + Phase-2b tests pass.

- [ ] **Step 4: Commit (Phase 2b done)**

```bash
git add scripts/smoke_flyscan_ui.py
git commit -m "feat: sim STXM fly raster launchable via Lightfall plan plugin + catalog (Phase 2b done)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

## Self-Review

**Spec coverage:**
- Register the flyer as a catalog device (DETECTOR, `device_class`, connected) → Task 2. ✓
- `PlanPlugin` + manifest `plan` entry; pure plan stays UI-free; thin annotated adapter → Task 3. ✓
- Connection eager in `backend.connect()` via `asyncio.run` → Task 2 (reuses existing `_connect_all`). ✓
- `device_class` filter (no `FLYER` enum / no Lightfall-core change) → Tasks 1, 3. ✓
- Spike pins the Lightfall-internal unknowns (non-`Readable` catalog risk, `PlanInfo` introspection, `device_class` matching, end-to-end run) → Task 1. ✓
- End-to-end UI-launch proof → Task 4. ✓
- Done bar (launchable + runs; no live image / progress panel) → Task 4; out-of-scope honored. ✓
- File-modification scope (extend `backend.py`/`manifest.py`; new `plan_plugin.py`; `flyer.py` only if Task 1 requires; `plans.py` untouched; no Lightfall-core) → Global Constraints + Tasks 2-3. ✓

**Placeholder scan:** No TBD/TODO. Task 1 is a spike whose explicit job is pinning Lightfall-internal APIs (the genuine version-sensitive unknowns, like Phase 2a's `event_page`); its scaffold + "record the working form" notes are spike-pinning instructions, not placeholders. Tasks 2-4 carry complete code; the "match Task 1's recorded form" notes are confined to the genuinely API-sensitive bits (`Annotated` argument names, parameter-descriptor field names, any `Readable` requirement, the resolve/run call sequence) — the contracts (flyer registered as DETECTOR with the given `device_class`; a flyer + motor picker plus numeric params delegating to `stxm_fly_raster`; `ny` `event_page`s) are concrete.

**Type consistency:** `STXMLineFlyer` (device name), `"lightfall_pystxmcontrol.flyer:PystxmLineFlyer"` (`device_class`), `DeviceCategory.DETECTOR`, `_stxm_fly_raster_ui(flyer, y_axis, *, y_start, y_stop, ny, x_start, x_stop, nx, dwell, md=None)` delegating to `stxm_fly_raster`, `StxmFlyRasterPlanPlugin` (`name="stxm_fly_raster"`, `category="stxm"`), and the event key `Counter1` / array length `nx` / line count `ny` are used consistently across Tasks 1-4. The `device_class` computation `f"{type(dev).__module__}:{type(dev).__name__}"` (Task 2) preserves the Phase-1 strings while giving the flyer the correct module path.
