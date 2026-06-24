# pystxmcontrol → Lightfall: Simulated Fly-Scan (Phase 2a)

**Date:** 2026-06-23
**Status:** Design — pending implementation plan
**Author:** Ron Pandolfi (with Ayaka)

## Context

Phase 1 (`2026-06-23-pystxmcontrol-ophyd-integration-design.md`) wrapped David Shapiro's
`pystxmcontrol` `motor`/`daq` drivers (in `simulation=True`) as ophyd-async **point** devices
(`PystxmAxis`, `PystxmCounter`) and ran a step-scan 2D raster (`grid_scan`) through Lightfall's
`BlueskyEngine`. It is complete: the package `lightfall-pystxmcontrol` is live and public, with
`pystxmcontrol` consumed from a pinned als-controls fork.

This spec covers the **first Phase-2 increment: a simulated *fly* scan** — a line-by-line 2D
raster where the fast axis is swept and the detector collects a whole row of counts per line via
`daq.getLine()`, rather than point-by-point via `getPoint()`. This is STXM's signature fast
acquisition mode and the payoff of choosing ophyd-async (a flyer has a natural home here).

Scope is deliberately one increment. The remaining Phase-2 items (live Tiled/image streaming,
faithful X velocity/trajectory, per-point encoder positions, derived energy/piezo motors,
externalized config, real-hardware bring-up) are **separate future specs**, not this one.

### Verified `getLine` facts (installed pystxmcontrol, sim path)

- `daq` ABC declares `getLine(self, step, **kw)` and `config(self, dwell, points, mode)`; the
  concrete `keysight53230A.getLine(self)` is a **no-arg coroutine**.
- In simulation, `getLine()` returns `numpy.poisson(1e7 * dwell/1000, count * samples)` — a **1-D
  array of `count * samples` Poisson counts** — after an `asyncio.sleep(dwell/1000 * count*samples)`
  that models acquisition time. `count`/`samples`/`dwell` are set by `config(...)`.
- Therefore configuring `points = nx` (and `samples = 1`) makes `getLine()` return exactly `nx`
  values — one row of the raster. The exact `config(...)` call and the resulting array length are
  **pinned by a spike** before wrapping (see Staged Delivery, Spike), mirroring Phase 1's
  `getPoint` spike.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| First Phase-2 scope | **Simulated fly scan** (line-by-line raster), its own spec | Headline Phase-2 capability; exercises the ophyd-async/flyer payoff; sim-first like Phase 1 |
| Done bar | **Prove the fly path**: correct document stream on a bare `RunEngine` **and** through Lightfall's `BlueskyEngine` | Mirrors Phase 1's done-criterion; smallest increment that proves the abstraction |
| Flyer implementation | **Custom bluesky `Flyable`** (`kickoff`/`complete`/`describe_collect`/`collect`) over `getLine()` | Genuinely exercises the fly machinery; lightweight — no `Writer`/`StreamResource`; async `getLine` bridges via `AsyncStatus` (proven in Phase 1). `StandardFlyer`'s collect is `StreamResource`-oriented and would fight a no-Writer, array-per-line shape |
| Event shape | **One event per line**: a 1-D count array + scalar Y + derived X array | Idiomatic flyer output; one `collect` per row maps directly to one `getLine`; showcases line acquisition |
| Fast-axis (X) positions | **Derived** `linspace(x_start, x_stop, nx)` | Sim `getLine` returns counts without per-point encoder readback; continuous-position readback is deferred to real hardware |
| Slow axis (Y) | Stepped by the plan via the existing `PystxmAxis` | Reuse Phase-1 positioner; hybrid step-Y / fly-X raster (standard STXM pattern) |
| Sim source | pystxmcontrol's `simulation=True` (`connect(mock=False)`); real signals | Same as Phase 1 — exercise David's drivers, not a mock |
| Lightfall core | **Unchanged** (additive package-only work) | Phase 1 established async devices drive `BlueskyEngine` with no core change |

## Architecture

```
pystxmcontrol driver objs        ophyd-async / bluesky            Lightfall
─────────────────────────        ────────────────────            ─────────
keysight53230A(sim, line) ─┐
   getLine() → row counts  ├─▶ PystxmLineFlyer(Flyable) ─┐
xpsMotor X (fast axis) ────┘     kickoff/complete/collect ├─▶ stxm_fly_raster plan ─▶ RunEngine
                                                          │       (step Y, fly X)     / BlueskyEngine
xpsMotor Y (slow axis) ──────▶ PystxmAxis (stepped) ──────┘                                │
                                                                                  one event per line
```

Additive to the Phase-1 package; the Phase-1 `devices.py`/`backend.py`/`plugin.py`/`manifest.py`
are untouched. The flyer + plan are built directly in tests and the smoke script (as Phase 1's
Phase-0 did with `init_devices`); exposing flyers through the `DeviceBackend`/`DeviceCatalog` is a
later increment.

## Components

### Package layout (additions to `lightfall-pystxmcontrol`)

```
src/lightfall_pystxmcontrol/
├── flyer.py     # PystxmLineFlyer (new)
├── plans.py     # stxm_fly_raster (new)
├── config.py    # + make_sim_line_daq (extend)
└── tests/test_flyer.py, tests/test_fly_raster.py   (new)
scripts/smoke_flyscan_lightfall.py                  (new)
```

### `PystxmLineFlyer` (bluesky `Flyable`)

Wraps a pystxmcontrol `daq` configured for **line mode** plus the **fast-axis (X) `PystxmAxis`**.
Constructed with the daq config, the X-axis config, and a device `name` (e.g. `"Counter1"`).

- **`__init__(self, daq_config, x_axis_config, name="")`** — builds nothing yet (devices built in
  `connect()`, like the Phase-1 devices); holds config.
- **`connect(self, mock=False, ...)`** — build the sim daq (`config.make_sim_line_daq`) and the X
  `PystxmAxis`; connect both on the running loop (real `simulation=True` path).
- **`prepare(self, row)`** — set the upcoming row: `y` (recorded into events), `x_start`, `x_stop`,
  `nx`, `dwell`. (A plain method called by the plan before `kickoff`; not bluesky `Preparable`.)
- **`kickoff(self) -> AsyncStatus`** — move X to `x_start` via `await asyncio.to_thread(moveTo, …)`
  (blocking sync; instant in sim) and `config(dwell, points=nx, mode="line")` so `getLine()` will
  return `nx` values.
- **`complete(self) -> AsyncStatus`** — `await self._daq.getLine()`, store the row's count array,
  assert `len(counts) == nx`. (In sim the row is one `getLine` call; commanding a *continuous* X
  trajectory across the row is the deferred real-hardware path — here the swept positions are the
  derived `linspace`.)
- **`describe_collect(self) -> dict`** — declare one stream (`"primary"`) with `SampleX`
  (array, shape `[nx]`, number), `SampleY` (scalar number), `Counter1` (array, shape `[nx]`, number).
- **`collect(self) -> Iterator`** — yield **one** partial event for the row: `data = {"SampleX":
  linspace(x_start, x_stop, nx), "SampleY": y, "Counter1": counts}`, with `timestamps`/`time`.

The exact ophyd-async/bluesky surfaces (`AsyncStatus.wrap`, the `describe_collect`/`collect`
return schema, and the plan's `declare_stream`/`collect` stub sequence) are pinned against the
installed versions during implementation, as Phase 1 did for the point devices — the **contract**
(one event per line; the three keys with the stated shapes; `mock=False` sim path) is fixed.

### `config.make_sim_line_daq(daq_config)`

Sibling of `make_sim_counter`: wire a `keysight53230A(simulation=True)`, `d.meta.update(...)`
(preserving the driver's `gate` default — the Phase-1 `KeyError` lesson), `d.start()`. Line-mode
specifics (ensuring `getLine()` returns `nx` values: `points = nx`, `samples = 1`) are applied in
the flyer's `kickoff` via `config(...)`, pinned by the spike.

### `stxm_fly_raster(flyer, y_axis, *, y_start, y_stop, ny, x_start, x_stop, nx, dwell, md=None)` plan

```
open_run(md)
for y in linspace(y_start, y_stop, ny):
    mv(y_axis, y)
    flyer.prepare(row=(y, x_start, x_stop, nx, dwell))
    kickoff(flyer, wait=True)
    complete(flyer, wait=True)
    collect(flyer)            # emits one event for this row
close_run()
```

The exact collect/declare_stream stubs are pinned during implementation. Result: a
`start → descriptor → ny events → stop` stream.

## Data flow (sim fly raster)

1. Plan opens a run.
2. Per Y row: `mv(Y, y)` → `flyer.prepare(...)` → `kickoff` (X→`x_start`, daq line config) →
   `complete` (`await getLine()` → `nx` Poisson counts) → `collect` (one event: `SampleX[nx]`,
   `SampleY`, `Counter1[nx]`).
3. `ny` events, then close. Document stream flows through Lightfall's existing subscribers
   unchanged.
4. Proven twice: a bare `RunEngine` (internal checkpoint) and `engine(plan)` on Lightfall's
   `BlueskyEngine` (the enqueue pattern + offscreen-Qt headless harness established in Phase 1).

## Staged delivery

- **Spike — pin `getLine` line-mode semantics.** A short script that configures the sim daq for a
  line and calls `getLine()`, recording the exact `config(...)` call, the return type, and that the
  length equals the requested `nx`. Steers the flyer (analogous to Phase 1's `getPoint` spike).
- **Flyer + plan.** `PystxmLineFlyer` + `make_sim_line_daq` + `stxm_fly_raster`, TDD.
- **Bare-RunEngine proof.** `test_fly_raster.py` asserts the document stream on a bare RunEngine.
- **Lightfall proof.** Same raster via `engine(plan)` on `BlueskyEngine`; `smoke_flyscan_lightfall.py`
  prints the `ny×nx` raster (min/max).

## Testing

- **Unit** (`pytest` + `pytest-asyncio`): one `prepare → kickoff → complete → collect` cycle yields
  exactly one event whose `Counter1` and `SampleX` arrays have length `nx` and whose counts are
  positive (Poisson); `describe_collect` reports the array shapes/dtypes.
- **Integration (bare RunEngine):** `stxm_fly_raster` over a sim flyer + Y axis emits
  `start`, `ny` events, `stop`; each event carries `SampleX[nx]`, scalar `SampleY`, `Counter1[nx]`
  with positive counts.
- **Integration (Lightfall):** the same plan runs via `BlueskyEngine` (`engine(plan)` + wait);
  smoke script prints the raster shape.
- Run in **Lightfall's Python 3.14 venv** via `.venv/Scripts/python -m pytest`, never bare `pytest`.

## Risks

1. **`getLine` config drift.** The exact `config(...)` needed to make `getLine()` return `nx`
   values (`points`/`samples` semantics) must be pinned. *Mitigation:* the spike, before wrapping.
2. **`Flyable` collect schema / bluesky stub sequence.** `describe_collect`/`collect` and
   `declare_stream`/`collect` shapes vary by bluesky version. *Mitigation:* pin against the
   installed bluesky during implementation; the event contract is fixed.
3. **Async `getLine` through `complete()`.** `complete` must return an `AsyncStatus` that awaits
   `getLine` on the RunEngine loop. *Mitigation:* the same async-device pattern Phase 1 proved
   through both a bare RunEngine and `BlueskyEngine`.

## Out of scope (future increments)

Live Tiled/image streaming (`StandardDetector` + `Writer` + `StreamResource`); faithful X
velocity/trajectory (`FlyMotorInfo`); per-point encoder positions; `WatchableAsyncStatus` move
progress; derived energy/piezo motors; externalized config from pystxmcontrol JSON; catalog/backend
exposure of flyers; real hardware (`simulation=False`).
