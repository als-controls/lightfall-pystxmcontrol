# pystxmcontrol → Lightfall: Fly-Scan Launchable from the UI (Phase 2b)

**Date:** 2026-06-25
**Status:** Design — pending implementation plan
**Author:** Ron Pandolfi (with Ayaka)

## Context

Phase 2a (`2026-06-23-pystxmcontrol-flyscan-design.md`, complete and public on `main`) added a
simulated STXM *fly* scan: a custom bluesky `PystxmLineFlyer` (`Flyable` + `Collectable`) over
`daq.getLine()` emitting one `event_page` per raster line, driven by a `stxm_fly_raster` plan
(step slow Y / fly fast X), proven on a bare `RunEngine` **and** through Lightfall's
`BlueskyEngine`. But the raster only runs from a smoke script — it is not reachable from the
Lightfall UI.

This spec covers **Phase 2b: making the fly raster launchable from Lightfall's UI** — a beamline
user picks the plan in Lightfall's plan panel, binds the flyer + slow axis + scalar parameters,
clicks Run, and the simulated raster executes through the real `BlueskyEngine`. This is the bridge
from "proven in a script" to "usable in the app."

Scope is one increment. Live image/Tiled streaming, a custom in-flight progress panel, faithful X
velocity/trajectory, per-point encoder readback, and real hardware remain **separate future specs**.

### Verified Lightfall plan-surfacing facts (to re-confirm in the spike)

Established by codebase exploration; the implementation spike re-confirms these against the
installed Lightfall before building (they are the version/Lightfall-sensitive unknowns, mirroring
Phase 1/2a's `getPoint`/`getLine` spikes):

- **`PlanPlugin`** (`lightfall/plugins/plan_plugin.py`) is the plan-contribution plugin type, exactly
  parallel to Phase-1's `DeviceBackendPlugin`: `type_name = "plan"`, `is_singleton = True`. Implement
  `name`, `category`, and `get_plan_function() -> Callable[..., Generator]`. Its `get_plan_info()`
  calls `PlanInfo.from_function(name, func, category)`, which introspects the returned function's
  signature for the UI. Registered via a `PluginEntry("plan", "<name>", "<module>:<Class>")` in the
  package `PluginManifest` (same mechanism Phase 1 used for `device_backend`).
- **`PlanRegistry`** (`lightfall/acquire/plans/registry.py`) holds plans by name; the UI lists them.
- **`BlueskyPanel`** (`lightfall/ui/panels/bluesky_panel.py`) is the execution UI: it lists plans,
  builds a parameter editor from the plan's signature, resolves device-name arguments to ophyd
  instances via the `DeviceCatalog` (`_resolve_device_kwargs`), then calls
  `plan_info.func(**resolved_kwargs)` and submits `engine(plan)` (the enqueue pattern Phase 2a used).
- **UI parameter hints** come from `typing.Annotated[...]` metadata in `lightfall/ui/annotations.py`
  — frozen dataclasses (`Unit`, `Decimals`, `Range`, `DeviceFilter`, …), **import-light, no Qt**.
  `DeviceFilter(category=…)` and `DeviceFilter(device_class=…)` drive device-picker filtering.
- **The execution path is plan-agnostic** — the engine just hands the generator to the `RunEngine`,
  so a `Flyable`-based plan and its `event_page` documents flow natively; no engine/core change is
  needed to *run* it.
- **No `FLYER` device category exists** (`DeviceCategory` = `MOTOR`, `DETECTOR`, `CONTROLLER`) and
  nothing in Lightfall handles flyers today.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Done bar | **Launchable + runs**: pick the plan in the UI, bind devices/params, Run executes the raster through `BlueskyEngine`; verified by tests + the running app | Smallest increment that proves UI reachability; mirrors Phase 1/2a done-criteria |
| Flyer binding | **Register the `PystxmLineFlyer` as a catalog device**; the plan takes `flyer` + `y_axis` device-pickers | Maximum reuse — connection is already solved by the Phase-1 `asyncio.run`-at-`connect()` pattern, and the standard name→instance resolution passes the connected flyer straight to the plan |
| Flyer filtering | **`DeviceFilter(device_class=…PystxmLineFlyer)`** (NOT a new category) | Keeps the work package-only; **no Lightfall-core change** (no `FLYER` enum), and disambiguates the flyer from the point `Counter1` |
| Flyer category | **`DETECTOR`** | A flyer is a detector-like acquisition object (it produces the count data); fits the existing enum without a core change |
| Pure plan | **`plans.py::stxm_fly_raster` stays UI-free**; the UI-annotated signature lives in a thin adapter in the new `plan_plugin.py` | Preserves the Phase-2a bare-`RunEngine` contract decoupled from `lightfall.ui`; the adapter is a thin delegation, not logic duplication |
| Connection | **Eager, at `backend.connect()`** via `asyncio.run` (same as Phase-1 devices) | Phase 1 proved this drives both bare `RunEngine` and `BlueskyEngine` with no loop mismatch; the plan must NOT connect inside the engine loop |
| Lightfall core | **Unchanged** | The plan/UI/engine path is already plan-agnostic |

## Architecture

```
PystxmStxmBackend.connect()                         (Phase-1 backend — EXTENDED)
  ├─ builds + connects SampleX, SampleY, Counter1            (unchanged)
  └─ + builds + connects PystxmLineFlyer; registers a DeviceInfo:
        name        = "STXMLineFlyer"
        category    = DETECTOR
        device_class= "lightfall_pystxmcontrol.flyer:PystxmLineFlyer"
        _ophyd_device = <connected flyer>

StxmFlyRasterPlanPlugin(PlanPlugin)                 (NEW: src/.../plan_plugin.py)
  name="stxm_fly_raster", category="stxm"
  get_plan_function() → _stxm_fly_raster_ui  (UI-annotated adapter, delegates to plans.stxm_fly_raster)
     flyer : Annotated[Device, DeviceFilter(device_class="…:PystxmLineFlyer")]
     y_axis: Annotated[Device, DeviceFilter(category="motor")]
     y_start, y_stop, x_start, x_stop : Annotated[float, Unit("um")]
     ny, nx : Annotated[int, Range(1, …)]
     dwell  : Annotated[float, Unit("ms")]

manifest.py  (EXTENDED)
  + PluginEntry("plan", "stxm_fly_raster", "lightfall_pystxmcontrol.plan_plugin:StxmFlyRasterPlanPlugin")
```

At run time Lightfall does the rest, unchanged: `PlanRegistry` lists the plan → `BlueskyPanel`
builds the parameter editor from the annotated signature → user picks the flyer + slow axis by name
→ `_resolve_device_kwargs` maps names to the connected instances → `plan_info.func(**kwargs)` →
`engine(plan)`. The flyer's per-line `event_page` documents stream through Lightfall's existing
subscribers.

## Components

### `PystxmStxmBackend` (extend `backend.py`)

Add, inside the existing `connect()` (alongside SampleX/SampleY/Counter1, built and connected in
the same `asyncio.run(_connect_all())`):

- Build a `PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"], name="STXMLineFlyer")`
  and `await flyer.connect(mock=False)`.
- Register a `DeviceInfo`: `name="STXMLineFlyer"`, `category=DeviceCategory.DETECTOR`,
  `device_class="lightfall_pystxmcontrol.flyer:PystxmLineFlyer"`, `connection_type=SIMULATED`,
  `tags=["flyer", "stxm", "pystxmcontrol", "simulated"]`, with `_ophyd_device = flyer`.

The existing three device registrations and all current behavior are unchanged. (If the spike shows
the device catalog/list/status UI requires the registered object to be `Readable`, add minimal
package-local `read()`/`describe()`/`read_configuration()`/`describe_configuration()` to
`PystxmLineFlyer` returning empty or last-line-summary dicts — NOT a Lightfall-core change.)

### `StxmFlyRasterPlanPlugin` (new `src/lightfall_pystxmcontrol/plan_plugin.py`)

- Subclasses `lightfall.plugins.plan_plugin.PlanPlugin`. `name = "stxm_fly_raster"`,
  `category = "stxm"`.
- `get_plan_function()` returns `_stxm_fly_raster_ui`, a thin adapter whose signature carries the
  `Annotated[...]` UI hints and which delegates to the pure `plans.stxm_fly_raster`:
  ```python
  def _stxm_fly_raster_ui(flyer, y_axis, *, y_start, y_stop, ny, x_start, x_stop, nx, dwell, md=None):
      yield from stxm_fly_raster(flyer, y_axis, y_start=y_start, y_stop=y_stop, ny=ny,
                                 x_start=x_start, x_stop=x_stop, nx=nx, dwell=dwell, md=md)
  ```
  (The exact `DeviceFilter`/`Unit`/`Range` annotation forms are pinned against the installed
  Lightfall in the spike; the binding contract — a flyer picker, a motor picker, numeric params — is
  fixed.)

### `manifest.py` (extend)

Add a second `PluginEntry("plan", "stxm_fly_raster",
"lightfall_pystxmcontrol.plan_plugin:StxmFlyRasterPlanPlugin")` next to the existing
`device_backend` entry.

### `plans.py` (unchanged)

`stxm_fly_raster` keeps its Phase-2a plain, UI-free signature and its bare-`RunEngine` behavior.

## Data flow (UI launch)

1. Lightfall loads the package manifest → `device_backend` registers SampleX/SampleY/Counter1 +
   `STXMLineFlyer`; `plan` registers `stxm_fly_raster` in the `PlanRegistry`.
2. User opens `BlueskyPanel`, selects "stxm_fly_raster". The panel introspects the annotated
   signature and renders: a flyer picker (filtered to `PystxmLineFlyer`), a motor picker (the slow
   axis, e.g. `SampleY`), and numeric fields for `y_start/y_stop/ny/x_start/x_stop/nx/dwell`.
3. User fills values and clicks Run. `_resolve_device_kwargs` maps the picked names to the connected
   `flyer` and `y_axis` instances; the panel calls `plan_info.func(**kwargs)` and submits
   `engine(plan)`.
4. The `RunEngine` (on the engine worker thread) runs the raster: `ny` lines, one `event_page` per
   line (`Counter1[nx]` Poisson counts, derived `SampleX[nx]`, scalar `SampleY`). Documents stream
   through Lightfall's subscribers unchanged.

## Staged delivery

- **Spike — pin the Lightfall-sensitive unknowns.** A headless script that, against the installed
  Lightfall: (a) registers a non-`Readable` `PystxmLineFlyer` as a `DeviceInfo` and exercises the
  device catalog/list/status path to confirm it does not break (or records the minimal Readable
  surface needed); (b) confirms `PlanInfo.from_function` introspects an `Annotated`-hinted signature
  into the expected parameter descriptors (flyer→device_class picker, y_axis→motor picker,
  numerics→spinboxes), and that `DeviceFilter(device_class=…)` resolves the flyer; (c) drives the
  `PlanRegistry` → device-name→instance resolution → `engine(plan)` path end-to-end so the
  registered flyer runs and emits `ny` `event_page`s. Records the working annotation forms + any
  Readable requirement for the tasks that follow.
- **Backend + flyer registration.** Extend `PystxmStxmBackend.connect()`; TDD.
- **PlanPlugin + manifest.** New `plan_plugin.py` + manifest entry; TDD (introspection + adapter
  delegation).
- **End-to-end proof.** Headless smoke driving the plan through the registry/catalog/engine path
  (and through `BlueskyPanel` if feasible), asserting the raster runs (`ny` lines, positive counts).

## Testing

- **Unit (backend):** after `connect()`, the catalog lists four devices including `STXMLineFlyer`
  with `category=DETECTOR`, the recorded `device_class`, and a connected `_ophyd_device`; the three
  Phase-1 devices are unchanged.
- **Unit (plan plugin):** `get_plan_info()` introspects the annotated adapter into the expected
  parameter set (flyer + motor device params, numeric params with units/ranges); the adapter
  delegates to `stxm_fly_raster` and yields the same document stream.
- **Integration (UI binding path):** with the registry + catalog populated, name→instance resolution
  binds the registered flyer + slow axis, and `engine(plan)` runs the raster emitting `ny`
  `event_page`s with positive `Counter1[nx]` counts.
- **Smoke:** headless run through the registry/catalog/engine (and `BlueskyPanel` if feasible)
  prints the raster shape.
- All current 15 tests stay green. Run in **Lightfall's 3.14 venv** via `.venv/Scripts/python -m
  pytest`, never bare `pytest`.

## Risks

1. **Non-`Readable` flyer in the device catalog.** The device-list/status UI may attempt to
   `read()`/`describe()` registered devices. *Mitigation:* the spike exercises the catalog path
   first; if needed, add minimal package-local `Readable` methods to `PystxmLineFlyer` (no core
   change).
2. **Annotated-signature introspection drift.** The exact `DeviceFilter`/`Unit`/`Range` forms and
   how `PlanInfo.from_function` maps them vary with the installed Lightfall. *Mitigation:* pin in the
   spike; the binding contract is fixed.
3. **`device_class` filter matching.** The picker must match the stored `device_class` string to the
   plan's `DeviceFilter(device_class=…)`. *Mitigation:* pin the exact matching semantics in the spike
   and use one shared constant for the string.
4. **Connection timing.** The flyer must be connected before the plan runs, not inside the engine
   loop. *Mitigation:* connect eagerly in `backend.connect()` via `asyncio.run`, exactly as Phase 1
   does for the other devices.

## Out of scope (future increments)

Live image/Tiled streaming (`StandardDetector` + `Writer` + `StreamResource`); a custom in-flight
progress panel (`@plan_with_ui`); a `FLYER` `DeviceCategory` in Lightfall core; refactoring
`PystxmLineFlyer` to accept injected pre-built devices (the deferred "Option C"); resolving the
SampleX-vs-internal-`fast_x` redundancy; faithful X velocity/trajectory (`FlyMotorInfo`); per-point
encoder readback; real hardware (`simulation=False`).
