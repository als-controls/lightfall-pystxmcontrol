# Environment Spike Notes — Task 1

## Interpreter / venv

- Python 3.12 (`py -3.12`), dedicated venv at `.venv/` inside repo (Phase 0 only).
- Lightfall's own venv is 3.14; this spike uses 3.12 per pystxmcontrol README cap.
- **RESOLVED (Task 6):** Phase 1 uses Lightfall's 3.14 venv. See section below.

## Pinned versions — Phase 0 (3.12 spike venv only)

> These versions are the dedicated **3.12 spike venv** used for Phase 0 (Tasks 1–5).
> The Phase 1 Lightfall 3.14 venv has DIFFERENT versions (e.g. `bluesky==1.14.6`) —
> see the "Task 6 — Phase 1 interpreter resolution" section below for the 3.14 set.

```
bluesky==1.15.1
numpy==2.3.5
ophyd-async==0.19.2
pyzmq==27.1.0
pystxmcontrol==1.0  (editable from _pystxmcontrol_src/, commit 346728584d22d1e198e596021e4920efeb2d8a03)
```

## Install path: --no-deps fallback was used

Full install failed:
```
pip install git+https://github.com/davidalexandershapiro/pystxmcontrol.git
```
Error:  `error: [WinError 2] The system cannot find the file specified` during wheel
build (`install_scripts` step). A Windows path issue in pystxmcontrol's setup.

Working path (the --no-deps fallback):
```bash
git clone https://github.com/davidalexandershapiro/pystxmcontrol.git ./_pystxmcontrol_src/
.venv/Scripts/python -m pip install -e ./_pystxmcontrol_src --no-deps
.venv/Scripts/python -m pip install numpy pyzmq pyepics pylibftdi pyserial python-usbtmc pyusb
```
The `_pystxmcontrol_src/` clone is in `.gitignore` and must not be committed.

## Drivers import: lazy-import guard required

`pystxmcontrol/drivers/__init__.py` eager-imports all 29 drivers at package load.
Several drivers need hardware SDKs or heavy GUI deps not installable without wheels:

| Module | Missing dep |
|---|---|
| `fccd_control` | `scipy` |
| `mclController` | `matplotlib` |
| `E712Controller` | `pipython` (PI GCS Python) |
| `xspress3` | `h5py` |
| `mcsController/Motor` | SmarAct SDK |
| `aerotechController/Motor` | Aerotech SDK |

**Fix applied:** Wrapped every eager import in `try/except Exception` with a print
message (same pattern David already uses for SmarAct/Aerotech at the bottom of the
file). This is a minimal upstream guard — the file change is in
`_pystxmcontrol_src/pystxmcontrol/drivers/__init__.py` and should be offered to
David Shapiro as a PR.

After the guard, `import pystxmcontrol.drivers.xpsMotor, pystxmcontrol.drivers.keysight53230A`
succeeds (prints unavailable-module warnings to stdout, not errors).

Note: `d.meta = DAQ_META` in the brief's smoke script omits the `"gate"` key required
by `keysight53230A.start()`. Fixed to `d.meta.update(DAQ_META)` so the default
`"gate": False` is preserved.

## getPoint() return type/shape/sample

```
type:   numpy.ndarray
shape:  (1,)
repr:   array([9901])    # (Poisson draw; varies each run; ~1e4 for dwell=1.0 ms)
```

Call signature: `await d.getPoint()` — no arguments. The ABC declares
`getPoint(self, scan, **kw)` but the concrete `keysight53230A.getPoint(self)` takes
no arguments. Calling it without `scan` is the working form.

**Task 4 note:** `getPoint()` returns `numpy.ndarray` of shape `(1,)`. Unwrap with
`data[0]` to get a scalar int64.

## Smoke script console output (representative run)

```
pystxmcontrol.drivers.fccd_control not available: No module named 'scipy'
pystxmcontrol.drivers.mclController not available: No module named 'matplotlib'
pystxmcontrol.drivers.E712Controller not available: No module named 'pipython'
pystxmcontrol.drivers.xspress3 not available: No module named 'h5py'
SmarAct SDK not installed.
Aerotech SDK not installed.
motor pos after moveTo(5.0): 5.0 moving: False
daq getPoint: [9901]
daq getPoint type: <class 'numpy.ndarray'>
daq getPoint repr: array([9901])
daq getPoint shape: (1,)
```

The six "not available" lines are expected; they are warnings from the lazy-import
guard, not errors. The motor and DAQ lines confirm the sim path works.

---

## Task 6 -- Phase 1 interpreter resolution

**Chosen interpreter:** Lightfall's existing 3.14 venv at
`C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python` (Python 3.14.0).
All subsequent Phase 1 work uses this interpreter for `.venv/Scripts/python`.

### Install sequence (all against the 3.14 lightfall venv)

```bash
# 1. Rollback snapshot (untracked, gitignored)
C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python \
    -m pip freeze > _lightfall_venv_freeze_pre_task6.txt

# 2. ophyd-async (cp314 native wheel available)
C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python \
    -m pip install ophyd-async

# 3. Patch pystxmcontrol pyproject.toml: relaxed requires-python
#    _pystxmcontrol_src/pyproject.toml: ">=3.9,<3.13" -> ">=3.9"
#    (GUI deps still blocked by --no-deps; the upstream cap is driven by PySide6
#     and other GUI wheels, not the driver modules we need.)

# 4. Install patched pystxmcontrol editable, no-deps
C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python \
    -m pip install -e _pystxmcontrol_src --no-deps

# 5. Extra deps needed by xpsMotor / keysight53230A on 3.14
#    (not in lightfall's venv before this task)
C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python \
    -m pip install python-usbtmc pyusb pyserial
```

### numpy bump — HARD pin conflict (runtime-benign today, but read this)

Installing ophyd-async bumped numpy **2.2.6 -> 2.3.5** in Lightfall's 3.14 venv.
This is a genuine **mutually-exclusive metadata pin conflict**, not just a warning:

- `pydantic-numpy 9.0.1` (transitive dep of ophyd-async) requires **`numpy~=2.3.5`** (>=2.3.5,<2.4)
- `gpcam` / `fvgp` / `hgdl` (already in Lightfall's venv) require **`numpy~=2.2.6`** (>=2.2.6,<2.3)

No single numpy version satisfies both. The venv currently sits at 2.3.5 (ophyd-async's side).

**Runtime status (verified 2026-06-23):** at numpy 2.3.5, `import lightfall`, `import gpcam`
(8.2.9), `import fvgp`, and `from gpcam import GPOptimizer` ALL succeed — gpcam's `~=2.2.6`
pin is conservative and its code runs fine on 2.3.5. So the conflict is currently
declaration-only, not a functional break.

**Risk / guidance:** a future `pip install`/`pip install --upgrade` that re-resolves against
gpcam's pin could silently DOWNGRADE numpy to 2.2.x and then break ophyd-async's
pydantic-numpy (or vice versa). If this venv must stay stable, pin `numpy>=2.3.5,<2.4`
explicitly. A rollback snapshot of the pre-Task-6 freeze is at
`_lightfall_venv_freeze_pre_task6.txt` (untracked). Longer term, a dedicated venv for the
pystxmcontrol/ophyd-async integration (separate from gpcam-based adaptive work) avoids the
clash entirely — flag for Ron's decision.

### Combined import verification (the crux)

```
$ python -c "import pystxmcontrol.drivers.xpsMotor, pystxmcontrol.drivers.keysight53230A, ophyd_async, lightfall; print('OK on 3.14')"
pystxmcontrol.drivers.epicsMotor not available: No module named 'epics'
pystxmcontrol.drivers.nptController not available: No module named 'pylibftdi'
pystxmcontrol.drivers.bcsController not available: No module named 'pylibftdi'
pystxmcontrol.drivers.mmcController not available: No module named 'pylibftdi'
pystxmcontrol.drivers.fccd_control not available: No module named 'matplotlib'
pystxmcontrol.drivers.mclController not available: No module named 'matplotlib'
pystxmcontrol.drivers.areaDetector not available: No module named 'epics'
pystxmcontrol.drivers.E712Controller not available: No module named 'pipython'
pystxmcontrol.drivers.xspress3 not available: No module named 'epics'
SmarAct SDK not installed.
Aerotech SDK not installed.
OK on 3.14
```

The "not available" lines are expected lazy-import guard warnings; they are NOT errors.
`import lightfall` succeeds (no regression from the numpy bump or ophyd-async install).

### Plugin import verification

```
$ python -m pip install -e C:/Users/rp/PycharmProjects/ncs/lightfall-pystxmcontrol --no-deps
Successfully installed lightfall-pystxmcontrol-0.1.dev5+g12a3dbd1f

$ python -c "import lightfall_pystxmcontrol; print('plugin importable')"
plugin importable
```

### Summary of extra deps added to lightfall's 3.14 venv

| Package | Version | Needed by |
|---|---|---|
| `ophyd-async` | 0.19.2 | our wrappers |
| `colorlog` | 6.10.1 | ophyd-async |
| `pydantic-numpy` | 9.0.1 | ophyd-async |
| `ruamel-yaml` | 0.18.0 | ophyd-async |
| `scanspec` | 1.0.0 | ophyd-async |
| `semver` | 3.0.4 | ophyd-async |
| `compress-pickle` | 2.1.0 | ophyd-async |
| `velocity-profile` | 1.0.0 | ophyd-async |
| `numpy` | 2.3.5 | bumped from 2.2.6 by ophyd-async |
| `python-usbtmc` | 0.8 | keysight53230A -> keysightCounter |
| `pyusb` | 1.3.1 | python-usbtmc -> usb.core |
| `pyserial` | 3.5 | keysight53230A -> shutter |
| `pystxmcontrol` | 1.0 (editable) | our wrappers |
| `lightfall-pystxmcontrol` | 0.1.dev5 (editable) | this package |

### Patches applied to _pystxmcontrol_src

1. `pystxmcontrol/drivers/__init__.py`: lazy-import guard (Task 1, preserved).
2. `pyproject.toml`: `requires-python` relaxed from `">=3.9,<3.13"` to `">=3.9"`
   so editable install succeeds on Python 3.14. The 3.12 cap in the upstream README
   is driven by GUI wheels (PySide6 etc.); `--no-deps` skips all GUI deps so 3.14
   works cleanly for the driver modules.
