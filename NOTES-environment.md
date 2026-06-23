# Environment Spike Notes — Task 1

## Interpreter / venv

- Python 3.12 (`py -3.12`), dedicated venv at `.venv/` inside repo.
- Lightfall's own venv is 3.14; this spike uses 3.12 per pystxmcontrol README cap.
- **OPEN reconciliation item (Task 6):** Phase 1 must confirm an interpreter where
  lightfall (3.14) + pystxmcontrol.drivers + ophyd_async all import; likely 3.14
  with `pip install -e ./_pystxmcontrol_src --no-deps`.

## Pinned versions (from `pip freeze`)

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
