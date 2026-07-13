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

### numpy bump — metadata pin conflict (NOT a Lightfall-core dep; runtime-benign)

Installing ophyd-async bumped numpy **2.2.6 -> 2.3.5** in this particular Lightfall 3.14 venv.
There is a **mutually-exclusive metadata pin** between two stacks:

- `pydantic-numpy 9.0.1` (transitive dep of ophyd-async) requires **`numpy~=2.3.5`** (>=2.3.5,<2.4)
- `gpcam` / `fvgp` / `hgdl` require **`numpy~=2.2.6`** (>=2.2.6,<2.3)

**Important attribution:** `gpcam`/`fvgp`/`hgdl` are **NOT dependencies of Lightfall** — they
do not appear in `lightfall/pyproject.toml`. In this venv they are `Required-by: tsuchinoko`
(Ron's separate gpCAM-based adaptive-experiment app, which happens to be installed in the same
venv). **A clean Lightfall venv without tsuchinoko + ophyd-async has no numpy conflict at all.**
The clash is tsuchinoko's gpCAM stack ↔ ophyd-async, not Lightfall ↔ ophyd-async.

**Runtime status (verified 2026-06-23):** at numpy 2.3.5, `import lightfall`, `import gpcam`
(8.2.9), `import fvgp`, and `from gpcam import GPOptimizer` ALL succeed — gpcam's `~=2.2.6`
pin is conservative and its code runs fine on 2.3.5. So even in the shared venv the conflict is
declaration-only, not a functional break.

**Guidance:** keep ophyd-async-based device integration out of any venv that also hosts the
tsuchinoko/gpCAM stack if you want pip resolves to stay clean — they don't need to share a venv.
If they must coexist, pin `numpy>=2.3.5,<2.4`. Rollback snapshot of the pre-Task-6 freeze:
`_lightfall_venv_freeze_pre_task6.txt` (untracked).

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

### Patches → now in the als-controls fork (SUPERSEDES the local clone)

**Post-Phase-1 update:** the local `_pystxmcontrol_src/` clone + manual patching is
**superseded**. The three install fixes now live on the fork
**`als-controls/pystxmcontrol`, branch `headless-install-fixes`**
(commit `fa801472a0e5f1dfe230edd48e9045dd3416a65d`), and are PR'd to David Shapiro.
The reproducible install is now a one-liner (no clone, no manual patching):

```bash
pip install --no-deps \
  "pystxmcontrol @ git+https://github.com/als-controls/pystxmcontrol.git@fa801472a0e5f1dfe230edd48e9045dd3416a65d"
```

The three fixes on that branch:

1. `pystxmcontrol/drivers/__init__.py`: lazy-import guard — each driver in `try/except`
   (mirrors the existing SmarAct/Aerotech pattern) so a missing optional SDK doesn't
   break importing the package.
2. `setup.py`: the Linux desktop-file install (`update-desktop-database`) made
   non-fatal / cross-platform — it ran unconditionally and raised `WinError 2` during
   the wheel build on Windows, aborting `pip install`.
3. `pyproject.toml`: `requires-python` relaxed from `">=3.9,<3.13"` to `">=3.9"`
   (the 3.12 cap is driven by GUI wheels; `--no-deps` skips them).

Once merged upstream, repoint at David's tag/commit and retire the fork.

---

## Phase 2a — fly-scan spike

**Script:** `scripts/smoke_getline.py`
**Interpreter:** `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python` (Python 3.14 / bluesky 1.14.6 / ophyd-async 0.19.2)

### (a) getLine line acquisition — pinned

Exact working call sequence:

```python
d = config.make_sim_counter(config.DEFAULT_COUNTER)   # build + meta.update + start
d.config(dwell=1.0, count=nx, samples=1)              # line config: concrete signature
data = asyncio.run(d.getLine())                        # returns numpy.ndarray, len == nx
```

- `config(dwell=…, count=nx, samples=1)` is the correct signature (NOT `points=` or `mode=`).
- `DEFAULT_COUNTER` has `"type": "point"` — that is fine; `getLine()` works regardless.
- `getLine()` returns `numpy.ndarray` of dtype `int32`, shape `(nx,)`.
- `len(data) == nx` confirmed for `nx = 5`.
- Sample output: `array([10139, 10097, 9886, 9863, 10008], dtype=int32)`

### (b) inline Flyable collect path — pinned

**Key finding:** bluesky 1.14.6's `bps.collect` emits `event_page` documents, NOT `event`.
The brief's expected doc names `['start', 'descriptor', 'event', 'stop']` are WRONG for this version.
Actual document stream observed (in order): `['start', 'descriptor', 'event_page', 'stop']`.

**Tasks 2 and 3 must use `event_page` throughout — not `event`.**

`event_page["data"][key]` is a list of per-event arrays; `[0]` indexes the first event's array.
For a one-event-per-line flyer, `event_page["data"]["Counter1"][0]` has shape `(nx,)`.

The `describe_collect` descriptor form with `"dtype": "array"` and `"shape": [nx]` is accepted
as-written — no `dtype_numpy` field required, no alternative spelling needed.

Working `kickoff` / `complete` / `collect` call forms (as-written in brief, confirmed working):
```python
yield from bps.kickoff(fl, wait=True)
yield from bps.complete(fl, wait=True)
yield from bps.collect(fl)        # emits event_page (not event)
```

### Exact spike stdout (representative run)

```
getLine type: <class 'numpy.ndarray'> len: 5 sample: array([10063, 10080,  9880, 10001,  9962], dtype=int32)
--- getLine pinned: ndarray len 5 ---
flyable doc names: ['start', 'descriptor', 'event_page', 'stop']
event_page Counter1 len: 5 SampleX len: 5
--- inline Flyable collect path OK ---
```

(Preceded by the expected 10-line pystxmcontrol lazy-import-guard noise.)

---

## Phase 2b — UI-launch spike

**Script:** `scripts/smoke_plan_ui.py`
**Interpreter:** `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python` (Python 3.14 / bluesky 1.14.6 / ophyd-async 0.19.2 / lightfall editable)
**Type:** empirical spike (NOT TDD). Probes Lightfall's *internal* plan-surfacing + device-catalog APIs so Tasks 2-4 build against confirmed forms.

### Lightfall source pinned (read-only, in `lightfall/src/lightfall/`)

- `plugins/plan_plugin.py` — `PlanPlugin(PluginType)`, `type_name="plan"`, `is_singleton=True`. ABC: abstract `name` (property) + abstract `get_plan_function()`; `category` property defaults `"general"`. `get_plan_info()` calls `PlanInfo.from_function(name=self.name, func=self.get_plan_function(), category=self.category)`. (Matches the prior-exploration note exactly.)
- `acquire/plans/registry.py` — `PlanInfo` + `ParameterInfo` dataclasses (see field names below); `PlanRegistry.register(name, func, category="general")` / `get_plan(name)->PlanInfo|None` / `list_plans(category=None)` / `register_or_replace(...)`.
- `ui/annotations.py` — frozen dataclasses, import-light (no Qt). Constructor arg names confirmed below.
- `ui/widgets/plan_config.py` — the device-vs-numeric classifier (`_build_param_spec` + `extract_annotated_metadata` + `get_param_category`); the verbatim `device_class` matching lambda.
- `ui/panels/bluesky_panel.py` — `_resolve_device_kwargs(self, plan_info, kwargs)` + `_resolve_single_device(catalog, name)` + `self._engine(plan)`.
- `devices/model.py`, `devices/catalog.py`, `devices/base.py` — `DeviceInfo` fields, `DeviceCatalog`, `DeviceBackend`.

### (a) PlanInfo / ParameterInfo field names — PINNED (assert these in Task 3)

`PlanInfo` (dataclass) public fields:
```
name, func, signature, description, category, parameters, examples, display_name, icon
```
Plus methods `get_display_name()`, `get_icon()`. `PlanInfo.from_function(name, func, category="general")` — keyword call works (`PlanInfo.from_function(name=..., func=..., category=...)`).

`ParameterInfo` (one per signature param, `info.parameters[i]`) fields + props:
```
name        : str          (parameter name)
annotation  : Any          (the RAW annotation — the Annotated[...] object/STRING, see (c))
default     : Any          (inspect.Parameter.empty when required)
kind        : inspect._ParameterKind
description : str          (parsed from the docstring Args: section)
required    : bool   (@property — default is inspect.Parameter.empty)
type_name   : str    (@property — annotation.__name__ or str(annotation); NOT a clean "int"/"float" when Annotated)
```
**Gotcha for Task 3:** `ParameterInfo.type_name` is NOT a clean base-type name for `Annotated[...]` params — it returns the full `str(annotation)` (e.g. `"Annotated[float, Unit('um')]"`, or the literal string when `from __future__ import annotations` is active). Do NOT assert `type_name == "float"`. To get the base type + UI metadata, use `lightfall.ui.widgets.plan_config.extract_annotated_metadata(param.annotation, func)` (returns `(base_type, [meta...])`).

### lightfall.ui.annotations constructor arg names — PINNED

```python
Unit(suffix: str)                                   # -> pyqtgraph spec["suffix"]
Decimals(places: int)                               # -> spec["decimals"]
Range(min=None, max=None)                           # -> spec["limits"] = (min, max)
Default(value)                                      # overrides signature default
DeviceFilter(device_class=None, category=None, group=None, source=None, name_pattern=None)
DeviceFilterAny(*filters)                           # OR of DeviceFilters (varargs)
DeviceDefault(*names, pattern=None)                 # pre-select
DeviceIcon(name)                                    # qtawesome icon
```
`DeviceFilter.category` accepts `str | set[str]`. All are `@dataclass(frozen=True)`. No `Qt` import — safe to import in plugin code.

### Working Annotated forms (use verbatim in Task 2/3 plan signature)

```python
flyer:   Annotated[Any, DeviceFilter(device_class=FLYER_DEVICE_CLASS)]
y_axis:  Annotated[Any, DeviceFilter(category="motor")]
y_start: Annotated[float, Unit("um")] = -5.0
ny:      Annotated[int, Range(1, 10000)] = 6
dwell:   Annotated[float, Unit("ms")] = 1.0
```
where `FLYER_DEVICE_CLASS = "lightfall_pystxmcontrol.flyer:PystxmLineFlyer"`.

### (c) Annotated classification + how a param becomes a device-picker — PINNED

The classifier lives in `plan_config._build_param_spec`:
1. `base_type, metadata = extract_annotated_metadata(annotation, func)` — strips `Annotated[T, m1, m2]` to `(T, [m1, m2])`. **Resolves STRING annotations** (from `from __future__ import annotations`) by `eval` against a namespace that includes `typing`, `Annotated`, the `lightfall.ui.annotations` classes, AND `func`'s module globals.
2. `category = get_param_category(name, base_type)` (name heuristics: `detectors`/`dets` -> DEVICES; `motor`/`signal`/`positioner`/`obj` -> DEVICE; else by type string).
3. **Override:** if any metadata item is a `DeviceFilter`/`DeviceFilterAny`, the param is forced to DEVICE (single) or DEVICES (if base is `list`/`tuple`). This is how `Annotated[Any, DeviceFilter(...)]` becomes a device-picker even though base `Any` is not device-like.

**VERIFIED IN-SCRIPT against the REAL Lightfall functions** — `smoke_plan_ui.py` imports
`extract_annotated_metadata`, `get_param_category`, `ParamCategory` from
`lightfall.ui.widgets.plan_config` and runs them on `_probe_plan` (the script has
`from __future__ import annotations`, so `param.annotation` is a STRING — the harder,
realistic case). No QApplication is constructed; both functions import and run cleanly
headless (they touch no Qt objects). Actual spike output:
```
param.annotation is a STRING (future-annotations)? True
flyer        -> device             (real base=Any, meta=['DeviceFilter'])
y_axis       -> device             (real base=Any, meta=['DeviceFilter'])
y_start      -> basic:float unit=um (real base=float, meta=['Unit'])
ny           -> basic:int range=(1, 10000) (real base=int, meta=['Range'])
dwell        -> basic:float unit=ms (real base=float, meta=['Unit'])
=> REAL classifier: flyer/y_axis=device, ny/dwell=basic — string-annotation classification WORKS under future-annotations.
```
The script `assert`s `flyer`/`y_axis` == `device` and `ny`/`dwell` startswith `basic:int`/`basic:float`,
so a regression would fail the spike.

**IMPORTANT for Tasks 2-4 (fold-forward #2, now EMPIRICALLY CONFIRMED):** classification works
under `from __future__ import annotations` **only because** `extract_annotated_metadata` is passed
`func` so `resolve_string_annotation` can eval the string against `func.__module__`'s globals.
The plugin module that defines the plan **must keep `Annotated`, `DeviceFilter`, `Unit`, `Range`,
and the `FLYER_DEVICE_CLASS` constant importable at module scope** — otherwise the eval fails and
the param silently falls back to a plain string field. Task 3 may use `from __future__ import
annotations` in the plan module (the realistic case is proven to work), provided those names stay
module-importable.

### device_class filter matching semantics — PINNED (a real gotcha)

Verbatim from `plan_config._build_param_spec` (the `filter_func` built for `DeviceFilter(device_class=dc)`):
```python
m["device_info"] is not None and (
    m["device_info"].device_class == dc
    or m["device_info"].device_class.rsplit(".", 1)[-1] == dc
)
```
- **`rsplit` is on `"."`, NOT `":"`.** Our `device_class` is `"lightfall_pystxmcontrol.flyer:PystxmLineFlyer"` (module:Class). Its last `"."`-segment is `"flyer:PystxmLineFlyer"`, so the bare-class fallback (`dc="PystxmLineFlyer"`) does **NOT** match.
- **Only full-string equality matches** for a `module:Class` device_class. Verified:
```
DeviceFilter(device_class='lightfall_pystxmcontrol.flyer:PystxmLineFlyer') selects: ['STXMLineFlyer']   (only the flyer)
DeviceFilter(device_class='PystxmLineFlyer')                              selects: []                  (bare-class fails)
DeviceFilter(category='motor')                                           selects: ['SampleX','SampleY']
```
**Task 2/3 rule:** the plugin's `Annotated[..., DeviceFilter(device_class=...)]` MUST pass the EXACT same `module:Class` string the flyer's `DeviceInfo.device_class` is registered with. Keep both pointing at one shared `FLYER_DEVICE_CLASS` constant.

### (b) non-Readable flyer in the device catalog — NONE NEEDED

`PystxmLineFlyer` is NOT Readable: `read()/describe()/read_configuration()/describe_configuration()/position/get()/connected` ALL absent (only `name`, `prepare`, `kickoff`, `complete`, `describe_collect`, `collect`).

Registering it as a `DeviceInfo` (DETECTOR, `_ophyd_device=flyer`) and exercising every catalog state/status/list/summary/resolve path **did not raise** — all 8 paths OK:
```
list_devices() / list_devices(DETECTOR) / get_device_by_name / state.status / to_summary()
/ search_devices / refresh_device_state / get_ophyd_device   -> all OK
=> non-Readable flyer broke the catalog path? NO
```
Why it's safe (pinned in source):
- `_add_device_internal` (package `backend.py`) sets `DeviceState` from `device._ophyd_device is not None` — never reads the device.
- `DeviceInfo.to_summary()` reads only `self._state` — never the ophyd device.
- `DeviceCatalog.refresh_device_state` is the ONLY path that probes the device, and it does so behind `hasattr(ophyd_dev, "position")` and `hasattr(ophyd_dev, "get")` guards (the `get()` call is also in a try/except). On the flyer both are absent, so it returns a plain ONLINE state.
- `mark_device_live` probes `getattr(ophyd_device, "connected", False)` (guarded) — not on the registration path used here.
- `DeviceConnectionManager` is NOT exercised when the backend pre-sets `_ophyd_device` (the spike registers via `_add_device_internal`, like Phase-1 does).

**Conclusion: do NOT add any `Readable` stub methods to `PystxmLineFlyer`. None are needed for the catalog/launch path.** (It is registered as a catalog DETECTOR purely for name-resolution; it is consumed by the plan as a Flyable, not read() by Bluesky.)

### Exact flyer DeviceInfo registration call (copy-paste for Task 2)

```python
from lightfall.devices.model import ConnectionType, DeviceCategory, DeviceInfo

FLYER_DEVICE_CLASS = "lightfall_pystxmcontrol.flyer:PystxmLineFlyer"

flyer_info = DeviceInfo(
    name="STXMLineFlyer",
    description="Simulated pystxmcontrol STXM line flyer",
    device_class=FLYER_DEVICE_CLASS,             # MUST equal the DeviceFilter(device_class=...) string
    category=DeviceCategory.DETECTOR,            # no FLYER category exists; DETECTOR is correct
    connection_type=ConnectionType.SIMULATED,
    prefix="STXMLineFlyer",
    tags=["flyer", "stxm", "pystxmcontrol", "simulated"],
    metadata={},
)
flyer_info._ophyd_device = flyer                 # the connected PystxmLineFlyer instance
# then register it the way backend.py does its own devices:
backend._add_device_internal(flyer_info)
backend._ophyd_devices["STXMLineFlyer"] = flyer  # so get_ophyd_device() finds it too
```
The Phase-1 `PystxmStxmBackend.connect()` is the natural home: extend it to also build+connect the flyer and register it with the same `_add_device_internal` pattern it already uses for SampleX/SampleY/Counter1.

### (d) Exact resolve + run call sequence — PINNED (copy-paste for Task 4)

The UI delivers device params as **name strings**; `_resolve_device_kwargs` (which keys off the live pyqtgraph param tree's `type=="device"`) replaces them with ophyd instances via `_resolve_single_device` -> `catalog.get_device_by_name(name).ophyd_device`. At API level (no Qt tree) the equivalent is:

```python
catalog = DeviceCatalog.get_instance()

def resolve(name):                               # mirrors BlueskyPanel._resolve_single_device
    di = catalog.get_device_by_name(name)
    return di.ophyd_device                        # already-connected instance (else request_device_connection)

resolved = {
    "flyer":  resolve("STXMLineFlyer"),
    "y_axis": resolve("SampleY"),
    "y_start": -5.0, "y_stop": 5.0, "ny": 6,
    "x_start": -5.0, "x_stop": 5.0, "nx": 10, "dwell": 1.0,
}

# In the real panel:  self._engine(plan_info.func(**resolved))
# Headless spike (Engine is a heavy Qt QObject w/ background queue) used a bare RunEngine,
# which proves the same binding contract:
from bluesky import RunEngine
docs = []
RE = RunEngine({})
RE(plan_info.func(**resolved), lambda n, d: docs.append((n, d)))
```
**Engine note for Task 4:** `lightfall.acquire.get_engine()` returns a `BaseEngine(QObject)` with a priority queue + background worker thread — heavy, Qt-bound, and async. For a deterministic headless test, drive a **bare `RunEngine({})`** (brief-sanctioned). The binding contract (`func(**resolved)` -> generator -> engine call) is identical; only the executor differs.

End-to-end result (bluesky 1.14.6 — emits `event_page`, per Phase 2a):
```
document names: ['start', 'descriptor', 'event_page', 'event_page', 'event_page', 'event_page', 'event_page', 'event_page', 'stop']
event_page count: 6 (expected ny=6)
positive-count pages: 6/6  total counts=600073.0
```
`event_page["data"]["STXMLineFlyer"][0]` is the per-line count array (list-wrapped -> `[0]`, per Phase 2a).

### Representative spike stdout (lazy-import-guard noise + loguru lines elided)

```
--- (a) PlanInfo.from_function field names ---
type(info): PlanInfo
PlanInfo public fields: ['name', 'func', 'signature', 'description', 'category', 'parameters', 'examples', 'display_name', 'icon']
type(parameters[0]): ParameterInfo
ParameterInfo fields: ['name', 'annotation', 'default', 'kind', 'description'] + props: required, type_name
  name='flyer'  type_name='Annotated[Any, DeviceFilter(device_class=FLYER_DEVICE_CLASS)]' required=True  ...
  name='ny'     type_name='Annotated[int, Range(1, 10000)]' required=False default=6 ...

--- (c) Annotated classification (REAL lightfall.ui.widgets.plan_config) ---
  param.annotation is a STRING (future-annotations)? True
  flyer        -> device             (real base=Any, meta=['DeviceFilter'])
  y_axis       -> device             (real base=Any, meta=['DeviceFilter'])
  ny           -> basic:int range=(1, 10000) (real base=int, meta=['Range'])
  dwell        -> basic:float unit=ms (real base=float, meta=['Unit'])
  => REAL classifier: flyer/y_axis=device, ny/dwell=basic — string-annotation classification WORKS under future-annotations.

--- (b) non-Readable flyer in the device catalog ---
backend.connect(): True device_count: 3
flyer has read(): False  describe(): False  position: False  get(): False  connected: False
  OK   list_devices(): ['SampleX', 'SampleY', 'Counter1', 'STXMLineFlyer']
  OK   list_devices(DETECTOR): ['Counter1', 'STXMLineFlyer']
  OK   get_device_by_name('STXMLineFlyer'): 'STXMLineFlyer'
  OK   flyer_info.state.status: 'online'
  OK   refresh_device_state(flyer): 'online'
  OK   get_ophyd_device('STXMLineFlyer'): 'PystxmLineFlyer'
  => non-Readable flyer broke the catalog path? NO (no path read()/describe()/position/value on it)

--- (c) DeviceFilter(device_class=...) matching ---
  DeviceFilter(device_class='lightfall_pystxmcontrol.flyer:PystxmLineFlyer') selects: ['STXMLineFlyer']
  bare-class fallback DeviceFilter(device_class='PystxmLineFlyer') selects: []
  DeviceFilter(category='motor') selects: ['SampleX', 'SampleY']

--- (d) end-to-end launch path ---
  resolved flyer: PystxmLineFlyer name= STXMLineFlyer
  resolved y_axis: PystxmAxis name= SampleY
  event_page count: 6 (expected ny=6)
  positive-count pages: 6/6  total counts=600073.0
  end-to-end run: PASS

--- Phase 2b spike complete ---
```
(Preceded by the expected ~10-line pystxmcontrol lazy-import-guard noise + a few loguru INFO/DEBUG lines.)

---

## Spec #2 (caproto IOCs) — deps added to the lightfall 3.14 venv (2026-07-12)

| Package | Needed by |
|---|---|
| `matplotlib` | mclController/fccd_control import guard (driver availability for config tests) |
| `pylibftdi` | bcs/npt/mmc controller imports |
| `pipython` | E712Controller (sim + hardware; required for e2e fly tests — must NOT skip) |

caproto 1.3.0 / ophyd 1.11.1 were already present. Test env facts: per-test random CA ports need BOTH
`EPICS_CAS_SERVER_PORT` (server bind, caproto also honors `EPICS_CA_SERVER_PORT`) and client
`EPICS_CA_ADDR_LIST=127.0.0.1:<port>`; enum PVs cannot be written as bare strings from caproto's
threading client (write by index or `data_type=ChannelType.STRING`); on Windows only one process
bound to UDP 5064 receives CA searches, hence the supervisor's per-IOC-port mode (default).
Worktree: `_pystxmcontrol_iocs_wt` (branch `feature/caproto-iocs`, LOCAL). Tests:
`PYTHONPATH=<worktree> lightfall-venv-python -m pytest tests/iocs -v` (~2 min, 51 tests).

---

## Spec #3 (EPICS environment) — documentation & environment facts (2026-07-13)

**netifaces installed (REQUIRED — 2026-07-12):** The optional caproto dependency `netifaces`
is load-bearing for EPICS CA address-list discovery on Windows. Without it, `ophyd_async`
connections to caproto-backed IOCs fail silently. Installed via `pip install netifaces` in
the lightfall 3.14 venv. The plugin guard in `epics_env.py::ensure_caproto_layer()` raises
`ImportError` if it is missing.

**OPHYD_CONTROL_LAYER=caproto:** Set by `epics_env.ensure_caproto_layer()` on first import
of the plugin. Can also be set explicitly in the environment before importing ophyd-async.

**Tests depend on PYSTXMCONTROL_IOCS_SRC:** The session-scoped `stxm_fleet` fixture (in
`tests/conftest.py`) spawns the full IOC fleet as subprocess instances. It requires the
pystxmcontrol fork with the caproto IOC layer at the path given by the environment variable
`PYSTXMCONTROL_IOCS_SRC`, or defaults to `_pystxmcontrol_iocs_wt`. If the path or branch
is wrong, pytest fails with a clear message.

**Fleet fixture behavior:** `stxm_fleet` spawns approximately 4 IOC subprocesses (one per
controller type: motors, DAQ, etc.), each on a random ephemeral UDP port in the range
40000–60000. `EPICS_CA_ADDR_LIST` and `EPICS_CA_AUTO_ADDR_LIST=NO` are set in each
subprocess environment so clients can locate all IOCs. The fixture lifetime is per-session;
teardown kills all subprocesses.
