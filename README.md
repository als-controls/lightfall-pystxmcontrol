# lightfall-pystxmcontrol

ophyd-async wrappers that expose David Shapiro's
[`pystxmcontrol`](https://github.com/davidalexandershapiro/pystxmcontrol) STXM
device drivers to the [Lightfall](https://git.als.lbl.gov/ncs) control
dashboard, so a **simulated STXM bluesky scan** — both a step-mode 2D raster
and a **line fly raster** (`getLine`) — can run inside Lightfall with no real
hardware.

This is a **simulation prototype** (a collaboration spike with David, ALS). It
wraps the *driver* objects only — pystxmcontrol's GUI, ZMQ client,
`stxmserver`, and its own asyncio scan engine are **not** used; Lightfall's
`BlueskyEngine`/`RunEngine` does the orchestration.

## What it provides

| Component | File | Role |
|---|---|---|
| `PystxmAxis` | `devices.py` | ophyd-async positioner over a pystxmcontrol `motor` (sim) |
| `PystxmCounter` | `devices.py` | ophyd-async detector over a pystxmcontrol `daq` (sim, Poisson counts) |
| `PystxmLineFlyer` | `flyer.py` | bluesky `Flyable`/`Collectable` over a pystxmcontrol `daq` (sim) — flies one raster line per `getLine()`, per-row dwell via `prepare()` |
| `stxm_fly_raster` | `plans.py` | line-fly raster plan — steps the slow axis (Y), flies the fast axis (X) per row, one event per line |
| `StxmFlyRasterPlanPlugin` | `plan_plugin.py` | `PlanPlugin` surfacing the fly raster in Lightfall's plan registry/UI |
| `PystxmBackendPlugin` | `plugin.py` | `HappiDatabasePlugin` subclass — loads the packaged happi DB and registers devices via Lightfall's built-in `HappiBackend` |
| device database | `pystxm_happi.json` | happi JSON device database (regenerate via `scripts/build_pystxm_happi_db.py`) |
| `manifest` | `manifest.py` | `PluginManifest` on the `lightfall.plugins` entry point (device backend, plan, visualization) |
| sim config | `config.py` | in-repo motor/daq config dicts + `make_sim_motor`/`make_sim_counter` wiring |

## Devices

Device instances are defined in `src/lightfall_pystxmcontrol/pystxm_happi.json` and loaded by
Lightfall's built-in `HappiBackend` through the `HappiDatabasePlugin` base class.
`PystxmBackendPlugin` subclasses `HappiDatabasePlugin` and points it at this packaged JSON;
no hand-written `DeviceBackend` is needed. The device classes (`PystxmAxis`, `PystxmCounter`,
`PystxmLineFlyer`) are ophyd-async and are connected by Lightfall's device pipeline.

To regenerate the database after adding or renaming devices:

```bash
python scripts/build_pystxm_happi_db.py
```

Devices connect with `mock=False` so pystxmcontrol's own `simulation=True` code
path runs — we exercise David's drivers, not ophyd-async's mock. Signals are
real (`soft_signal_rw`); `motor.moveTo` (blocking) is called via
`asyncio.to_thread`; `daq.getPoint` (a coroutine) is awaited directly.

## Install

pystxmcontrol is consumed from a **pinned als-controls fork** that carries three
small fixes for a clean headless, cross-platform install (lazy-import guard,
non-fatal Linux desktop hook, relaxed `requires-python` — all PR'd upstream to
David Shapiro). Install it `--no-deps` to skip its heavy GUI dependencies
(PySide6, opencv, ...); the simulated driver path only needs
numpy/pyzmq/usbtmc/serial. Full details and pinned versions are in
[`NOTES-environment.md`](NOTES-environment.md). Against the target interpreter's venv:

```bash
# 1. ophyd-async (native cp314 wheel; pulls scanspec, pydantic-numpy, ...)
python -m pip install ophyd-async bluesky numpy

# 2. pystxmcontrol driver modules from the pinned fork, no GUI deps
python -m pip install --no-deps \
  "pystxmcontrol @ git+https://github.com/als-controls/pystxmcontrol.git@fa801472a0e5f1dfe230edd48e9045dd3416a65d"
python -m pip install pyzmq python-usbtmc pyusb pyserial   # minimal driver deps

# 3. this package
python -m pip install -e . --no-deps
```

(The `hardware` extra in `pyproject.toml` records the same pinned fork URL, so
`pip install -e ".[hardware]" --no-deps` installs both in one step.)

- **Phase 0** (driver/wrapper proof, no Lightfall) runs on a dedicated **Python
  3.12** venv.
- **Phase 1** (integration) runs in **Lightfall's Python 3.14 venv**, where
  `import lightfall`, `import pystxmcontrol.drivers.xpsMotor`, and
  `import ophyd_async` all succeed.

> **numpy caveat:** ophyd-async's `pydantic-numpy` pins `numpy~=2.3.5` while
> `gpcam`/`fvgp`/`hgdl` (in Lightfall's venv) pin `numpy~=2.2.6` — mutually
> exclusive metadata pins. It is runtime-benign today (gpcam imports/runs on
> 2.3.5). See `NOTES-environment.md` for the rollback freeze and guidance.

## Run the tests

```bash
.venv/Scripts/python -m pytest          # never bare `pytest`
```
Tests that import `lightfall` (`test_backend.py`, `test_backend_flyer.py`,
`test_plugin_integration.py`) require Lightfall's 3.14 venv. The bare-RunEngine
fly tests (`test_fly_raster.py`, `test_flyer.py`) run on either venv.

## Smoke scripts

```bash
# step-mode 2D raster
.venv/Scripts/python scripts/smoke_raw.py             # raw pystxmcontrol sim path (no ophyd)
.venv/Scripts/python scripts/smoke_gridscan.py        # 2D raster on a bare RunEngine
.venv/Scripts/python scripts/smoke_lightfall.py       # 2D raster via Lightfall's BlueskyEngine

# line fly raster
.venv/Scripts/python scripts/smoke_getline.py         # raw getLine() sim path (no ophyd)
.venv/Scripts/python scripts/smoke_flyscan_lightfall.py  # fly raster via Lightfall's BlueskyEngine
.venv/Scripts/python scripts/smoke_flyscan_ui.py      # fly raster via the plan-plugin + device-binding path
```
`smoke_lightfall.py` enqueues the plan via `engine(plan)` (the `BlueskyEngine`
runs its RunEngine on a worker thread) and prints e.g.
`grid_scan ran via Lightfall BlueskyEngine: 25 points; min=... max=...`.
`smoke_flyscan_lightfall.py` prints e.g.
`fly raster ran via Lightfall BlueskyEngine: 6 lines x 10 pts; min=... max=...`.

## Upstream fork & PR

The three install fixes live on the **als-controls fork**
(`als-controls/pystxmcontrol`, branch `headless-install-fixes`) and are offered
to David Shapiro as an upstream PR:

1. `drivers/__init__.py` — lazy-import guard (each driver in `try/except`,
   mirroring the existing SmarAct/Aerotech pattern) so a missing hardware SDK
   (epics, pylibftdi, scipy, matplotlib, h5py, ...) doesn't break importing the
   package.
2. `setup.py` — make the Linux desktop-file install non-fatal / cross-platform
   (it ran `update-desktop-database` unconditionally → `WinError 2` aborted the
   wheel build on Windows).
3. `pyproject.toml` — relax `requires-python` to allow 3.13+.

Once David merges upstream, repoint the `hardware` dependency in
`pyproject.toml` (and the install command above) at his upstream tag/commit and
retire the fork.

## Implemented since Phase 1

Line fly scanning via `getLine()` — `PystxmLineFlyer` (a hand-rolled
`Flyable`/`Collectable`, not ophyd-async's `StandardFlyer`) with per-row dwell
configured through `prepare()`, driven by the `stxm_fly_raster` plan and
surfaced in Lightfall's plan registry via `StxmFlyRasterPlanPlugin`.

## Phase A: energy stacks (option-5 vertical slice)

- `stxm_energy_stack` plan: an (ny, nx) fly image per energy; one run, one
  `primary` stream, `nE*ny` line events. Contract: `contract.py` +
  `docs/superpowers/specs/2026-07-07-stxm-lightfall-option5-design.md` §4.
- STXM Scan panel (`stxm_scan`): region-on-image (through Tiled, motor
  coords), energy ranges, device pickers, validated submit.
- STXM Energy Stack viz (`stxm_stack`): live per-line cube fill with energy
  slider + live-follow.
- Golden fixture: `tests/fixtures/golden_energy_stack_run.json`
  (regenerate: `scripts/make_golden_fixture.py`).
- Smoke: `scripts/smoke_energy_stack.py`.

## Out of scope

Per-scan dwell via the ophyd-async `configure` protocol (we use `prepare()`
instead), move-progress `WatchableAsyncStatus`, derived/energy/piezo motors,
real hardware (`simulation=False` with `getStatus()` polling).
