# lightfall-pystxmcontrol

ophyd-async wrappers that expose David Shapiro's
[`pystxmcontrol`](https://github.com/davidalexandershapiro/pystxmcontrol) STXM
device drivers to the [Lightfall](https://git.als.lbl.gov/ncs) control
dashboard, so a **simulated STXM 2D-raster bluesky scan** can run inside
Lightfall with no real hardware.

This is a **Phase-1 simulation prototype** (a collaboration spike with David,
ALS). It wraps the *driver* objects only — pystxmcontrol's GUI, ZMQ client,
`stxmserver`, and its own asyncio scan engine are **not** used; Lightfall's
`BlueskyEngine`/`RunEngine` does the orchestration.

## What it provides

| Component | File | Role |
|---|---|---|
| `PystxmAxis` | `devices.py` | ophyd-async positioner over a pystxmcontrol `motor` (sim) |
| `PystxmCounter` | `devices.py` | ophyd-async detector over a pystxmcontrol `daq` (sim, Poisson counts) |
| `PystxmStxmBackend` | `backend.py` | Lightfall `DeviceBackend` — builds/connects the devices, registers them in the `DeviceCatalog` |
| `PystxmBackendPlugin` | `plugin.py` | `DeviceBackendPlugin` so Lightfall discovers the backend |
| `manifest` | `manifest.py` | `PluginManifest` on the `lightfall.plugins` entry point |
| sim config | `config.py` | in-repo motor/daq config dicts + `make_sim_motor`/`make_sim_counter` wiring |

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
Phase-1 tests (`test_backend.py`, `test_plugin_integration.py`) require
Lightfall's 3.14 venv (they import `lightfall`).

## Smoke scripts

```bash
.venv/Scripts/python scripts/smoke_raw.py        # raw pystxmcontrol sim path (no ophyd)
.venv/Scripts/python scripts/smoke_gridscan.py   # 2D raster on a bare RunEngine (Phase 0)
.venv/Scripts/python scripts/smoke_lightfall.py  # 2D raster via Lightfall's BlueskyEngine (Phase 1)
```
`smoke_lightfall.py` enqueues the plan via `engine(plan)` (the `BlueskyEngine`
runs its RunEngine on a worker thread) and prints e.g.
`grid_scan ran via Lightfall BlueskyEngine: 25 points; min=... max=...`.

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

## Out of scope (Phase 2+)

Fly scanning (`getLine` + `StandardFlyer`), per-scan dwell via
`prepare`/`configure`, move-progress `WatchableAsyncStatus`, derived/energy/piezo
motors, real hardware (`simulation=False` with `getStatus()` polling).
