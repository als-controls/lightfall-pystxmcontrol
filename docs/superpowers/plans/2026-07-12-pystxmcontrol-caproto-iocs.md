# pystxmcontrol caproto IOC Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap David Shapiro's pystxmcontrol device drivers as caproto EPICS IOCs (spec #2), so Lightfall and any EPICS client talk to STXM hardware as standard PVs.

**Architecture:** New leaf subpackage `pystxmcontrol.iocs` in the als-controls fork. A `MotorRecordGroup` (caproto `record='motor'`) wraps each `pystxmcontrol.drivers.*Motor`; per-controller IOC processes host groups of axes; the E712 IOC adds a FLY PVGroup running the line loop IOC-side; DAQ/shutter get small custom groups; a supervisor (`stxm-iocs`) parses David's `motor.json`/`daq.json` and manages one subprocess per controller with restart-backoff and status PVs.

**Tech Stack:** Python 3.14 (lightfall venv), caproto 1.3.0 (asyncio server), ophyd 1.11.1 with `OPHYD_CONTROL_LAYER=caproto` for e2e, pytest 9. Windows host — spawn-safe subprocesses only (`sys.executable -m ...`), no fork().

## Global Constraints

- **Repo/worktree:** all code goes in the pystxmcontrol fork. Main checkout: `C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\_pystxmcontrol_src` (remotes: `origin` = davidalexandershapiro — NEVER push; `fork` = als-controls). Work happens in a **git worktree** at `C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\_pystxmcontrol_iocs_wt`, branch `feature/caproto-iocs` off `headless-install-fixes` (its install fixes are load-bearing on Windows). Branch stays LOCAL — Ron drives pushes/PRs.
- **Interpreter:** ALWAYS `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python` (referred to below as `$PY`). Never bare `python`/`pytest`.
- **Editable-install pitfall:** `pystxmcontrol` is installed editable from `_pystxmcontrol_src` (the MAIN checkout). Every test/run command in the worktree MUST set `PYTHONPATH` to the worktree root, e.g. `PYTHONPATH=/c/Users/rp/PycharmProjects/ncs/lightfall-pystxmcontrol/_pystxmcontrol_iocs_wt` — otherwise you silently test the main checkout's code.
- **Import isolation:** nothing under `pystxmcontrol/iocs/` may be imported by the base package; `pystxmcontrol.iocs.__init__` must degrade gracefully (clear ImportError message) when caproto is missing.
- **Do NOT modify** `pystxmcontrol/controller/client.py`, `server.py`, `controller.py`, any GUI code, or any existing driver file. Config files: adding an OPTIONAL `"epics"` sub-dict *inside* an existing motor/daq entry is allowed (David's code ignores unknown per-entry keys); adding new TOP-LEVEL keys to `motor.json` is FORBIDDEN (his code iterates top-level keys as motors).
- **PV naming default:** `STXM{station}:{controller_label}:{axis}` (e.g. `STXM7011:E712:FineX`); fly PVs nest as `...:FLY:GO`; DAQ as `STXM{station}:{daq_label}:COUNTS`.
- **CA env for anything that talks CA:** `EPICS_CA_ADDR_LIST=127.0.0.1 EPICS_CA_AUTO_ADDR_LIST=NO`, and tests use a random server port via `EPICS_CAS_SERVER_PORT` (server) mirrored into `EPICS_CA_ADDR_LIST=127.0.0.1:<port>` (client). `OPHYD_CONTROL_LAYER` must NOT be `dummy` in e2e; use `caproto` (pyepics is not installed in this venv).
- **Sim only in CI:** every test path uses David's `simulation=True` driver branches. Hardware branches are written but guarded and excluded from tests (benchmark is a stub, Task 12).
- **Commits:** explicit `git add <paths>` only (never `-A`). Message trailers:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01PFykQo3UJmNXTg3kxLHKxv`
- **Deferred (spec §9):** detectors/frames, PVA, CSM/iocular, autosave/archiver, changes to David's server/GUI, Lightfall migration (spec #3).

## Reference facts (verified against the checkout, 2026-07-12)

- Driver ABC `pystxmcontrol/controller/motor.py`: `motor` with `moveTo(pos)`, `moveBy(step)`, `getPos()`, `getStatus()`, `connect(axis=...)`; concrete drivers also have `stop()` (xpsMotor, E712Motor; derivedPiezo.stop() is a no-op) and `checkLimits(pos)` (raises `SoftwareLimitError` in xpsMotor, returns bool in E712Motor). `moveTo` is BLOCKING sync. Sim mode: `driver.simulation` mirrored from `controller.simulation` in `connect()`.
- Controller instantiation pattern (David's `controller.py:98-155`): controllers keyed by `controllerID`, built as `ControllerClass(address=controllerID, port=port, simulation=sim)` then `.initialize(simulation=sim)`; primary motors `DriverClass()` then `.controller = <controller>`, `setattr(m, "config", entry)`, `.connect(axis=entry["axis"])`. Derived motors: `DriverClass()`, `.axes[axisN] = <already-built motor obj>`, config, `.connect(axis=<motor.json key>)`. DAQs: `DriverClass(address=..., port=..., simulation=...)`, `.meta = entry`, `.start()`.
- `config/motor.json` entries: `type` ("primary"/"derived"), `driver`, `controller`, `controllerID`, `port`, `axis` (or `axes` dict for derived), `minValue`/`maxValue`, `units`, `offset`, `max velocity`, `simulation` (0/1). `config/daq.json`: `default` → keysight53230A, `simulation: true`, `gate: true`, `gate address`.
- keysight53230A: `start()`, `stop()`, `config(dwell, count=1, samples=1, trigger='BUS', output='OFF')`, `async getLine()` → int ndarray len `count*samples`, `async getPoint()` → ndarray shape (1,), sim `getPoint` sleeps `dwell/1000` then Poisson. `meta` dict needs `"gate"` key — use `d.meta.update(entry)` semantics (start() reads `meta["gate"]`, `meta["gate address"]`, `meta["channel"]`).
- shutter: `shutter(address)`, `.connect(simulation=...)`, `.mode` in {"auto","close","open"}, `.setStatus(softGATE=, shutterMASK=)`, `.getStatus()` → bool in sim.
- caproto motor record (venv `caproto/ioc_examples/fake_motor_record.py`, `caproto/server/records/`): `pvproperty(value=0.0, name='', record='motor')`; `fields = instance.field_inst` is a `MotorFields` with `user_readback_value` (.RBV), `done_moving_to_value` (.DMOV), `motor_is_moving` (.MOVN), `stop` (.STOP), `user_high_limit`/`user_low_limit` (.HLM/.LLM), `velocity` (.VELO), `engineering_units` (.EGU); `fields.value_write_hook = async fn(fields, value)` fires on .VAL puts. Server: `from caproto.server import PVGroup, pvproperty, run, ioc_arg_parser`; asyncio backend default.
- The lightfall venv already has: caproto 1.3.0, ophyd 1.11.1, pytest 9.0.2, numpy 2.3.5, bluesky 1.14.6. No pyepics.
- Existing `[project.scripts]` in fork `pyproject.toml` (~line 72): `stxmcontrol`, `stxmserver`. `[project.optional-dependencies]` exists (has `docs`).

## File structure (final)

```
pystxmcontrol/iocs/__init__.py     # guarded caproto import; re-exports nothing heavy
pystxmcontrol/iocs/config.py       # motor.json/daq.json parsing → IOC fleet model + PV naming
pystxmcontrol/iocs/base.py         # MotorRecordGroup + build_driver helpers
pystxmcontrol/iocs/motor_ioc.py    # generic per-controller motor IOC main (incl. co-located derived)
pystxmcontrol/iocs/derived_ioc.py  # CAMotorProxy + cross-controller derived IOC main
pystxmcontrol/iocs/e712_ioc.py     # FlyGroup + E712 IOC main
pystxmcontrol/iocs/daq_ioc.py      # DaqGroup (keysight) + main
pystxmcontrol/iocs/shutter_ioc.py  # ShutterGroup + main
pystxmcontrol/iocs/supervisor.py   # stxm-iocs entry point
pystxmcontrol/iocs/README.md       # usage + PV surface (upstreamable docs)
pystxmcontrol/iocs/benchmark.py    # hardware benchmark stub (Task 12)
tests/iocs/__init__.py, conftest.py, test_config.py, test_motor_record.py,
tests/iocs/test_motor_ioc.py, test_derived.py, test_daq_ioc.py, test_shutter_ioc.py,
tests/iocs/test_e712_fly.py, test_supervisor.py, test_e2e_ophyd.py
pyproject.toml                     # + stxm-iocs script, + iocs extra, + [tool.pytest.ini_options]
```

Run all test commands from the worktree root as:

```bash
cd /c/Users/rp/PycharmProjects/ncs/lightfall-pystxmcontrol/_pystxmcontrol_iocs_wt
PYTHONPATH=$PWD /c/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/iocs -v
```

---

### Task 1: Worktree, package scaffold, packaging metadata

**Files:**
- Create: worktree `_pystxmcontrol_iocs_wt` (branch `feature/caproto-iocs`)
- Create: `pystxmcontrol/iocs/__init__.py`
- Create: `tests/iocs/__init__.py`, `tests/__init__.py` (empty)
- Modify: `pyproject.toml` (`[project.scripts]` + `[project.optional-dependencies]` + pytest config)
- Modify: `C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\.gitignore` (add worktree dir)
- Test: `tests/iocs/test_package.py`

**Interfaces:**
- Produces: importable `pystxmcontrol.iocs` with `require_caproto()` helper used by every later module.

- [ ] **Step 1: Create worktree**

```bash
cd /c/Users/rp/PycharmProjects/ncs/lightfall-pystxmcontrol/_pystxmcontrol_src
git worktree add ../_pystxmcontrol_iocs_wt -b feature/caproto-iocs headless-install-fixes
```

Also append `_pystxmcontrol_iocs_wt/` on its own line to `C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\.gitignore` (the plugin repo must not sweep the worktree; commit that one-line change in the plugin repo separately with message `chore: ignore caproto-iocs worktree`).

All later steps run inside `_pystxmcontrol_iocs_wt`.

- [ ] **Step 2: Write the failing test**

`tests/iocs/test_package.py`:

```python
import subprocess
import sys


def test_iocs_importable():
    import pystxmcontrol.iocs  # noqa: F401


def test_base_package_does_not_import_iocs():
    # importing pystxmcontrol must not pull in caproto or pystxmcontrol.iocs
    code = (
        "import sys, pystxmcontrol, pystxmcontrol.drivers; "
        "assert 'pystxmcontrol.iocs' not in sys.modules, 'iocs leaked into base import'; "
        "assert 'caproto' not in sys.modules, 'caproto leaked into base import'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_require_caproto_returns_module():
    from pystxmcontrol.iocs import require_caproto
    assert require_caproto().__name__ == "caproto"
```

- [ ] **Step 3: Run to verify failure**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_package.py -v` (from worktree root; `$PY` per Global Constraints)
Expected: FAIL / error — `ModuleNotFoundError: No module named 'pystxmcontrol.iocs'` (note: `tests/` and `tests/iocs/` need empty `__init__.py` files first).

- [ ] **Step 4: Implement**

`pystxmcontrol/iocs/__init__.py`:

```python
"""EPICS IOC layer for pystxmcontrol devices (caproto-based).

Leaf subpackage: nothing here is imported by the base pystxmcontrol package.
Install the extra to use it:  pip install pystxmcontrol[iocs]
"""


def require_caproto():
    """Import and return caproto, with an actionable error if missing."""
    try:
        import caproto
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pystxmcontrol.iocs requires caproto. "
            "Install with: pip install pystxmcontrol[iocs]"
        ) from exc
    return caproto
```

`pyproject.toml` edits:

```toml
[project.scripts]
stxmcontrol = "pystxmcontrol.gui.main:main"
stxmserver = "pystxmcontrol.controller.server:main"
stxm-iocs = "pystxmcontrol.iocs.supervisor:main"
```

Add to `[project.optional-dependencies]`:

```toml
iocs = ["caproto>=1.1"]
```

Append at end of `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Note: if `pytest-asyncio` is not installed in the venv, drop the `asyncio_mode` line — the test harness in Task 3 uses threads, not async tests. Check with `$PY -c "import pytest_asyncio"` and only include the line if it imports.

- [ ] **Step 5: Run tests to verify pass**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_package.py -v`
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add pystxmcontrol/iocs/__init__.py tests/__init__.py tests/iocs/__init__.py tests/iocs/test_package.py pyproject.toml
git commit -m "feat(iocs): scaffold pystxmcontrol.iocs leaf subpackage with guarded caproto import"
```

(Include the two trailer lines from Global Constraints in this and every commit.)

---

### Task 2: Config parsing, controller grouping, PV naming (`config.py`)

**Files:**
- Create: `pystxmcontrol/iocs/config.py`
- Test: `tests/iocs/test_config.py`

**Interfaces:**
- Produces (consumed by all IOC mains and supervisor):
  - `sanitize(name: str) -> str` — PV-safe token (alnum + `_`; spaces→`_`).
  - `@dataclass MotorEntry`: `key, entry (raw dict), pv_suffix, prefix` ; `@dataclass ControllerGroup`: `controller_id: str, controller_cls: str, label: str, motors: list[MotorEntry], derived: list[MotorEntry]` ; `@dataclass DerivedRemoteGroup`: `key, entry, prefix, axis_pvs: dict[str,str]` ; `@dataclass DaqGroup_` (name `DaqEntry`): `key, entry, prefix` ; `@dataclass ShutterEntry`: `key, address, prefix, simulation`.
  - `@dataclass FleetConfig`: `station: str, controller_groups: list[ControllerGroup], derived_remote: list[DerivedRemoteGroup], daqs: list[DaqEntry], shutters: list[ShutterEntry], motor_pv: dict[str, str]` (motor.json key → full motor-record PV name, for every motor incl. derived).
  - `load_fleet(motor_json_path: str, daq_json_path: str, station: str = "SIM") -> FleetConfig`.
  - `write_slice(group, fleet, path)` / `read_slice(path) -> dict` — JSON slice files handed to IOC subprocesses (contain `station`, the group's entries verbatim, and `motor_pv` map).

**Naming rules (implement exactly):**
- `label` for a controller group = controller class name minus trailing `"Controller"`, uppercased (`xpsController`→`XPS`, `E712Controller`→`E712`, `bcsController`→`BCS`, `mclController`→`MCL`, `xerController`→`XER`); if several groups share a label (same class, different controllerID), suffix `_2`, `_3`, … in motor.json iteration order.
- Motor PV = `STXM{station}:{label}:{sanitize(key)}` (key = the motor.json top-level key, e.g. `"FineX"`→`FineX`, `"Beamline Energy"`→`Beamline_Energy`).
- Per-entry override: optional `entry["epics"]["pv"]` (full PV name) wins verbatim.
- Derived motors: co-located if every axis in `entry["axes"]` resolves to primaries on ONE controllerID → goes in that `ControllerGroup.derived` with PV under that controller's label. Otherwise → `DerivedRemoteGroup` with prefix `STXM{station}:DERIVED:{sanitize(key)}` and `axis_pvs` mapping axisN → the underlying motor's full PV.
- DAQ PV prefix = `STXM{station}:{sanitize(key).upper()}` (daq.json key `"default"`→`STXMSIM:DEFAULT`). Shutters: one per unique `gate address` among daq entries with `"gate": true`, prefix `STXM{station}:SHUTTER{n}` (n=1..), `simulation` from the daq entry.
- Motors whose `driver` is `epicsMotor` or whose driver class is missing from `pystxmcontrol.drivers` (guarded import) are SKIPPED with a warning list returned on `FleetConfig.skipped: list[tuple[key, reason]]` — the IOC layer must not wrap already-EPICS motors.

- [ ] **Step 1: Write the failing tests**

`tests/iocs/test_config.py` (uses David's real shipped configs — they are the source of truth):

```python
import json
from pathlib import Path

import pytest

from pystxmcontrol.iocs.config import load_fleet, sanitize, write_slice, read_slice

REPO = Path(__file__).resolve().parents[2]
MOTOR_JSON = REPO / "config" / "motor.json"
DAQ_JSON = REPO / "config" / "daq.json"


def test_sanitize():
    assert sanitize("Beamline Energy") == "Beamline_Energy"
    assert sanitize("FineX") == "FineX"
    assert sanitize("XS121 Vert Size") == "XS121_Vert_Size"


@pytest.fixture(scope="module")
def fleet():
    return load_fleet(str(MOTOR_JSON), str(DAQ_JSON), station="SIM")


def test_groups_by_controller_id(fleet):
    ids = {g.controller_id: g for g in fleet.controller_groups}
    # motor.json ships: bcsController@127.0.0.1, xerController@/dev/ttyACM1,
    # mclController@/usr/lib/..., xerController@COM3, xpsController@192.168.1.254
    assert "192.168.1.254" in ids
    xps = ids["192.168.1.254"]
    assert xps.controller_cls == "xpsController"
    assert xps.label == "XPS"
    assert sorted(m.key for m in xps.motors) == ["CoarseX", "CoarseY"]


def test_duplicate_label_disambiguation(fleet):
    xer_labels = sorted(g.label for g in fleet.controller_groups
                        if g.controller_cls == "xerController")
    assert xer_labels == ["XER", "XER_2"]


def test_motor_pv_naming(fleet):
    assert fleet.motor_pv["CoarseX"] == "STXMSIM:XPS:CoarseX"
    assert fleet.motor_pv["FineX"] == "STXMSIM:MCL:FineX"


def test_colocated_derived(fleet):
    # SampleX = derivedPiezo over FineX (mcl) + CoarseX (xps) -> CROSS-controller
    remote_keys = {d.key for d in fleet.derived_remote}
    assert "SampleX" in remote_keys and "SampleY" in remote_keys
    sx = next(d for d in fleet.derived_remote if d.key == "SampleX")
    assert sx.axis_pvs == {"axis1": "STXMSIM:MCL:FineX", "axis2": "STXMSIM:XPS:CoarseX"}
    # Energy = derivedEnergy over Beamline Energy (bcs) + ZonePlateZ (xer) -> also remote
    assert "Energy" in remote_keys


def test_epics_motors_skipped(fleet):
    skipped_keys = {k for k, _ in fleet.skipped}
    assert {"OSA_X", "OSA_Y", "OSA_Z"} <= skipped_keys
    assert "OSA_X" not in fleet.motor_pv


def test_daq_and_shutter(fleet):
    assert fleet.daqs[0].key == "default"
    assert fleet.daqs[0].prefix == "STXMSIM:DEFAULT"
    assert len(fleet.shutters) == 1
    assert fleet.shutters[0].prefix == "STXMSIM:SHUTTER1"
    assert fleet.shutters[0].simulation is True


def test_pv_override(tmp_path):
    cfg = json.loads(MOTOR_JSON.read_text())
    cfg["CoarseX"]["epics"] = {"pv": "BL7011:M1"}
    p = tmp_path / "motor.json"
    p.write_text(json.dumps(cfg))
    fleet = load_fleet(str(p), str(DAQ_JSON), station="SIM")
    assert fleet.motor_pv["CoarseX"] == "BL7011:M1"


def test_slice_roundtrip(tmp_path, fleet):
    g = fleet.controller_groups[0]
    p = tmp_path / "slice.json"
    write_slice(g, fleet, str(p))
    s = read_slice(str(p))
    assert s["station"] == "SIM"
    assert s["kind"] == "controller"
    assert s["controller_id"] == g.controller_id
    assert set(s["motor_pv"]) == set(fleet.motor_pv)
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_config.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'pystxmcontrol.iocs.config'`

- [ ] **Step 3: Implement `pystxmcontrol/iocs/config.py`**

```python
"""Parse David's motor.json/daq.json into an IOC fleet model.

The JSON files remain the single source of truth; this module only READS them
(plus an optional per-entry "epics" sub-dict) and never mutates them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


def sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name.strip())


@dataclass
class MotorEntry:
    key: str
    entry: dict
    pv: str


@dataclass
class ControllerGroup:
    controller_id: str
    controller_cls: str
    label: str
    port: int
    simulation: bool
    motors: list[MotorEntry] = field(default_factory=list)
    derived: list[MotorEntry] = field(default_factory=list)


@dataclass
class DerivedRemoteGroup:
    key: str
    entry: dict
    prefix: str
    axis_pvs: dict[str, str]


@dataclass
class DaqEntry:
    key: str
    entry: dict
    prefix: str


@dataclass
class ShutterEntry:
    key: str
    address: str
    prefix: str
    simulation: bool


@dataclass
class FleetConfig:
    station: str
    controller_groups: list[ControllerGroup]
    derived_remote: list[DerivedRemoteGroup]
    daqs: list[DaqEntry]
    shutters: list[ShutterEntry]
    motor_pv: dict[str, str]
    skipped: list[tuple[str, str]]


def _label_for(cls_name: str) -> str:
    base = cls_name[: -len("Controller")] if cls_name.endswith("Controller") else cls_name
    return sanitize(base).upper()


def _driver_available(driver: str) -> bool:
    import pystxmcontrol.drivers as drv
    return hasattr(drv, driver)


def load_fleet(motor_json_path: str, daq_json_path: str, station: str = "SIM") -> FleetConfig:
    with open(motor_json_path) as f:
        motor_cfg = json.load(f)
    with open(daq_json_path) as f:
        daq_cfg = json.load(f)

    skipped: list[tuple[str, str]] = []
    motor_pv: dict[str, str] = {}
    groups: dict[str, ControllerGroup] = {}
    labels_used: dict[str, int] = {}

    def full_pv(key: str, entry: dict, label: str) -> str:
        override = entry.get("epics", {}).get("pv")
        return override if override else f"STXM{station}:{label}:{sanitize(key)}"

    # --- primaries ---
    for key, entry in motor_cfg.items():
        if entry.get("type") != "primary":
            continue
        driver = entry["driver"]
        if driver == "epicsMotor":
            skipped.append((key, "already an EPICS motor"))
            continue
        if not _driver_available(driver) or not _driver_available(entry["controller"]):
            skipped.append((key, f"driver {driver}/{entry['controller']} unavailable"))
            continue
        cid = entry["controllerID"]
        if cid not in groups:
            cls = entry["controller"]
            base = _label_for(cls)
            n = labels_used.get(base, 0) + 1
            labels_used[base] = n
            label = base if n == 1 else f"{base}_{n}"
            groups[cid] = ControllerGroup(
                controller_id=cid, controller_cls=cls, label=label,
                port=int(entry.get("port", 0)),
                simulation=bool(entry.get("simulation", 1)),
            )
        g = groups[cid]
        pv = full_pv(key, entry, g.label)
        g.motors.append(MotorEntry(key=key, entry=entry, pv=pv))
        motor_pv[key] = pv

    # --- derived ---
    derived_remote: list[DerivedRemoteGroup] = []
    for key, entry in motor_cfg.items():
        if entry.get("type") != "derived":
            continue
        driver = entry["driver"]
        if not _driver_available(driver):
            skipped.append((key, f"driver {driver} unavailable"))
            continue
        axes = entry["axes"]
        underlying = [motor_cfg.get(v) for v in axes.values()]
        if any(u is None for u in underlying) or any(
            axes_key not in motor_pv for axes_key in axes.values()
        ):
            skipped.append((key, "underlying axis missing or skipped"))
            continue
        cids = {u["controllerID"] for u in underlying if u.get("type") == "primary"}
        if len(cids) == 1 and (cid := next(iter(cids))) in groups:
            g = groups[cid]
            pv = full_pv(key, entry, g.label)
            g.derived.append(MotorEntry(key=key, entry=entry, pv=pv))
            motor_pv[key] = pv
        else:
            prefix = entry.get("epics", {}).get("pv") or f"STXM{station}:DERIVED:{sanitize(key)}"
            derived_remote.append(DerivedRemoteGroup(
                key=key, entry=entry, prefix=prefix,
                axis_pvs={ax: motor_pv[mk] for ax, mk in axes.items()},
            ))
            motor_pv[key] = prefix

    # --- daqs + shutters ---
    daqs: list[DaqEntry] = []
    shutters: list[ShutterEntry] = []
    seen_gate: dict[str, ShutterEntry] = {}
    for key, entry in daq_cfg.items():
        prefix = entry.get("epics", {}).get("pv") or f"STXM{station}:{sanitize(key).upper()}"
        daqs.append(DaqEntry(key=key, entry=entry, prefix=prefix))
        if entry.get("gate") and entry.get("gate address") and entry["gate address"] not in seen_gate:
            n = len(seen_gate) + 1
            seen_gate[entry["gate address"]] = ShutterEntry(
                key=f"shutter{n}", address=entry["gate address"],
                prefix=f"STXM{station}:SHUTTER{n}",
                simulation=bool(entry.get("simulation", True)),
            )
    shutters = list(seen_gate.values())

    return FleetConfig(
        station=station,
        controller_groups=list(groups.values()),
        derived_remote=derived_remote,
        daqs=daqs,
        shutters=shutters,
        motor_pv=motor_pv,
        skipped=skipped,
    )


# --- slice files handed to IOC subprocesses (Windows spawn-safe: path arg, not blob) ---

def write_slice(group, fleet: FleetConfig, path: str) -> None:
    if isinstance(group, ControllerGroup):
        payload = {
            "kind": "controller",
            "station": fleet.station,
            "controller_id": group.controller_id,
            "controller_cls": group.controller_cls,
            "label": group.label,
            "port": group.port,
            "simulation": group.simulation,
            "motors": [{"key": m.key, "entry": m.entry, "pv": m.pv} for m in group.motors],
            "derived": [{"key": m.key, "entry": m.entry, "pv": m.pv} for m in group.derived],
            "motor_pv": fleet.motor_pv,
        }
    elif isinstance(group, DerivedRemoteGroup):
        payload = {
            "kind": "derived_remote",
            "station": fleet.station,
            "key": group.key,
            "entry": group.entry,
            "prefix": group.prefix,
            "axis_pvs": group.axis_pvs,
            "motor_pv": fleet.motor_pv,
        }
    elif isinstance(group, DaqEntry):
        payload = {"kind": "daq", "station": fleet.station, "key": group.key,
                   "entry": group.entry, "prefix": group.prefix, "motor_pv": fleet.motor_pv}
    elif isinstance(group, ShutterEntry):
        payload = {"kind": "shutter", "station": fleet.station, "key": group.key,
                   "address": group.address, "prefix": group.prefix,
                   "simulation": group.simulation, "motor_pv": fleet.motor_pv}
    else:  # pragma: no cover
        raise TypeError(f"unknown group type {type(group)!r}")
    with open(path, "w") as f:
        json.dump(payload, f, indent=1)


def read_slice(path: str) -> dict:
    with open(path) as f:
        return json.load(f)
```

- [ ] **Step 4: Run tests, iterate until green**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_config.py -v`
Expected: all PASS. Note `test_colocated_derived` asserts SampleX is CROSS-controller with David's shipped config (FineX is mcl, CoarseX is xps) — a co-located case is exercised in Task 5 with a synthetic config.

- [ ] **Step 5: Commit**

```bash
git add pystxmcontrol/iocs/config.py tests/iocs/test_config.py
git commit -m "feat(iocs): fleet config model - motor.json/daq.json parsing, grouping, PV naming"
```

---

### Task 3: `MotorRecordGroup` + in-process IOC test harness (`base.py`, `conftest.py`)

**Files:**
- Create: `pystxmcontrol/iocs/base.py`
- Create: `tests/iocs/conftest.py`
- Test: `tests/iocs/test_motor_record.py`

**Interfaces:**
- Produces:
  - `base.build_controller(slice_or_group: dict) -> object` — instantiate + `initialize(simulation=...)` a controller class by name from `pystxmcontrol.drivers`.
  - `base.build_motor(driver_cls_name: str, controller, entry: dict, axis) -> object` — David's exact wiring: `cls()`, `.controller=`, `setattr(m,'config',entry)`, `.connect(axis=...)`, then `m.offset/units` from config.
  - `class base.MotorRecordGroup(PVGroup)` — ctor `MotorRecordGroup(prefix, driver=<motor obj>, motor_config=<entry dict>, idle_poll=0.1, moving_poll=0.02)`; PV surface: `<prefix>` (.VAL via `name=''`), fields `.RBV/.DMOV/.MOVN/.STOP/.HLM/.LLM/.EGU/.VELO`. Limits enforced IOC-side from the live HLM/LLM field values (seeded from `minValue`/`maxValue`); out-of-limits put raises → CA write error, no motion. `.STOP` put calls `driver.stop()` (if the driver has one) and cancels the pending move. `.VELO` put calls `driver.setAxisParams(velocity=value)` when available.
  - `conftest.run_ioc(pvdb) -> (ctx_factory, port)` fixture: runs a caproto asyncio server on a random port in a daemon thread; yields a `caproto.threading.client.Context` configured for `127.0.0.1:<port>`; used by ALL IOC tests.

**Design notes (follow the venv example `caproto/ioc_examples/fake_motor_record.py`):**
- `motor = pvproperty(value=0.0, name='', record='motor', precision=3)`. Access fields via `self.motor.field_inst`.
- Move execution: `fields.value_write_hook` fires on .VAL put. The hook validates limits (raise `ValueError` on violation — caproto propagates a write failure to the client) and pushes the target onto an `asyncio.Queue`. A `@motor.startup` coroutine consumes the queue: write `DMOV=0, MOVN=1`, run the blocking `driver.moveTo(target)` in a thread (`loop.run_in_executor`), and while the executor future is pending poll `driver.getPos()` every `moving_poll` seconds into `.RBV`; on completion write final RBV, `MOVN=0, DMOV=1`. When idle, poll RBV every `idle_poll` seconds.
- David's sim `moveTo` returns instantly; DMOV-transition tests use the `SlowSimMotor` test double below.
- `SoftwareLimitError` from `driver.checkLimits` inside `moveTo` (xpsMotor raises it) must be caught in the executor wrapper → recorded, `MOVN=0/DMOV=1`, RBV refreshed (belt-and-braces: our own HLM/LLM check runs first).

- [ ] **Step 1: Write conftest harness**

`tests/iocs/conftest.py`:

```python
"""Shared IOC test harness: run a caproto asyncio server in a thread on a random port."""
import asyncio
import os
import random
import socket
import threading
import time

import pytest
from caproto.threading.client import Context


def _free_udp_port() -> int:
    for _ in range(50):
        port = random.randint(40000, 60000)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free port found")


class IocHarness:
    def __init__(self):
        self.port = _free_udp_port()
        self._loop = None
        self._thread = None
        self._started = threading.Event()

    def start(self, pvdb: dict):
        os.environ["EPICS_CA_ADDR_LIST"] = f"127.0.0.1:{self.port}"
        os.environ["EPICS_CA_AUTO_ADDR_LIST"] = "NO"
        os.environ["EPICS_CAS_SERVER_PORT"] = str(self.port)

        def runner():
            from caproto.asyncio.server import start_server
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            async def main():
                self._started.set()
                await start_server(pvdb)

            try:
                self._loop.run_until_complete(main())
            except asyncio.CancelledError:
                pass

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()
        assert self._started.wait(10), "IOC server thread failed to start"
        time.sleep(0.5)  # let the server bind before clients connect
        return self

    def client(self) -> Context:
        return Context()

    def call_soon(self, coro):
        """Schedule a coroutine on the IOC loop (e.g. server-side writes)."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)


@pytest.fixture
def ioc_harness():
    h = IocHarness()
    yield h
    # daemon thread; loop dies with the process. Stop the loop politely:
    if h._loop is not None:
        h._loop.call_soon_threadsafe(h._loop.stop)


@pytest.fixture
def slow_sim_motor():
    """xpsMotor in sim mode with an artificial per-move duration, for DMOV tests."""
    from pystxmcontrol.drivers.xpsMotor import xpsMotor

    class SlowSimController:
        simulation = True
        moving = False

    class SlowSimMotor(xpsMotor):
        move_duration = 0.5

        def moveTo(self, pos):
            if self.checkLimits(pos):
                deadline = time.time() + self.move_duration
                self._stop_requested = False
                start = self._controller_position
                while time.time() < deadline:
                    if getattr(self, "_stop_requested", False):
                        return
                    frac = 1 - (deadline - time.time()) / self.move_duration
                    self._controller_position = start + frac * (pos - start)
                    time.sleep(0.02)
                self._controller_position = pos

        def stop(self):
            self._stop_requested = True

    m = SlowSimMotor()
    m.controller = SlowSimController()
    m.config = {"units": 1, "offset": 0, "minValue": -40, "maxValue": 40,
                "max velocity": 1000.0, "simulation": 1}
    m.simulation = True
    return m
```

Note for the implementer: verify `caproto.asyncio.server.start_server`'s exact signature in the venv (`grep -n "async def start_server" .venv/Lib/site-packages/caproto/asyncio/server.py` in the lightfall venv) — if it takes `(pvdb, *, interfaces=...)` pass `interfaces=["127.0.0.1"]`.

- [ ] **Step 2: Write the failing tests**

`tests/iocs/test_motor_record.py`:

```python
import time

import pytest


def _make_group(driver):
    from pystxmcontrol.iocs.base import MotorRecordGroup
    return MotorRecordGroup("TEST:M1", driver=driver,
                            motor_config=driver.config,
                            idle_poll=0.05, moving_poll=0.01)


@pytest.fixture
def motor_ioc(ioc_harness, slow_sim_motor):
    group = _make_group(slow_sim_motor)
    ioc_harness.start(group.pvdb)
    ctx = ioc_harness.client()
    (val,) = ctx.get_pvs("TEST:M1", timeout=10)
    val.wait_for_connection(timeout=10)
    return ioc_harness, ctx, slow_sim_motor


def test_move_and_readback(motor_ioc):
    h, ctx, drv = motor_ioc
    val, rbv, dmov = ctx.get_pvs("TEST:M1", "TEST:M1.RBV", "TEST:M1.DMOV")
    val.write(5.0, wait=True, timeout=15)
    deadline = time.time() + 5
    while time.time() < deadline and dmov.read().data[0] != 1:
        time.sleep(0.05)
    assert dmov.read().data[0] == 1
    assert abs(rbv.read().data[0] - 5.0) < 1e-6
    assert abs(drv.getPos() - 5.0) < 1e-6


def test_dmov_transitions_during_move(motor_ioc):
    h, ctx, drv = motor_ioc
    val, dmov, movn = ctx.get_pvs("TEST:M1", "TEST:M1.DMOV", "TEST:M1.MOVN")
    val.write(10.0, wait=False)
    time.sleep(0.15)  # mid-move (move_duration=0.5)
    assert movn.read().data[0] == 1
    assert dmov.read().data[0] == 0
    deadline = time.time() + 5
    while time.time() < deadline and dmov.read().data[0] != 1:
        time.sleep(0.05)
    assert dmov.read().data[0] == 1
    assert movn.read().data[0] == 0


def test_limits_enforced(motor_ioc):
    h, ctx, drv = motor_ioc
    val, rbv, hlm, llm = ctx.get_pvs("TEST:M1", "TEST:M1.RBV", "TEST:M1.HLM", "TEST:M1.LLM")
    assert hlm.read().data[0] == 40.0 and llm.read().data[0] == -40.0
    before = rbv.read().data[0]
    with pytest.raises(Exception):
        val.write(41.0, wait=True, timeout=10)
    time.sleep(0.3)
    assert abs(rbv.read().data[0] - before) < 1e-6  # no motion happened


def test_stop_mid_move(motor_ioc):
    h, ctx, drv = motor_ioc
    val, stop, dmov, rbv = ctx.get_pvs("TEST:M1", "TEST:M1.STOP", "TEST:M1.DMOV", "TEST:M1.RBV")
    val.write(20.0, wait=False)
    time.sleep(0.15)
    stop.write(1, wait=True, timeout=10)
    deadline = time.time() + 5
    while time.time() < deadline and dmov.read().data[0] != 1:
        time.sleep(0.05)
    assert dmov.read().data[0] == 1
    final = rbv.read().data[0]
    assert final < 19.0  # stopped short of the 20.0 target
    time.sleep(0.3)
    assert abs(rbv.read().data[0] - final) < 0.5  # and stayed put


def test_egu_and_velo(motor_ioc):
    h, ctx, drv = motor_ioc
    egu, velo = ctx.get_pvs("TEST:M1.EGU", "TEST:M1.VELO")
    assert egu.read(data_type="native").data[0].decode() == "um"
    assert velo.read().data[0] == 1000.0
```

- [ ] **Step 3: Run to verify failure**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_motor_record.py -v`
Expected: import error — `No module named 'pystxmcontrol.iocs.base'`

- [ ] **Step 4: Implement `pystxmcontrol/iocs/base.py`**

```python
"""Driver-backed caproto motor record + driver construction helpers."""
from __future__ import annotations

import asyncio
import functools

from caproto.server import PVGroup, pvproperty

from pystxmcontrol.controller.motor import SoftwareLimitError


def build_controller(controller_cls: str, controller_id: str, port: int, simulation: bool):
    """David's controller wiring (controller.py addController), without eval."""
    import pystxmcontrol.drivers as drv
    cls = getattr(drv, controller_cls)
    ctrl = cls(address=controller_id, port=int(port), simulation=int(simulation))
    ctrl.initialize(simulation=bool(simulation))
    return ctrl


def build_motor(driver_cls: str, controller, entry: dict, axis):
    """David's motor wiring (controller.py initialize), without eval."""
    import pystxmcontrol.drivers as drv
    m = getattr(drv, driver_cls)()
    m.controller = controller
    setattr(m, "config", entry)
    m.connect(axis=axis)
    m.offset = entry["offset"]
    m.units = entry["units"]
    return m


class MotorRecordGroup(PVGroup):
    """caproto record='motor' facade over a pystxmcontrol motor driver.

    .VAL put -> limit check (HLM/LLM, IOC-side) -> blocking driver.moveTo in a
    worker thread; .RBV polled from driver.getPos() (idle_poll s idle,
    moving_poll s while moving); .STOP -> driver.stop(); .VELO -> setAxisParams.
    """

    motor = pvproperty(value=0.0, name="", record="motor", precision=3)

    def __init__(self, prefix, *, driver, motor_config,
                 idle_poll=0.1, moving_poll=0.02, **kwargs):
        super().__init__(prefix, **kwargs)
        self._driver = driver
        self._motor_config = motor_config
        self._idle_poll = idle_poll
        self._moving_poll = moving_poll
        self._move_queue: asyncio.Queue = asyncio.Queue()

    @motor.startup
    async def motor(self, instance, async_lib):
        fields = instance.field_inst
        cfg = self._motor_config
        await fields.user_low_limit.write(float(cfg.get("minValue", -1e12)))
        await fields.user_high_limit.write(float(cfg.get("maxValue", 1e12)))
        await fields.velocity.write(float(cfg.get("max velocity", 0.0)))
        await fields.engineering_units.write(
            cfg.get("epics", {}).get("egu", "um"))
        await fields.done_moving_to_value.write(1)

        async def value_write_hook(fields_, value):
            lo = fields.user_low_limit.value
            hi = fields.user_high_limit.value
            if not (lo <= value <= hi):
                raise ValueError(
                    f"{self.prefix}: {value} outside limits [{lo}, {hi}]")
            await self._move_queue.put(value)

        fields.value_write_hook = value_write_hook

        loop = asyncio.get_running_loop()
        pos = await loop.run_in_executor(None, self._driver.getPos)
        await fields.user_readback_value.write(pos)

        while True:
            try:
                target = await asyncio.wait_for(
                    self._move_queue.get(), timeout=self._idle_poll)
            except asyncio.TimeoutError:
                pos = await loop.run_in_executor(None, self._driver.getPos)
                await fields.user_readback_value.write(pos)
                continue

            await fields.done_moving_to_value.write(0)
            await fields.motor_is_moving.write(1)
            move_future = loop.run_in_executor(
                None, self._guarded_move_to, target)
            while not move_future.done():
                pos = await loop.run_in_executor(None, self._driver.getPos)
                await fields.user_readback_value.write(pos)
                await async_lib.library.sleep(self._moving_poll)
            move_future.result()  # re-raise unexpected errors (limit errors swallowed)
            pos = await loop.run_in_executor(None, self._driver.getPos)
            await fields.user_readback_value.write(pos)
            await fields.motor_is_moving.write(0)
            await fields.done_moving_to_value.write(1)

    def _guarded_move_to(self, target):
        try:
            self._driver.moveTo(target)
        except SoftwareLimitError:
            pass  # belt-and-braces; the hook's HLM/LLM check runs first

    @motor.fields.stop.putter
    async def motor(self, instance, value):  # noqa: F811
        group = instance.group.group  # MotorFields -> record group -> MotorRecordGroup
        if value and hasattr(group._driver, "stop"):
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, group._driver.stop)
        return value

    @motor.fields.velocity.putter
    async def motor(self, instance, value):  # noqa: F811
        group = instance.group.group
        if hasattr(group._driver, "setAxisParams"):
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, functools.partial(group._driver.setAxisParams, velocity=value))
        return value
```

**Implementer caution (expected iteration points):**
- The `@motor.fields.stop.putter` decoration form for record fields may differ in caproto 1.3; the authoritative reference is the installed source: `caproto/server/records/base.py` (`MotorFields`) and any ioc_example overriding a record field putter. If field putters can't be attached this way, fall back to watching `fields.stop.value` inside the poll loop (write 0 back after acting) — the fake_motor example uses exactly that pattern, and the tests only require STOP-by-put to halt the move.
- `instance.group` navigation (`MotorFields` → parent group) should be verified with a quick REPL: `grep -n "self.group" caproto/server/records/base.py`. Adjust `_guarded` access accordingly (e.g. keep a module-level weakref registry `prefix -> MotorRecordGroup` if navigation is awkward).
- `pvproperty.fields` startup/putter composition: if `@motor.startup` on a record pvproperty misbehaves, use a separate dummy `pvproperty` (e.g. `_poller = pvproperty(value=0, name=':_POLL', read_only=True)`) to host the startup loop. PV surface asserted by tests is the contract; internal wiring may adapt.

- [ ] **Step 5: Run tests, iterate until green**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_motor_record.py -v`
Expected: 5 PASS. Iterate on the caution points above — do not weaken the tests.

- [ ] **Step 6: Run the whole suite, commit**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs -v` → all green.

```bash
git add pystxmcontrol/iocs/base.py tests/iocs/conftest.py tests/iocs/test_motor_record.py
git commit -m "feat(iocs): MotorRecordGroup - driver-backed caproto motor record with IOC-side limits"
```

---

### Task 4: Generic per-controller motor IOC (`motor_ioc.py`)

**Files:**
- Create: `pystxmcontrol/iocs/motor_ioc.py`
- Test: `tests/iocs/test_motor_ioc.py`

**Interfaces:**
- Consumes: `config.read_slice`, `base.build_controller/build_motor/MotorRecordGroup`.
- Produces:
  - `build_pvdb_from_slice(slice_dict: dict) -> dict` — one controller instance, one `MotorRecordGroup` per primary in the slice, co-located derived per Task 5 (this task: primaries only; Task 5 extends the same function).
  - CLI: `$PY -m pystxmcontrol.iocs.motor_ioc --slice <path> [--quiet]` → runs `caproto.server.run(pvdb)` (asyncio). This exact invocation is what the supervisor spawns (Windows spawn-safe).
  - `spawn_ioc(module: str, slice_path: str, port: int) -> subprocess.Popen` helper in `tests/iocs/conftest.py` (added here, reused by every subprocess test): spawns with env `EPICS_CAS_SERVER_PORT=<port>`, `EPICS_CA_ADDR_LIST=127.0.0.1:<port>`, `EPICS_CA_AUTO_ADDR_LIST=NO`, `PYTHONPATH=<worktree root>`.

- [ ] **Step 1: Write the failing test**

`tests/iocs/test_motor_ioc.py`:

```python
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from pystxmcontrol.iocs.config import load_fleet, write_slice

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def xps_slice(tmp_path):
    fleet = load_fleet(str(REPO / "config" / "motor.json"),
                       str(REPO / "config" / "daq.json"), station="SIM")
    xps = next(g for g in fleet.controller_groups if g.label == "XPS")
    p = tmp_path / "xps.json"
    write_slice(xps, fleet, str(p))
    return str(p)


def test_build_pvdb_from_slice(xps_slice):
    from pystxmcontrol.iocs.motor_ioc import build_pvdb_from_slice
    pvdb = build_pvdb_from_slice(json.load(open(xps_slice)))
    assert "STXMSIM:XPS:CoarseX" in pvdb
    assert "STXMSIM:XPS:CoarseY" in pvdb
    assert "STXMSIM:XPS:CoarseX.RBV" in pvdb


def test_motor_ioc_subprocess(xps_slice, free_port, spawn_ioc):
    proc = spawn_ioc("pystxmcontrol.iocs.motor_ioc", xps_slice, free_port)
    try:
        from caproto.threading.client import Context
        ctx = Context()
        (val, rbv) = ctx.get_pvs("STXMSIM:XPS:CoarseX", "STXMSIM:XPS:CoarseX.RBV",
                                 timeout=20)
        val.wait_for_connection(timeout=20)
        val.write(3.0, wait=True, timeout=20)
        deadline = time.time() + 10
        while time.time() < deadline and abs(rbv.read().data[0] - 3.0) > 1e-6:
            time.sleep(0.1)
        assert abs(rbv.read().data[0] - 3.0) < 1e-6
    finally:
        proc.terminate()
        proc.wait(timeout=10)
```

Add to `tests/iocs/conftest.py`:

```python
@pytest.fixture
def free_port(monkeypatch):
    port = _free_udp_port()
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", f"127.0.0.1:{port}")
    monkeypatch.setenv("EPICS_CA_AUTO_ADDR_LIST", "NO")
    monkeypatch.setenv("EPICS_CAS_SERVER_PORT", str(port))
    return port


@pytest.fixture
def spawn_ioc():
    import os
    import subprocess
    import sys
    from pathlib import Path
    procs = []

    def _spawn(module: str, slice_path: str, port: int):
        env = dict(os.environ)
        env.update({
            "EPICS_CAS_SERVER_PORT": str(port),
            "EPICS_CA_ADDR_LIST": f"127.0.0.1:{port}",
            "EPICS_CA_AUTO_ADDR_LIST": "NO",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        })
        p = subprocess.Popen([sys.executable, "-m", module, "--slice", slice_path],
                             env=env)
        procs.append(p)
        time.sleep(3.0)  # IOC startup (driver connect + server bind)
        assert p.poll() is None, f"{module} exited early with {p.returncode}"
        return p

    yield _spawn
    for p in procs:
        if p.poll() is None:
            p.terminate()
            p.wait(timeout=10)
```

(also `import time` at top of conftest if not present)

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_motor_ioc.py -v`
Expected: `No module named 'pystxmcontrol.iocs.motor_ioc'`

- [ ] **Step 3: Implement `pystxmcontrol/iocs/motor_ioc.py`**

```python
"""Generic per-controller motor IOC.

Usage (spawned by the supervisor, or standalone):
    python -m pystxmcontrol.iocs.motor_ioc --slice /path/to/slice.json
"""
from __future__ import annotations

import argparse
import json

from pystxmcontrol.iocs import require_caproto

require_caproto()

from caproto.server import run  # noqa: E402

from pystxmcontrol.iocs.base import (  # noqa: E402
    MotorRecordGroup, build_controller, build_motor)
from pystxmcontrol.iocs.config import read_slice  # noqa: E402


def build_pvdb_from_slice(s: dict) -> dict:
    assert s["kind"] == "controller", s["kind"]
    controller = build_controller(
        s["controller_cls"], s["controller_id"], s["port"], s["simulation"])
    pvdb: dict = {}
    motors_by_key: dict = {}
    for m in s["motors"]:
        drv = build_motor(m["entry"]["driver"], controller,
                          m["entry"], m["entry"]["axis"])
        motors_by_key[m["key"]] = drv
        group = MotorRecordGroup(m["pv"], driver=drv, motor_config=m["entry"])
        pvdb.update(group.pvdb)
    # co-located derived motors are wired in Task 5 (build_derived_colocated)
    from pystxmcontrol.iocs.derived_ioc import build_derived_colocated
    pvdb.update(build_derived_colocated(s, motors_by_key))
    return pvdb


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", required=True)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    pvdb = build_pvdb_from_slice(read_slice(args.slice))
    run(pvdb, log_pv_names=not args.quiet)


if __name__ == "__main__":
    main()
```

For THIS task, make `build_derived_colocated` a stub so motor_ioc works before Task 5 — create `pystxmcontrol/iocs/derived_ioc.py` containing only:

```python
"""Derived-motor IOC support (fleshed out in Task 5)."""
from __future__ import annotations


def build_derived_colocated(slice_dict: dict, motors_by_key: dict) -> dict:
    return {}
```

- [ ] **Step 4: Run tests until green**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_motor_ioc.py -v` → 2 PASS.
Also rerun: `PYTHONPATH=$PWD $PY -m pytest tests/iocs -v` → all green.

- [ ] **Step 5: Commit**

```bash
git add pystxmcontrol/iocs/motor_ioc.py pystxmcontrol/iocs/derived_ioc.py tests/iocs/test_motor_ioc.py tests/iocs/conftest.py
git commit -m "feat(iocs): generic per-controller motor IOC with slice-file CLI"
```

---

### Task 5: Derived motors (`derived_ioc.py`) — co-located + cross-controller

**Files:**
- Modify: `pystxmcontrol/iocs/derived_ioc.py` (replace stub)
- Test: `tests/iocs/test_derived.py`

**Interfaces:**
- Consumes: `base.MotorRecordGroup`, `base.build_motor`, `config.read_slice`.
- Produces:
  - `build_derived_colocated(slice_dict, motors_by_key: dict[str, motor]) -> dict` — for each entry in `slice_dict["derived"]`: instantiate `DriverClass()`, wire `.axes[axisN] = motors_by_key[<underlying key>]`, `setattr(m,'config',entry)`, `m.connect(axis=<key>)`, offset/units — then wrap in `MotorRecordGroup(pv, driver=m, motor_config=entry)` and merge pvdbs.
  - `class CAMotorProxy` — duck-types David's `motor` interface over CA (caproto threading client): ctor `CAMotorProxy(pv: str, ctx: Context, axis_label: str = "x")`; methods `moveTo(pos)` (put with wait=True), `getPos()` (.RBV get), `getStatus()` (.MOVN != 0), `stop()` (.STOP put 1), `checkLimits(pos)` (against cached .HLM/.LLM), `setAxisParams(velocity=...)` (.VELO put); attrs `axis` (=axis_label), `config` dict (`minValue`/`maxValue` from .LLM/.HLM, `offset` 0.0, `units` 1.0, `maxScanRange` from limits span, `max velocity` from .VELO), `simulation=False`, and `controller` = a `_ProxyController` stub with `getAxis(name)->1`, `simulation=False`, `lock` (a `threading.Lock`) — enough for `derivedPiezo.connect` / `derivedEnergy.connect` attribute walks.
  - CLI: `$PY -m pystxmcontrol.iocs.derived_ioc --slice <path>` for `kind == "derived_remote"` slices: builds proxies for `axis_pvs`, wires the derived driver exactly like David does, wraps in `MotorRecordGroup`, runs the server.

**Key subtlety:** the derived drivers call `self.axes["axis1"].controller...` and read `self.axes[...].config[...]` during `connect()` and moves. The proxy must present those attributes; anything not listed above may raise `AttributeError` loudly (better to fail loudly than silently no-op hardware math). `entry["simulation"]` drives the derived driver's own sim branch (`derivedPiezo.connect` reads `self.config["simulation"]`) — for the CA-composed case, `simulation` in the derived entry must be 0/false so moves go through the proxies to the real (sim-backed) motor IOCs; document this in README (Task 11).

- [ ] **Step 1: Write the failing tests**

`tests/iocs/test_derived.py`:

```python
import json
import time
from pathlib import Path

import pytest

from pystxmcontrol.iocs.config import load_fleet, write_slice

REPO = Path(__file__).resolve().parents[2]


def _synthetic_colocated_config(tmp_path):
    """FineQ + CoarseQ both on ONE xpsController + a derivedPiezo over them."""
    base = json.loads((REPO / "config" / "motor.json").read_text())
    fine = dict(base["CoarseX"]);  fine.update({"axis": "x"})
    coarse = dict(base["CoarseY"]); coarse.update({"axis": "y"})
    cfg = {
        "FineQ": fine,
        "CoarseQ": coarse,
        "SampleQ": {
            "type": "derived",
            "axes": {"axis1": "FineQ", "axis2": "CoarseQ"},
            "driver": "derivedPiezo",
            "reset_after_move": False,
            "max velocity": 1000.0,
            "minValue": -5000.0, "maxValue": 5000.0,
            "offset": 0.0, "units": 1.0,
            "simulation": 1,
        },
    }
    p = tmp_path / "motor.json"
    p.write_text(json.dumps(cfg))
    return p


def test_colocated_derived_in_process(tmp_path, ioc_harness):
    mp = _synthetic_colocated_config(tmp_path)
    fleet = load_fleet(str(mp), str(REPO / "config" / "daq.json"), station="SIM")
    assert not fleet.derived_remote  # all on one controller -> co-located
    g = fleet.controller_groups[0]
    assert [d.key for d in g.derived] == ["SampleQ"]

    sp = tmp_path / "slice.json"
    write_slice(g, fleet, str(sp))
    from pystxmcontrol.iocs.motor_ioc import build_pvdb_from_slice
    pvdb = build_pvdb_from_slice(json.load(open(sp)))
    assert "STXMSIM:XPS:SampleQ" in pvdb

    ioc_harness.start(pvdb)
    ctx = ioc_harness.client()
    val, rbv = ctx.get_pvs("STXMSIM:XPS:SampleQ", "STXMSIM:XPS:SampleQ.RBV")
    val.wait_for_connection(timeout=10)
    val.write(7.5, wait=True, timeout=15)
    deadline = time.time() + 5
    while time.time() < deadline and abs(rbv.read().data[0] - 7.5) > 1e-3:
        time.sleep(0.05)
    assert abs(rbv.read().data[0] - 7.5) < 1e-3


def test_ca_motor_proxy_against_live_ioc(ioc_harness, slow_sim_motor):
    from pystxmcontrol.iocs.base import MotorRecordGroup
    group = MotorRecordGroup("PROXY:M1", driver=slow_sim_motor,
                             motor_config=slow_sim_motor.config,
                             idle_poll=0.05, moving_poll=0.01)
    ioc_harness.start(group.pvdb)

    from pystxmcontrol.iocs.derived_ioc import CAMotorProxy
    ctx = ioc_harness.client()
    proxy = CAMotorProxy("PROXY:M1", ctx, axis_label="x")
    assert proxy.checkLimits(0.0) is True
    assert proxy.checkLimits(100.0) is False
    proxy.moveTo(4.0)
    assert abs(proxy.getPos() - 4.0) < 1e-3
    assert proxy.getStatus() is False
    assert proxy.config["minValue"] == -40.0
    assert proxy.config["maxValue"] == 40.0
    assert proxy.controller.getAxis("x") == 1


def test_cross_controller_derived_ioc_subprocess(tmp_path, free_port, spawn_ioc):
    """Full chain: 1 motor IOC (2 axes on distinct controllers is overkill —
    reuse one controller IOC) + derived_remote IOC composing over CA."""
    base = json.loads((REPO / "config" / "motor.json").read_text())
    fine = dict(base["CoarseX"]); fine.update({"axis": "x"})
    # second physical controller: same class, different controllerID
    coarse = dict(base["CoarseY"]); coarse.update({"axis": "y", "controllerID": "192.168.1.253"})
    cfg = {
        "FineQ": fine, "CoarseQ": coarse,
        "SampleQ": {
            "type": "derived",
            "axes": {"axis1": "FineQ", "axis2": "CoarseQ"},
            "driver": "derivedPiezo", "reset_after_move": False,
            "max velocity": 1000.0, "minValue": -5000.0, "maxValue": 5000.0,
            "offset": 0.0, "units": 1.0, "simulation": 0,
        },
    }
    mp = tmp_path / "motor.json"
    mp.write_text(json.dumps(cfg))
    fleet = load_fleet(str(mp), str(REPO / "config" / "daq.json"), station="SIM")
    assert [d.key for d in fleet.derived_remote] == ["SampleQ"]

    slices = {}
    for g in fleet.controller_groups:
        p = tmp_path / f"{g.label}.json"
        write_slice(g, fleet, str(p))
        slices[g.label] = str(p)
    dp = tmp_path / "derived.json"
    write_slice(fleet.derived_remote[0], fleet, str(dp))

    for label in slices:
        spawn_ioc("pystxmcontrol.iocs.motor_ioc", slices[label], free_port)
    spawn_ioc("pystxmcontrol.iocs.derived_ioc", str(dp), free_port)

    from caproto.threading.client import Context
    ctx = Context()
    pv_name = fleet.motor_pv["SampleQ"]
    val, rbv = ctx.get_pvs(pv_name, pv_name + ".RBV", timeout=30)
    val.wait_for_connection(timeout=30)
    val.write(2.5, wait=True, timeout=30)
    deadline = time.time() + 15
    while time.time() < deadline and abs(rbv.read().data[0] - 2.5) > 1e-3:
        time.sleep(0.1)
    assert abs(rbv.read().data[0] - 2.5) < 1e-3
```

Note: multiple IOC subprocesses sharing one `EPICS_CAS_SERVER_PORT` will conflict. `spawn_ioc` must therefore allocate a DISTINCT server port per spawned IOC while the CLIENT env (`EPICS_CA_ADDR_LIST`) lists all of them. **Amend `spawn_ioc`** to: allocate a fresh port per call, append `127.0.0.1:<port>` to an accumulated address list stored on the fixture, and set the client's `EPICS_CA_ADDR_LIST` (both `os.environ` for in-test Contexts and each child's env) to the space-separated accumulated list. The derived IOC subprocess is itself a CA client of the motor IOCs, so its env must carry the full list too.

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_derived.py -v`
Expected: FAIL — `build_derived_colocated` returns `{}` (first test asserts the PV exists), `CAMotorProxy` missing.

- [ ] **Step 3: Implement `pystxmcontrol/iocs/derived_ioc.py`** (replace stub)

```python
"""Derived-motor IOC support.

Co-located: derived driver composed IN-PROCESS inside the owning controller's
IOC (David's exact wiring). Cross-controller: this module's CLI runs a small
IOC whose derived driver composes the underlying axes VIA CA (CAMotorProxy),
so composition and physical IOCs restart independently.
"""
from __future__ import annotations

import argparse
import threading

from pystxmcontrol.iocs import require_caproto

require_caproto()


def build_derived_colocated(slice_dict: dict, motors_by_key: dict) -> dict:
    import pystxmcontrol.drivers as drv
    from pystxmcontrol.iocs.base import MotorRecordGroup

    pvdb: dict = {}
    for d in slice_dict.get("derived", []):
        entry = d["entry"]
        m = getattr(drv, entry["driver"])()
        for ax, underlying_key in entry["axes"].items():
            m.axes[ax] = motors_by_key[underlying_key]
        setattr(m, "config", entry)
        m.connect(axis=d["key"])
        m.offset = entry["offset"]
        m.units = entry["units"]
        motors_by_key[d["key"]] = m
        group = MotorRecordGroup(d["pv"], driver=m, motor_config=entry)
        pvdb.update(group.pvdb)
    return pvdb


class _ProxyController:
    """Minimal controller stand-in for CA-proxied axes."""
    simulation = False

    def __init__(self):
        self.lock = threading.Lock()

    def getAxis(self, name):
        return 1


class CAMotorProxy:
    """pystxmcontrol motor-interface facade over a live EPICS motor record."""

    def __init__(self, pv: str, ctx, axis_label: str = "x"):
        self._pvs = dict(zip(
            ("val", "rbv", "movn", "stop", "hlm", "llm", "velo"),
            ctx.get_pvs(pv, pv + ".RBV", pv + ".MOVN", pv + ".STOP",
                        pv + ".HLM", pv + ".LLM", pv + ".VELO", timeout=30),
        ))
        self._pvs["val"].wait_for_connection(timeout=30)
        self.axis = axis_label
        self.simulation = False
        self.controller = _ProxyController()
        hlm = float(self._pvs["hlm"].read().data[0])
        llm = float(self._pvs["llm"].read().data[0])
        velo = float(self._pvs["velo"].read().data[0])
        self.config = {
            "minValue": llm, "maxValue": hlm, "offset": 0.0, "units": 1.0,
            "maxScanRange": hlm - llm, "max velocity": velo, "simulation": 0,
        }
        self.offset = 0.0
        self.units = 1.0
        self.moving = False

    def moveTo(self, pos, **kwargs):
        self._pvs["val"].write(float(pos), wait=True, timeout=120)

    def moveBy(self, step, **kwargs):
        self.moveTo(self.getPos() + step)

    def getPos(self, **kwargs):
        return float(self._pvs["rbv"].read().data[0])

    def getStatus(self, **kwargs):
        return bool(self._pvs["movn"].read().data[0])

    def stop(self):
        self._pvs["stop"].write(1, wait=True, timeout=10)

    def checkLimits(self, pos):
        return self.config["minValue"] <= pos <= self.config["maxValue"]

    def setAxisParams(self, velocity=None, **kwargs):
        if velocity is not None:
            self._pvs["velo"].write(float(velocity), wait=True, timeout=10)

    def connect(self, axis=None, **kwargs):
        return True


def build_pvdb_from_slice(s: dict) -> dict:
    assert s["kind"] == "derived_remote", s["kind"]
    import pystxmcontrol.drivers as drv
    from caproto.threading.client import Context
    from pystxmcontrol.iocs.base import MotorRecordGroup

    ctx = Context()
    entry = s["entry"]
    m = getattr(drv, entry["driver"])()
    for ax, pv in s["axis_pvs"].items():
        m.axes[ax] = CAMotorProxy(pv, ctx, axis_label=ax)
    setattr(m, "config", entry)
    m.connect(axis=s["key"])
    m.offset = entry["offset"]
    m.units = entry["units"]
    group = MotorRecordGroup(s["prefix"], driver=m, motor_config=entry)
    return group.pvdb


def main(argv=None):
    from caproto.server import run
    from pystxmcontrol.iocs.config import read_slice
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", required=True)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    pvdb = build_pvdb_from_slice(read_slice(args.slice))
    run(pvdb, log_pv_names=not args.quiet)


if __name__ == "__main__":
    main()
```

**Implementer caution:** `derivedPiezo.connect()` with `simulation=0` calls `self.getPos()` → walks both axes over CA — the underlying motor IOCs must be up BEFORE the derived IOC starts (the test spawns them first; the supervisor starts derived IOCs last, Task 9). `derivedPiezo.moveTo` may call `self.axes["axis1"].checkLimits(...)`, `servoState`, `setZero` in some branches — with `reset_after_move: False` those branches are skipped; if a test hits an `AttributeError` on a proxy for a legitimately-needed method, add it to `CAMotorProxy` as a loud `NotImplementedError` first, then decide.

- [ ] **Step 4: Run tests until green**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_derived.py -v` → 3 PASS.
Full suite: `PYTHONPATH=$PWD $PY -m pytest tests/iocs -v` → green.

- [ ] **Step 5: Commit**

```bash
git add pystxmcontrol/iocs/derived_ioc.py tests/iocs/test_derived.py tests/iocs/conftest.py
git commit -m "feat(iocs): derived motors - co-located in-process + cross-controller via CAMotorProxy"
```

---

### Task 6: DAQ IOC (`daq_ioc.py`)

**Files:**
- Create: `pystxmcontrol/iocs/daq_ioc.py`
- Test: `tests/iocs/test_daq_ioc.py`

**Interfaces:**
- Consumes: `config.read_slice`.
- Produces:
  - `class DaqGroup(PVGroup)` — ctor `DaqGroup(prefix, daq=<driver obj>, daq_entry=<dict>)`. PVs (relative to prefix, e.g. `STXMSIM:DEFAULT:`):
    - `:DWELL` float ms (default 1.0) — stored; applied at acquire time via `daq.config(dwell=..., count=1, samples=1)`.
    - `:MODE` enum `('point', 'line')` (informational in v1; fly lines drive the DAQ directly in Task 8).
    - `:ACQUIRE` int — **putter awaits the full acquisition** (`daq.config(...)` in executor + `await daq.getPoint()`), writes `:COUNTS` and `:RATE` before returning, then returns 0. Because caproto completes the CA put only when the putter returns, `caput -c -w`/ophyd `set()` get busy-record completion semantics for free.
    - `:COUNTS` float (last point, read-only), `:COUNTS:WF` float64 waveform `max_length=16384` (last line written by fly scans or line acquisitions; exposed via `await group.write_line(np.ndarray)` coroutine for Task 8), `:RATE` float Hz (= counts / (dwell_ms/1000)).
  - `build_pvdb_from_slice(s: dict) -> dict` for `kind == "daq"`: instantiate driver David's way — `getattr(drivers, entry["driver"])(address=entry["address"], port=entry.get("port", 0), simulation=entry["simulation"])`, then `daq.meta.update(entry)` (UPDATE, not replace — preserves the default `"gate"` key, NOTES-environment lesson), then `daq.start()` in a thread executor at first startup.
  - CLI `$PY -m pystxmcontrol.iocs.daq_ioc --slice <path>`.
- `daq.getPoint()` is a coroutine (asyncio) — the IOC's asyncio loop awaits it DIRECTLY (no executor); `daq.config()` is sync/possibly-blocking → executor.

- [ ] **Step 1: Write the failing tests**

`tests/iocs/test_daq_ioc.py`:

```python
import time
from pathlib import Path

import pytest

from pystxmcontrol.iocs.config import load_fleet

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def daq_ioc(ioc_harness):
    fleet = load_fleet(str(REPO / "config" / "motor.json"),
                       str(REPO / "config" / "daq.json"), station="SIM")
    from pystxmcontrol.iocs.daq_ioc import build_pvdb_for_entry
    pvdb, group = build_pvdb_for_entry(fleet.daqs[0].entry, fleet.daqs[0].prefix)
    ioc_harness.start(pvdb)
    return ioc_harness, group


def test_acquire_put_completion_blocks_until_done(daq_ioc):
    h, group = daq_ioc
    ctx = h.client()
    dwell, acq, counts, rate = ctx.get_pvs(
        "STXMSIM:DEFAULT:DWELL", "STXMSIM:DEFAULT:ACQUIRE",
        "STXMSIM:DEFAULT:COUNTS", "STXMSIM:DEFAULT:RATE")
    acq.wait_for_connection(timeout=10)
    dwell.write(200.0, wait=True, timeout=10)  # 200 ms sim acquisition
    t0 = time.monotonic()
    acq.write(1, wait=True, timeout=30)        # completion callback semantics
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.18, f"put completed in {elapsed:.3f}s - did not wait for acquisition"
    c = counts.read().data[0]
    assert c > 0  # Poisson(1e7 * 0.2) ~ 2e6
    assert abs(rate.read().data[0] - c / 0.2) / (c / 0.2) < 1e-6


def test_counts_wf_written_by_write_line(daq_ioc):
    import numpy as np
    h, group = daq_ioc
    ctx = h.client()
    (wf,) = ctx.get_pvs("STXMSIM:DEFAULT:COUNTS:WF")
    wf.wait_for_connection(timeout=10)
    line = np.arange(50, dtype=float)
    h.call_soon(group.write_line(line)).result(timeout=10)
    data = wf.read().data
    assert list(data[:50]) == list(line)


def test_mode_enum(daq_ioc):
    h, group = daq_ioc
    ctx = h.client()
    (mode,) = ctx.get_pvs("STXMSIM:DEFAULT:MODE")
    mode.wait_for_connection(timeout=10)
    mode.write("line", wait=True, timeout=10)
    assert mode.read(data_type="native").data[0] in (1, b"line", "line")
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_daq_ioc.py -v`
Expected: `No module named 'pystxmcontrol.iocs.daq_ioc'`

- [ ] **Step 3: Implement `pystxmcontrol/iocs/daq_ioc.py`**

```python
"""DAQ IOC: keysight counter family behind gated-acquire PVs."""
from __future__ import annotations

import argparse
import asyncio
import functools

from pystxmcontrol.iocs import require_caproto

require_caproto()

from caproto import ChannelType  # noqa: E402
from caproto.server import PVGroup, pvproperty, run  # noqa: E402

from pystxmcontrol.iocs.config import read_slice  # noqa: E402

MAX_LINE = 16384


class DaqGroup(PVGroup):
    dwell = pvproperty(value=1.0, name=":DWELL", precision=3, doc="dwell per point, ms")
    mode = pvproperty(value="point", enum_strings=["point", "line"],
                      dtype=ChannelType.ENUM, name=":MODE")
    acquire = pvproperty(value=0, name=":ACQUIRE",
                         doc="write 1: acquire one point; put completes when done")
    counts = pvproperty(value=0.0, name=":COUNTS", read_only=True)
    counts_wf = pvproperty(value=[0.0], name=":COUNTS:WF", read_only=True,
                           max_length=MAX_LINE)
    rate = pvproperty(value=0.0, name=":RATE", read_only=True, doc="counts/s")

    def __init__(self, prefix, *, daq, daq_entry, **kwargs):
        super().__init__(prefix, **kwargs)
        self._daq = daq
        self._entry = daq_entry
        self._started = False

    async def _ensure_started(self):
        if not self._started:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._daq.start)
            self._started = True

    @acquire.putter
    async def acquire(self, instance, value):
        if not value:
            return 0
        await self._ensure_started()
        loop = asyncio.get_running_loop()
        dwell_ms = self.dwell.value
        await loop.run_in_executor(
            None, functools.partial(self._daq.config, dwell_ms, count=1, samples=1))
        data = await self._daq.getPoint()  # coroutine on OUR loop
        c = float(data[0])
        await self.counts.write(c)
        await self.rate.write(c / (dwell_ms / 1000.0) if dwell_ms else 0.0)
        return 0

    async def write_line(self, line) -> None:
        """Publish a fly-line waveform (called in-process by the fly loop)."""
        await self.counts_wf.write([float(x) for x in line])
        if len(line):
            await self.counts.write(float(line[-1]))


def build_pvdb_for_entry(entry: dict, prefix: str):
    import pystxmcontrol.drivers as drv
    cls = getattr(drv, entry["driver"])
    daq = cls(address=entry["address"], port=entry.get("port", 0),
              simulation=entry["simulation"])
    daq.meta.update(entry)  # UPDATE not replace: keeps default 'gate' key
    group = DaqGroup(prefix, daq=daq, daq_entry=entry)
    return dict(group.pvdb), group


def build_pvdb_from_slice(s: dict) -> dict:
    assert s["kind"] == "daq", s["kind"]
    pvdb, _ = build_pvdb_for_entry(s["entry"], s["prefix"])
    return pvdb


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", required=True)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    run(build_pvdb_from_slice(read_slice(args.slice)), log_pv_names=not args.quiet)


if __name__ == "__main__":
    main()
```

**Implementer caution:** long ACQUIRE putters hold that PV's write path; caproto handles other PVs concurrently — acceptable v1. If caproto's put-with-notify times out client-side, raise the client timeout in tests, not a server workaround. `pvproperty` keyword for waveforms is `max_length` in caproto 1.x — verify against `caproto/server/server.py` if a TypeError appears.

- [ ] **Step 4: Run until green; commit**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_daq_ioc.py -v` → 3 PASS; full `tests/iocs` green.

```bash
git add pystxmcontrol/iocs/daq_ioc.py tests/iocs/test_daq_ioc.py
git commit -m "feat(iocs): keysight DAQ IOC with put-callback ACQUIRE completion"
```

---

### Task 7: Shutter IOC (`shutter_ioc.py`)

**Files:**
- Create: `pystxmcontrol/iocs/shutter_ioc.py`
- Test: `tests/iocs/test_shutter_ioc.py`

**Interfaces:**
- Produces: `class ShutterGroup(PVGroup)` — ctor `ShutterGroup(prefix, shutter=<shutter obj>)`; PVs: `:MODE` enum `('OPEN','CLOSED','AUTO')` (initial `AUTO`) mapping to David's `shutter.mode` values `"open"/"close"/"auto"` + a `setStatus()` call on every MODE put; `:STATE` read-only enum `('CLOSED','OPEN')` polled from `shutter.getStatus()` every 0.5 s. `build_pvdb_from_slice(s)` for `kind == "shutter"` builds `shutter(address=s["address"])`, `.connect(simulation=s["simulation"])`. CLI `$PY -m pystxmcontrol.iocs.shutter_ioc --slice <path>`.

- [ ] **Step 1: Write the failing tests**

`tests/iocs/test_shutter_ioc.py`:

```python
import pytest


@pytest.fixture
def shutter_ioc(ioc_harness):
    from pystxmcontrol.drivers.shutter import shutter as Shutter
    sh = Shutter(address="COM_FAKE")
    sh.connect(simulation=True)
    from pystxmcontrol.iocs.shutter_ioc import ShutterGroup
    group = ShutterGroup("STXMSIM:SHUTTER1", shutter=sh)
    ioc_harness.start(group.pvdb)
    return ioc_harness, sh


@pytest.mark.parametrize("mode_str,david_mode", [
    ("OPEN", "open"), ("CLOSED", "close"), ("AUTO", "auto")])
def test_mode_maps_to_setgate_semantics(shutter_ioc, mode_str, david_mode):
    h, sh = shutter_ioc
    ctx = h.client()
    (mode,) = ctx.get_pvs("STXMSIM:SHUTTER1:MODE")
    mode.wait_for_connection(timeout=10)
    mode.write(mode_str, wait=True, timeout=10)
    assert sh.mode == david_mode


def test_state_readback_exists(shutter_ioc):
    h, sh = shutter_ioc
    ctx = h.client()
    (state,) = ctx.get_pvs("STXMSIM:SHUTTER1:STATE")
    state.wait_for_connection(timeout=10)
    assert state.read().data[0] in (0, 1)
```

- [ ] **Step 2: Run to verify failure** — `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_shutter_ioc.py -v` → module missing.

- [ ] **Step 3: Implement `pystxmcontrol/iocs/shutter_ioc.py`**

```python
"""Shutter/gate IOC: MODE enum over David's shutter.setStatus semantics."""
from __future__ import annotations

import argparse
import asyncio

from pystxmcontrol.iocs import require_caproto

require_caproto()

from caproto import ChannelType  # noqa: E402
from caproto.server import PVGroup, pvproperty, run  # noqa: E402

from pystxmcontrol.iocs.config import read_slice  # noqa: E402

_MODE_MAP = {"OPEN": "open", "CLOSED": "close", "AUTO": "auto"}


class ShutterGroup(PVGroup):
    mode = pvproperty(value="AUTO", enum_strings=list(_MODE_MAP),
                      dtype=ChannelType.ENUM, name=":MODE")
    state = pvproperty(value="CLOSED", enum_strings=["CLOSED", "OPEN"],
                       dtype=ChannelType.ENUM, name=":STATE", read_only=True)

    def __init__(self, prefix, *, shutter, poll=0.5, **kwargs):
        super().__init__(prefix, **kwargs)
        self._shutter = shutter
        self._poll = poll

    @mode.putter
    async def mode(self, instance, value):
        loop = asyncio.get_running_loop()

        def apply():
            self._shutter.mode = _MODE_MAP[str(value)]
            self._shutter.setStatus()

        await loop.run_in_executor(None, apply)
        return value

    @state.scan(period=0.5)
    async def state(self, instance, async_lib):
        loop = asyncio.get_running_loop()
        is_open = await loop.run_in_executor(None, self._shutter.getStatus)
        await instance.write("OPEN" if is_open else "CLOSED")


def build_pvdb_from_slice(s: dict) -> dict:
    assert s["kind"] == "shutter", s["kind"]
    from pystxmcontrol.drivers.shutter import shutter as Shutter
    sh = Shutter(address=s["address"])
    sh.connect(simulation=bool(s["simulation"]))
    return dict(ShutterGroup(s["prefix"], shutter=sh).pvdb)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", required=True)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    run(build_pvdb_from_slice(read_slice(args.slice)), log_pv_names=not args.quiet)


if __name__ == "__main__":
    main()
```

(Note: `@state.scan(period=0.5)` — if caproto's scan decorator doesn't accept read_only pvproperties writing to themselves, switch to a `@state.startup` while-loop with `await async_lib.library.sleep(self._poll)`.)

- [ ] **Step 4: Run until green; commit**

```bash
git add pystxmcontrol/iocs/shutter_ioc.py tests/iocs/test_shutter_ioc.py
git commit -m "feat(iocs): shutter IOC - MODE enum over setGate semantics with STATE readback"
```

---

### Task 8: E712 fly IOC (`e712_ioc.py`)

**Files:**
- Create: `pystxmcontrol/iocs/e712_ioc.py`
- Test: `tests/iocs/test_e712_fly.py`

**Interfaces:**
- Consumes: `base.MotorRecordGroup/build_controller/build_motor`, `daq_ioc.build_pvdb_for_entry` (+ returned `DaqGroup` instances for `write_line`).
- Produces:
  - `class FlyGroup(PVGroup)` — ctor `FlyGroup(prefix, motors: dict[str, motor], daq_groups: dict[str, DaqGroup], simulation: bool)`. `motors` maps enum axis label → driver. PVs under `<prefix>` (e.g. `STXMSIM:E712:FLY`):
    - Config: `:START` float, `:STOP` float, `:NPOINTS` int (1..MAX_LINE), `:DWELL` float ms, `:AXIS` enum (keys of `motors`), `:MODE` enum `('raster','continuous')` (v1: both run the same sim loop; hardware continuous path is the guarded branch).
    - Control: `:ARM` (validates config: NPOINTS in range, START/STOP inside the axis's limits, DWELL>0 → STATE=ARMED or ERROR w/ message in `:ERROR`), `:GO` (**putter runs the whole line; put-completion = line done**), `:ABORT` (sets abort flag; STATE→IDLE), `:STATE` read-only enum `('IDLE','ARMED','FLYING','ERROR')`, `:ERROR` read-only string.
    - Data: `:DATA:{daq_key}` read-only float64 waveform per attached DAQ (max_length MAX_LINE), `:POS` read-only float64 waveform (actual/interpolated positions), `:INDEX` read-only int, init 0. **Ordering contract: GO writes ALL `:DATA:*` and `:POS` waveforms first, then increments `:INDEX` — clients monitor INDEX then read waveforms.**
  - `build_pvdb_from_slice(s)` for controller slices whose `controller_cls == "E712Controller"`: motor records for each axis (reuse motor_ioc build) + one `FlyGroup` at `{station_prefix}:{label}:FLY` wired to the axis drivers and to co-hosted DaqGroups (the slice carries `s.get("daqs", [])` — **extend `write_slice`/supervisor in Task 9 to embed daq entries into the E712 slice**; for THIS task the test wires groups directly, no slice needed).
  - CLI `$PY -m pystxmcontrol.iocs.e712_ioc --slice <path>`.
- **Sim line loop (the CI-tested path), mirroring the Phase-2a spike:** on GO: STATE=FLYING; for each daq: `config(dwell, count=NPOINTS, samples=1)` (executor) then `line = await daq.getLine()` (coroutine — realistic duration `dwell*NPOINTS`); positions = `numpy.linspace(START, STOP, NPOINTS)`; abort flag checked between DAQs; write waveforms via `daq_group.write_line(line)` AND `:DATA:{key}`; write `:POS`; increment `:INDEX`; STATE=ARMED (ready for next line) — errors → STATE=ERROR + `:ERROR` message, INDEX NOT incremented.
- **Hardware line loop (guarded `if not simulation`, NOT unit-tested):** before `getLine`, configure trajectory on the driver like David's `line_image.py` scan does (`motor.trajectory_start/stop/pixel_count/pixel_dwell`, `update_trajectory()`, then `asyncio.gather(daq.getLine(), loop.run_in_executor(None, motor.moveLine))`, positions from `motor.positions`). Copy the exact call pattern from `pystxmcontrol/controller/scans/line_image.py` — read that file before writing this branch; it is landed code but exercised only in the Task-12 hardware benchmark.

- [ ] **Step 1: Write the failing tests**

`tests/iocs/test_e712_fly.py`:

```python
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from pystxmcontrol.iocs.config import load_fleet

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def fly_ioc(ioc_harness):
    # sim E712 controller + x/y motors, wired David's way
    from pystxmcontrol.iocs.base import build_motor
    import pystxmcontrol.drivers as drv
    ctrl = drv.E712Controller(address="192.168.1.201", port=5000, simulation=True)
    ctrl.initialize(simulation=True)
    entry = {"axis": "x", "minValue": -50.0, "maxValue": 50.0, "offset": 0.0,
             "units": 1.0, "max velocity": 1000.0, "simulation": 1}
    mx = build_motor("E712Motor", ctrl, dict(entry), "x")
    my = build_motor("E712Motor", ctrl, dict(entry, axis="y"), "y")

    fleet = load_fleet(str(REPO / "config" / "motor.json"),
                       str(REPO / "config" / "daq.json"), station="SIM")
    from pystxmcontrol.iocs.daq_ioc import build_pvdb_for_entry
    daq_pvdb, daq_group = build_pvdb_for_entry(fleet.daqs[0].entry, "STXMSIM:DEFAULT")

    from pystxmcontrol.iocs.e712_ioc import FlyGroup
    fly = FlyGroup("STXMSIM:E712:FLY", motors={"x": mx, "y": my},
                   daq_groups={"default": daq_group}, simulation=True)
    pvdb = {}
    pvdb.update(daq_pvdb)
    pvdb.update(fly.pvdb)
    ioc_harness.start(pvdb)
    ctx = ioc_harness.client()
    return ioc_harness, ctx


def _pvs(ctx, *suffixes):
    pvs = ctx.get_pvs(*[f"STXMSIM:E712:FLY:{s}" for s in suffixes], timeout=15)
    for pv in pvs:
        pv.wait_for_connection(timeout=15)
    return pvs


def test_arm_validates_and_transitions(fly_ioc):
    h, ctx = fly_ioc
    start, stop, npts, dwell, arm, state, error = _pvs(
        ctx, "START", "STOP", "NPOINTS", "DWELL", "ARM", "STATE", "ERROR")
    start.write(-5.0, wait=True); stop.write(5.0, wait=True)
    npts.write(20, wait=True); dwell.write(1.0, wait=True)
    arm.write(1, wait=True, timeout=15)
    assert state.read().data[0] == 1  # ARMED


def test_arm_rejects_out_of_limit_line(fly_ioc):
    h, ctx = fly_ioc
    start, stop, npts, dwell, arm, state, error = _pvs(
        ctx, "START", "STOP", "NPOINTS", "DWELL", "ARM", "STATE", "ERROR")
    start.write(-500.0, wait=True)  # axis limits are +/-50
    stop.write(5.0, wait=True); npts.write(20, wait=True); dwell.write(1.0, wait=True)
    arm.write(1, wait=True, timeout=15)
    assert state.read().data[0] == 3  # ERROR
    msg = b"".join(error.read(data_type="native").data) if isinstance(
        error.read().data[0], (bytes, int)) else error.read().data[0]
    assert b"limit" in bytes(msg).lower() or "limit" in str(msg).lower()


def test_fly_line_waveforms_and_index_ordering(fly_ioc):
    h, ctx = fly_ioc
    start, stop, npts, dwell, arm, go, state, index, data, pos = _pvs(
        ctx, "START", "STOP", "NPOINTS", "DWELL", "ARM", "GO", "STATE",
        "INDEX", "DATA:default", "POS")
    start.write(-5.0, wait=True); stop.write(5.0, wait=True)
    npts.write(25, wait=True); dwell.write(1.0, wait=True)
    arm.write(1, wait=True, timeout=15)
    assert index.read().data[0] == 0

    # monitor: on every INDEX increment the waveforms must ALREADY be fresh
    observed = []

    def on_index(sub, response):
        if response.data[0] > 0:
            observed.append((response.data[0],
                             len(data.read().data), len(pos.read().data)))

    sub = index.subscribe()
    token = sub.add_callback(on_index)

    for line_no in (1, 2, 3):
        go.write(1, wait=True, timeout=60)  # put-completion == line done
        assert index.read().data[0] == line_no

    d = np.asarray(data.read().data, dtype=float)
    p = np.asarray(pos.read().data, dtype=float)
    assert len(d) == 25 and len(p) == 25
    assert (d > 0).all()                       # Poisson counts at 1 ms dwell
    assert abs(p[0] - -5.0) < 1e-6 and abs(p[-1] - 5.0) < 1e-6
    time.sleep(0.5)
    idxs = [o[0] for o in observed]
    assert idxs == sorted(idxs) and len(set(idxs)) == len(idxs)  # monotonic
    assert all(nd == 25 and np_ == 25 for _, nd, np_ in observed)
    sub.remove_callback(token)


def test_abort_returns_to_idle(fly_ioc):
    h, ctx = fly_ioc
    start, stop, npts, dwell, arm, go, abort, state = _pvs(
        ctx, "START", "STOP", "NPOINTS", "DWELL", "ARM", "GO", "ABORT", "STATE")
    start.write(-5.0, wait=True); stop.write(5.0, wait=True)
    npts.write(2000, wait=True); dwell.write(1.0, wait=True)  # ~2 s line
    arm.write(1, wait=True, timeout=15)
    t = threading.Thread(target=lambda: go.write(1, wait=True, timeout=60))
    t.start()
    time.sleep(0.3)
    abort.write(1, wait=True, timeout=15)
    t.join(timeout=30)
    assert state.read().data[0] == 0  # IDLE


def test_go_without_arm_errors(fly_ioc):
    h, ctx = fly_ioc
    go, state = _pvs(ctx, "GO", "STATE")
    # fresh fixture; STATE may be IDLE(0): GO must not fly
    go.write(1, wait=True, timeout=15)
    assert state.read().data[0] in (0, 3)  # IDLE or ERROR, never leaves data
```

- [ ] **Step 2: Run to verify failure** — `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_e712_fly.py -v` → module missing.

- [ ] **Step 3: Implement `pystxmcontrol/iocs/e712_ioc.py`**

```python
"""E712 fly IOC: motor records + FLY PVGroup with an IOC-side line loop.

Consistency contract: on each completed line, ALL data/pos waveforms are
written BEFORE :INDEX increments. Clients monitor :INDEX, then read waveforms.
"""
from __future__ import annotations

import argparse
import asyncio
import functools

import numpy as np

from pystxmcontrol.iocs import require_caproto

require_caproto()

from caproto import ChannelType  # noqa: E402
from caproto.server import PVGroup, pvproperty, run  # noqa: E402

from pystxmcontrol.iocs.config import read_slice  # noqa: E402
from pystxmcontrol.iocs.daq_ioc import MAX_LINE, build_pvdb_for_entry  # noqa: E402

STATES = ["IDLE", "ARMED", "FLYING", "ERROR"]


def _fly_group_class(axis_labels, daq_keys):
    """FLY PVGroup with per-DAQ DATA waveforms built dynamically."""

    class FlyGroup(PVGroup):
        start = pvproperty(value=0.0, name=":START")
        stop = pvproperty(value=0.0, name=":STOP")
        npoints = pvproperty(value=10, name=":NPOINTS")
        dwell = pvproperty(value=1.0, name=":DWELL", doc="ms per point")
        axis = pvproperty(value=axis_labels[0], enum_strings=axis_labels,
                          dtype=ChannelType.ENUM, name=":AXIS")
        fly_mode = pvproperty(value="raster", enum_strings=["raster", "continuous"],
                              dtype=ChannelType.ENUM, name=":MODE")
        arm = pvproperty(value=0, name=":ARM")
        go = pvproperty(value=0, name=":GO")
        abort = pvproperty(value=0, name=":ABORT")
        state = pvproperty(value="IDLE", enum_strings=STATES,
                           dtype=ChannelType.ENUM, name=":STATE", read_only=True)
        error = pvproperty(value="", name=":ERROR", read_only=True,
                           dtype=ChannelType.CHAR, max_length=256,
                           report_as_string=True)
        pos = pvproperty(value=[0.0], name=":POS", read_only=True,
                         max_length=MAX_LINE)
        index = pvproperty(value=0, name=":INDEX", read_only=True)

        def __init__(self, prefix, *, motors, daq_groups, simulation=True, **kw):
            super().__init__(prefix, **kw)
            self._motors = motors
            self._daq_groups = daq_groups
            self._simulation = simulation
            self._abort = asyncio.Event()

        async def _set_state(self, name, error_msg=""):
            await self.state.write(name)
            await self.error.write(error_msg)

        def _current_motor(self):
            return self._motors[self.axis.enum_strings[
                self.axis.value if isinstance(self.axis.value, int)
                else self.axis.enum_strings.index(self.axis.value)]]

        @arm.putter
        async def arm(self, instance, value):
            if not value:
                return 0
            n = int(self.npoints.value)
            lo_hi = self._current_motor().config
            lo, hi = lo_hi["minValue"], lo_hi["maxValue"]
            problems = []
            if not (1 <= n <= MAX_LINE):
                problems.append(f"NPOINTS {n} outside 1..{MAX_LINE}")
            for label, v in (("START", self.start.value), ("STOP", self.stop.value)):
                if not (lo <= v <= hi):
                    problems.append(f"{label} {v} outside limit [{lo}, {hi}]")
            if self.dwell.value <= 0:
                problems.append(f"DWELL {self.dwell.value} must be > 0")
            if problems:
                await self._set_state("ERROR", "; ".join(problems)[:255])
            else:
                self._abort.clear()
                await self._set_state("ARMED")
            return 0

        @go.putter
        async def go(self, instance, value):
            if not value:
                return 0
            if STATES[self.state.value] != "ARMED":
                await self._set_state("ERROR", "GO before ARM")
                return 0
            await self._set_state("FLYING")
            try:
                aborted = await self._fly_one_line()
            except Exception as exc:  # noqa: BLE001 - surfaced on :ERROR
                await self._set_state("ERROR", str(exc)[:255])
                return 0
            if aborted:
                await self._set_state("IDLE")
            else:
                await self._set_state("ARMED")
            return 0

        @abort.putter
        async def abort(self, instance, value):
            if value:
                self._abort.set()
            return 0

        async def _fly_one_line(self) -> bool:
            loop = asyncio.get_running_loop()
            n = int(self.npoints.value)
            dwell = float(self.dwell.value)
            x0, x1 = float(self.start.value), float(self.stop.value)

            lines = {}
            for key, group in self._daq_groups.items():
                if self._abort.is_set():
                    return True
                daq = group._daq
                await group._ensure_started()
                await loop.run_in_executor(
                    None, functools.partial(daq.config, dwell, count=n, samples=1))
                if self._simulation:
                    get_task = asyncio.ensure_future(daq.getLine())
                    while not get_task.done():
                        if self._abort.is_set():
                            get_task.cancel()
                            try:
                                await get_task
                            except asyncio.CancelledError:
                                pass
                            return True
                        await asyncio.sleep(0.02)
                    lines[key] = get_task.result()
                else:  # pragma: no cover - hardware path, benchmark-only (Task 12)
                    motor = self._current_motor()
                    motor.trajectory_start = (x0, 0.0)
                    motor.trajectory_stop = (x1, 0.0)
                    motor.trajectory_pixel_count = n
                    motor.trajectory_pixel_dwell = dwell
                    motor.lineMode = "continuous"
                    await loop.run_in_executor(None, motor.update_trajectory)
                    line, _ = await asyncio.gather(
                        daq.getLine(),
                        loop.run_in_executor(None, motor.moveLine))
                    lines[key] = line

            positions = np.linspace(x0, x1, n)
            if not self._simulation and hasattr(self._current_motor(), "positions"):
                positions = np.asarray(self._current_motor().positions[0])[:n]  # pragma: no cover

            # ---- ordering contract: waveforms FIRST, then INDEX ----
            for key, line in lines.items():
                await self._data_props[key].write([float(v) for v in line])
                await self._daq_groups[key].write_line(line)
            await self.pos.write([float(v) for v in positions])
            await self.index.write(self.index.value + 1)
            return False

    # dynamic per-DAQ DATA waveform pvproperties
    data_props = {}
    for key in daq_keys:
        prop = pvproperty(value=[0.0], name=f":DATA:{key}", read_only=True,
                          max_length=MAX_LINE)
        setattr(FlyGroup, f"data_{key}", prop)
        data_props[key] = prop
    FlyGroup._data_prop_names = {k: f"data_{k}" for k in daq_keys}

    # resolve bound instances at init time
    orig_init = FlyGroup.__init__

    def patched_init(self, *a, **kw):
        orig_init(self, *a, **kw)
        self._data_props = {k: getattr(self, n)
                            for k, n in FlyGroup._data_prop_names.items()}

    FlyGroup.__init__ = patched_init
    return FlyGroup


def FlyGroup(prefix, *, motors, daq_groups, simulation=True):
    cls = _fly_group_class(list(motors), list(daq_groups))
    return cls(prefix, motors=motors, daq_groups=daq_groups, simulation=simulation)


def build_pvdb_from_slice(s: dict) -> dict:
    assert s["kind"] == "controller" and s["controller_cls"] == "E712Controller"
    from pystxmcontrol.iocs.base import (MotorRecordGroup, build_controller,
                                         build_motor)
    controller = build_controller(
        s["controller_cls"], s["controller_id"], s["port"], s["simulation"])
    pvdb: dict = {}
    motors = {}
    for m in s["motors"]:
        drv = build_motor(m["entry"]["driver"], controller, m["entry"],
                          m["entry"]["axis"])
        motors[m["entry"]["axis"]] = drv
        pvdb.update(MotorRecordGroup(m["pv"], driver=drv,
                                     motor_config=m["entry"]).pvdb)
    daq_groups = {}
    for d in s.get("daqs", []):
        dq_pvdb, group = build_pvdb_for_entry(d["entry"], d["prefix"])
        pvdb.update(dq_pvdb)
        daq_groups[d["key"]] = group
    fly_prefix = f"STXM{s['station']}:{s['label']}:FLY"
    fly = FlyGroup(fly_prefix, motors=motors, daq_groups=daq_groups,
                   simulation=bool(s["simulation"]))
    pvdb.update(fly.pvdb)
    return pvdb


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", required=True)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    run(build_pvdb_from_slice(read_slice(args.slice)), log_pv_names=not args.quiet)


if __name__ == "__main__":
    main()
```

**Implementer cautions:**
- Dynamic pvproperty attachment (`setattr` on the class before instantiation) must happen before `PVGroup`'s metaclass collects properties — if caproto's `PVGroupMeta` has already run, build the class with `type('FlyGroup', (PVGroup,), namespace)` where the namespace dict includes the per-DAQ pvproperties up front. The test only requires the PV `STXMSIM:E712:FLY:DATA:default` to exist and honor the ordering contract.
- Enum value handling on `ChannelType.ENUM` pvproperties differs by caproto version (`.value` may be int or string): normalize via `instance.enum_strings`. Check `STATES[self.state.value]` accordingly.
- Keysight sim `getLine` sleeps `dwell/1000*count` — abort test relies on that; do not shortcut the sleep.

- [ ] **Step 4: Run until green; commit**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_e712_fly.py -v` → 5 PASS; full `tests/iocs` green.

```bash
git add pystxmcontrol/iocs/e712_ioc.py tests/iocs/test_e712_fly.py
git commit -m "feat(iocs): E712 fly IOC - FLY PVGroup with IOC-side line loop and INDEX ordering contract"
```

---

### Task 9: Supervisor (`supervisor.py`, `stxm-iocs`)

**Files:**
- Create: `pystxmcontrol/iocs/supervisor.py`
- Modify: `pystxmcontrol/iocs/config.py` (embed daq entries into E712 slices)
- Test: `tests/iocs/test_supervisor.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `plan_fleet(fleet: FleetConfig, slice_dir: str) -> list[IocPlan]` where `@dataclass IocPlan: name: str, module: str, slice_path: str`. Rules: each `ControllerGroup` → `pystxmcontrol.iocs.motor_ioc` EXCEPT `controller_cls == "E712Controller"` → `pystxmcontrol.iocs.e712_ioc`; each `DaqEntry` → `daq_ioc` UNLESS attached to an E712 group (v1 rule: if any controller group is an E712, ALL daq entries ride in its slice as `s["daqs"]` and get no standalone IOC — document in README); each `ShutterEntry` → `shutter_ioc` unless `--no-shutter-iocs`; each `DerivedRemoteGroup` → `derived_ioc` (started LAST, after a `--startup-delay` default 3 s so underlying PVs exist).
  - `class Supervisor`: `__init__(plans, restart_backoff=(1,2,4,8,16,30), status_prefix="STXM{station}:SUP")`, `start()` (spawn all via `subprocess.Popen([sys.executable, "-m", plan.module, "--slice", plan.slice_path, "--quiet"])`, monitor thread per fleet: poll `proc.poll()` every 0.5 s, on exit restart after backoff step, escalating; reset backoff after 60 s healthy), `stop()` (terminate all, wait), `status() -> dict[name, {"running": bool, "restarts": int, "pid": int|None}]`, and a status PVGroup: for each plan `SUP:{name}:RUNNING` (0/1) + `SUP:{name}:RESTARTS` (int), served from the supervisor's own asyncio caproto server; plus stdout table every `--status-interval` (default 10 s, 0=off).
  - `main(argv=None)`: args `--motor-config` (default: David's shipped `config/motor.json` resolved via `pystxmcontrol` package location), `--daq-config`, `--station` (default `SIM`, or env `STXM_STATION`), `--slice-dir` (default: temp dir), `--no-shutter-iocs`, `--status-interval`, `--startup-delay`. Runs until Ctrl-C; on KeyboardInterrupt calls `stop()`.
- Supervisor does NOT import driver modules itself (config parsing only needs `pystxmcontrol.drivers` attr checks — acceptable).

- [ ] **Step 1: Write the failing tests**

`tests/iocs/test_supervisor.py`:

```python
import sys
import time
from pathlib import Path

import pytest

from pystxmcontrol.iocs.config import load_fleet

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def fleet():
    return load_fleet(str(REPO / "config" / "motor.json"),
                      str(REPO / "config" / "daq.json"), station="SIM")


def test_plan_fleet_modules(fleet, tmp_path):
    from pystxmcontrol.iocs.supervisor import plan_fleet
    plans = plan_fleet(fleet, str(tmp_path))
    by_module = {}
    for p in plans:
        by_module.setdefault(p.module, []).append(p.name)
    # shipped config has no E712 entry -> all controllers use motor_ioc
    assert len(by_module.get("pystxmcontrol.iocs.motor_ioc", [])) >= 4
    assert len(by_module.get("pystxmcontrol.iocs.daq_ioc", [])) == 1
    assert len(by_module.get("pystxmcontrol.iocs.shutter_ioc", [])) == 1
    assert len(by_module.get("pystxmcontrol.iocs.derived_ioc", [])) == 3  # SampleX, SampleY, Energy
    # derived plans come last
    assert all(p.module != "pystxmcontrol.iocs.derived_ioc" for p in plans[:-3])
    for p in plans:
        assert Path(p.slice_path).exists()


def test_plan_fleet_e712_absorbs_daqs(tmp_path):
    import json
    base = json.loads((REPO / "config" / "motor.json").read_text())
    cfg = {
        "FlyX": {
            "index": 0, "type": "primary", "axis": "x", "driver": "E712Motor",
            "controllerID": "192.168.1.201", "port": 5000,
            "controller": "E712Controller", "max velocity": 1000.0,
            "minValue": -50.0, "maxValue": 50.0, "offset": 0.0, "units": 1.0,
            "display": True, "simulation": 1,
        },
    }
    mp = tmp_path / "motor.json"
    mp.write_text(json.dumps(cfg))
    fleet = load_fleet(str(mp), str(REPO / "config" / "daq.json"), station="SIM")
    if not fleet.controller_groups:
        pytest.skip("E712Controller unavailable in this env (pipython guard)")
    from pystxmcontrol.iocs.supervisor import plan_fleet
    from pystxmcontrol.iocs.config import read_slice
    plans = plan_fleet(fleet, str(tmp_path / "slices"))
    e712 = [p for p in plans if p.module == "pystxmcontrol.iocs.e712_ioc"]
    assert len(e712) == 1
    s = read_slice(e712[0].slice_path)
    assert [d["key"] for d in s["daqs"]] == ["default"]
    assert not [p for p in plans if p.module == "pystxmcontrol.iocs.daq_ioc"]


def test_supervisor_restarts_crashed_ioc(tmp_path, free_port):
    """Use a tiny fake IOC module that exits after N seconds to test restart."""
    from pystxmcontrol.iocs.supervisor import IocPlan, Supervisor
    fake = tmp_path / "fake_ioc.py"
    fake.write_text("import sys, time\ntime.sleep(1.0)\nsys.exit(1)\n")
    plan = IocPlan(name="fake", module=None, slice_path=str(fake))
    # Supervisor must support module=None -> spawn [sys.executable, slice_path]
    sup = Supervisor([plan], restart_backoff=(0.5, 0.5), status_prefix=None)
    sup.start()
    try:
        time.sleep(4.0)
        st = sup.status()["fake"]
        assert st["restarts"] >= 1
    finally:
        sup.stop()


def test_supervisor_status_pvs(tmp_path, free_port):
    from pystxmcontrol.iocs.supervisor import IocPlan, Supervisor
    fake = tmp_path / "fake_ioc.py"
    fake.write_text("import time\ntime.sleep(60)\n")
    sup = Supervisor([IocPlan(name="fake", module=None, slice_path=str(fake))],
                     status_prefix="STXMSIM:SUP")
    sup.start()
    try:
        from caproto.threading.client import Context
        ctx = Context()
        running, restarts = ctx.get_pvs("STXMSIM:SUP:fake:RUNNING",
                                        "STXMSIM:SUP:fake:RESTARTS", timeout=20)
        running.wait_for_connection(timeout=20)
        assert running.read().data[0] == 1
        assert restarts.read().data[0] == 0
    finally:
        sup.stop()


def test_console_script_declared():
    import tomllib
    py = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert py["project"]["scripts"]["stxm-iocs"] == "pystxmcontrol.iocs.supervisor:main"
    assert "caproto>=1.1" in py["project"]["optional-dependencies"]["iocs"]
```

- [ ] **Step 2: Run to verify failure** — `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_supervisor.py -v`

- [ ] **Step 3: Implement**

First extend `config.write_slice`: `write_slice(group, fleet, path, daqs=None)` — when `daqs` (list of `DaqEntry`) is passed for a controller slice, add `"daqs": [{"key": d.key, "entry": d.entry, "prefix": d.prefix} for d in daqs]`.

`pystxmcontrol/iocs/supervisor.py`:

```python
"""stxm-iocs: parse motor.json/daq.json, run one caproto IOC per controller.

    stxm-iocs --station 7011 --motor-config /path/motor.json --daq-config /path/daq.json
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from pystxmcontrol.iocs import require_caproto

require_caproto()

from pystxmcontrol.iocs.config import (  # noqa: E402
    FleetConfig, load_fleet, write_slice)


@dataclass
class IocPlan:
    name: str
    module: str | None  # None -> run slice_path as a plain script (tests)
    slice_path: str
    delay: float = 0.0


def plan_fleet(fleet: FleetConfig, slice_dir: str,
               shutter_iocs: bool = True, startup_delay: float = 3.0) -> list[IocPlan]:
    Path(slice_dir).mkdir(parents=True, exist_ok=True)
    plans: list[IocPlan] = []
    e712_groups = [g for g in fleet.controller_groups
                   if g.controller_cls == "E712Controller"]
    daqs_absorbed = bool(e712_groups)
    for g in fleet.controller_groups:
        p = str(Path(slice_dir) / f"{g.label}.json")
        if g in e712_groups:
            write_slice(g, fleet, p, daqs=fleet.daqs)
            plans.append(IocPlan(name=g.label, module="pystxmcontrol.iocs.e712_ioc",
                                 slice_path=p))
        else:
            write_slice(g, fleet, p)
            plans.append(IocPlan(name=g.label, module="pystxmcontrol.iocs.motor_ioc",
                                 slice_path=p))
    if not daqs_absorbed:
        for d in fleet.daqs:
            p = str(Path(slice_dir) / f"daq_{d.key}.json")
            write_slice(d, fleet, p)
            plans.append(IocPlan(name=f"daq_{d.key}",
                                 module="pystxmcontrol.iocs.daq_ioc", slice_path=p))
    if shutter_iocs:
        for sh in fleet.shutters:
            p = str(Path(slice_dir) / f"{sh.key}.json")
            write_slice(sh, fleet, p)
            plans.append(IocPlan(name=sh.key,
                                 module="pystxmcontrol.iocs.shutter_ioc", slice_path=p))
    for d in fleet.derived_remote:  # LAST: they are CA clients of the above
        p = str(Path(slice_dir) / f"derived_{d.key}.json")
        write_slice(d, fleet, p)
        plans.append(IocPlan(name=f"derived_{d.key}",
                             module="pystxmcontrol.iocs.derived_ioc",
                             slice_path=p, delay=startup_delay))
    return plans


class Supervisor:
    def __init__(self, plans: list[IocPlan],
                 restart_backoff=(1, 2, 4, 8, 16, 30),
                 status_prefix: str | None = None,
                 status_interval: float = 0.0):
        self._plans = plans
        self._backoff = restart_backoff
        self._status_prefix = status_prefix
        self._status_interval = status_interval
        self._procs: dict[str, subprocess.Popen | None] = {}
        self._restarts: dict[str, int] = {p.name: 0 for p in plans}
        self._stopping = threading.Event()
        self._threads: list[threading.Thread] = []
        self._status_loop: asyncio.AbstractEventLoop | None = None
        self._status_channels: dict[str, tuple] = {}

    # -- process control ---------------------------------------------------
    def _spawn(self, plan: IocPlan) -> subprocess.Popen:
        if plan.module is None:
            cmd = [sys.executable, plan.slice_path]
        else:
            cmd = [sys.executable, "-m", plan.module,
                   "--slice", plan.slice_path, "--quiet"]
        env = dict(os.environ)
        env.setdefault("PYTHONPATH", str(Path(__file__).resolve().parents[2]))
        return subprocess.Popen(cmd, env=env)

    def _monitor(self, plan: IocPlan):
        if plan.delay and not self._stopping.wait(plan.delay):
            pass
        attempt = 0
        while not self._stopping.is_set():
            proc = self._spawn(plan)
            self._procs[plan.name] = proc
            self._publish(plan.name, running=1)
            healthy_since = time.monotonic()
            while proc.poll() is None:
                if self._stopping.wait(0.5):
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    self._publish(plan.name, running=0)
                    return
                if time.monotonic() - healthy_since > 60:
                    attempt = 0
            self._publish(plan.name, running=0)
            if self._stopping.is_set():
                return
            self._restarts[plan.name] += 1
            self._publish(plan.name, restarts=self._restarts[plan.name])
            delay = self._backoff[min(attempt, len(self._backoff) - 1)]
            attempt += 1
            print(f"[stxm-iocs] {plan.name} exited rc={proc.returncode}; "
                  f"restart in {delay}s (restart #{self._restarts[plan.name]})")
            if self._stopping.wait(delay):
                return

    def start(self):
        if self._status_prefix:
            self._start_status_server()
        for plan in self._plans:
            t = threading.Thread(target=self._monitor, args=(plan,), daemon=True)
            t.start()
            self._threads.append(t)
        if self._status_interval:
            t = threading.Thread(target=self._table_loop, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        self._stopping.set()
        for t in self._threads:
            t.join(timeout=15)
        for proc in self._procs.values():
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        if self._status_loop is not None:
            self._status_loop.call_soon_threadsafe(self._status_loop.stop)

    def status(self):
        return {
            name: {
                "running": proc is not None and proc.poll() is None,
                "restarts": self._restarts[name],
                "pid": proc.pid if proc is not None and proc.poll() is None else None,
            }
            for name, proc in ((p.name, self._procs.get(p.name))
                               for p in self._plans)
        }

    def _table_loop(self):
        while not self._stopping.wait(self._status_interval):
            print(f"{'IOC':<24} {'RUNNING':<8} {'RESTARTS':<8} PID")
            for name, st in self.status().items():
                print(f"{name:<24} {int(st['running']):<8} "
                      f"{st['restarts']:<8} {st['pid'] or '-'}")

    # -- status PVs ---------------------------------------------------------
    def _start_status_server(self):
        from caproto import ChannelInteger

        pvdb = {}
        for plan in self._plans:
            running = ChannelInteger(value=0)
            restarts = ChannelInteger(value=0)
            pvdb[f"{self._status_prefix}:{plan.name}:RUNNING"] = running
            pvdb[f"{self._status_prefix}:{plan.name}:RESTARTS"] = restarts
            self._status_channels[plan.name] = (running, restarts)

        started = threading.Event()

        def runner():
            from caproto.asyncio.server import start_server
            self._status_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._status_loop)

            async def main():
                started.set()
                await start_server(pvdb)

            try:
                self._status_loop.run_until_complete(main())
            except (asyncio.CancelledError, RuntimeError):
                pass

        threading.Thread(target=runner, daemon=True).start()
        started.wait(10)
        time.sleep(0.5)

    def _publish(self, name: str, running: int | None = None,
                 restarts: int | None = None):
        if not self._status_channels or self._status_loop is None:
            return
        ch_running, ch_restarts = self._status_channels[name]

        async def _do():
            if running is not None:
                await ch_running.write(running)
            if restarts is not None:
                await ch_restarts.write(restarts)

        try:
            asyncio.run_coroutine_threadsafe(_do(), self._status_loop)
        except RuntimeError:
            pass


def _default_config(name: str) -> str:
    import pystxmcontrol
    pkg_root = Path(pystxmcontrol.__file__).resolve().parents[1]
    return str(pkg_root / "config" / name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--motor-config", default=_default_config("motor.json"))
    parser.add_argument("--daq-config", default=_default_config("daq.json"))
    parser.add_argument("--station", default=os.environ.get("STXM_STATION", "SIM"))
    parser.add_argument("--slice-dir", default=None)
    parser.add_argument("--no-shutter-iocs", action="store_true")
    parser.add_argument("--status-interval", type=float, default=10.0)
    parser.add_argument("--startup-delay", type=float, default=3.0)
    args = parser.parse_args(argv)

    slice_dir = args.slice_dir or tempfile.mkdtemp(prefix="stxm_iocs_")
    fleet = load_fleet(args.motor_config, args.daq_config, station=args.station)
    for key, reason in fleet.skipped:
        print(f"[stxm-iocs] skipping {key}: {reason}")
    plans = plan_fleet(fleet, slice_dir, shutter_iocs=not args.no_shutter_iocs,
                       startup_delay=args.startup_delay)
    print(f"[stxm-iocs] station STXM{args.station}: {len(plans)} IOCs")
    sup = Supervisor(plans, status_prefix=f"STXM{args.station}:SUP",
                     status_interval=args.status_interval)
    sup.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[stxm-iocs] shutting down")
        sup.stop()


if __name__ == "__main__":
    main()
```

(Verify `from caproto import ChannelInteger` — if it lives elsewhere, `from caproto.server import ...` or `caproto._data`; grep the venv.)

- [ ] **Step 4: Run until green**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_supervisor.py -v` → 5 PASS (the E712 test may skip if pipython missing — that skip is expected and fine). Full suite green.

- [ ] **Step 5: Commit**

```bash
git add pystxmcontrol/iocs/supervisor.py pystxmcontrol/iocs/config.py tests/iocs/test_supervisor.py
git commit -m "feat(iocs): stxm-iocs supervisor - fleet planning, restart backoff, status PVs"
```

---

### Task 10: e2e — ophyd EpicsMotor + full fly line over PVs

**Files:**
- Test: `tests/iocs/test_e2e_ophyd.py`
- Possibly create: `tests/iocs/data/e712_motor.json` (synthetic E712 sim config)

**Interfaces:** consumes everything; this is the spec-§7 acceptance test.

**Env contract for this file (set via `monkeypatch` before importing ophyd):** `OPHYD_CONTROL_LAYER=caproto`, `EPICS_CA_ADDR_LIST` per `free_port`/`spawn_ioc` accumulated list, `EPICS_CA_AUTO_ADDR_LIST=NO`. ophyd reads `OPHYD_CONTROL_LAYER` at import — set it at MODULE level before any ophyd import, and keep every ophyd import inside test functions/fixtures.

- [ ] **Step 1: Write the failing e2e tests**

`tests/iocs/test_e2e_ophyd.py`:

```python
"""Spec §7 e2e: sim-backed IOC subprocess driven by real ophyd EpicsMotor + fly line over PVs."""
import json
import os
import time
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("OPHYD_CONTROL_LAYER", "caproto")

from pystxmcontrol.iocs.config import load_fleet, write_slice  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _e712_sim_config(tmp_path):
    cfg = {
        "FlyX": {
            "index": 0, "type": "primary", "axis": "x", "driver": "E712Motor",
            "controllerID": "192.168.1.201", "port": 5000,
            "controller": "E712Controller", "max velocity": 1000.0,
            "minValue": -50.0, "maxValue": 50.0, "offset": 0.0, "units": 1.0,
            "display": True, "simulation": 1,
        },
        "FlyY": {
            "index": 1, "type": "primary", "axis": "y", "driver": "E712Motor",
            "controllerID": "192.168.1.201", "port": 5000,
            "controller": "E712Controller", "max velocity": 1000.0,
            "minValue": -50.0, "maxValue": 50.0, "offset": 0.0, "units": 1.0,
            "display": True, "simulation": 1,
        },
    }
    p = tmp_path / "motor.json"
    p.write_text(json.dumps(cfg))
    return p


@pytest.fixture
def e712_fleet_up(tmp_path, free_port, spawn_ioc):
    pytest.importorskip("pipython", reason="E712Controller needs pipython even in sim")
    mp = _e712_sim_config(tmp_path)
    fleet = load_fleet(str(mp), str(REPO / "config" / "daq.json"), station="SIM")
    from pystxmcontrol.iocs.supervisor import plan_fleet
    plans = plan_fleet(fleet, str(tmp_path / "slices"))
    for plan in plans:
        spawn_ioc(plan.module, plan.slice_path, free_port)
    return fleet


def test_ophyd_epicsmotor_move_readback_stop_limits(e712_fleet_up):
    from ophyd import EpicsMotor
    m = EpicsMotor("STXMSIM:E712:FlyX", name="flyx")
    m.wait_for_connection(timeout=30)

    st = m.move(7.0, timeout=60)
    assert st.done and st.success
    assert abs(m.position - 7.0) < 1e-3

    assert m.low_limit_travel.get() == -50.0
    assert m.high_limit_travel.get() == 50.0
    with pytest.raises(Exception):
        m.move(60.0, timeout=30)  # outside HLM -> rejected put
    assert abs(m.position - 7.0) < 1e-3

    # STOP PV is wired (sim moves are fast; just assert the put round-trips)
    m.stop_signal.put(1, wait=True)
    time.sleep(0.2)
    assert m.motor_done_move.get() == 1


def test_full_fly_line_over_pvs(e712_fleet_up):
    from caproto.threading.client import Context
    ctx = Context()
    names = ["START", "STOP", "NPOINTS", "DWELL", "AXIS", "ARM", "GO",
             "STATE", "INDEX", "DATA:default", "POS"]
    pvs = dict(zip(names, ctx.get_pvs(
        *[f"STXMSIM:E712:FLY:{n}" for n in names], timeout=30)))
    pvs["GO"].wait_for_connection(timeout=30)

    pvs["START"].write(-10.0, wait=True); pvs["STOP"].write(10.0, wait=True)
    pvs["NPOINTS"].write(40, wait=True); pvs["DWELL"].write(1.0, wait=True)
    pvs["AXIS"].write("x", wait=True)

    index_events = []
    sub = pvs["INDEX"].subscribe()
    token = sub.add_callback(
        lambda s, r: index_events.append(
            (int(r.data[0]), len(pvs["DATA:default"].read().data),
             len(pvs["POS"].read().data))))

    pvs["ARM"].write(1, wait=True, timeout=30)
    assert pvs["STATE"].read().data[0] == 1  # ARMED
    n_lines = 3
    for i in range(1, n_lines + 1):
        pvs["GO"].write(1, wait=True, timeout=120)
        assert pvs["INDEX"].read().data[0] == i

    data = np.asarray(pvs["DATA:default"].read().data, dtype=float)
    pos = np.asarray(pvs["POS"].read().data, dtype=float)
    assert len(data) == 40 and len(pos) == 40          # waveform lengths
    assert (data > 0).all()
    assert abs(pos[0] + 10.0) < 1e-6 and abs(pos[-1] - 10.0) < 1e-6
    time.sleep(0.5)
    nonzero = [e for e in index_events if e[0] > 0]
    idxs = [e[0] for e in nonzero]
    assert idxs == sorted(idxs) and len(set(idxs)) == len(idxs)  # INDEX monotonic
    assert all(nd == 40 and npos == 40 for _, nd, npos in nonzero)  # write-then-increment
    sub.remove_callback(token)


def test_acquire_completion_over_pvs(e712_fleet_up):
    from caproto.threading.client import Context
    ctx = Context()
    dwell, acq, counts = ctx.get_pvs(
        "STXMSIM:DEFAULT:DWELL", "STXMSIM:DEFAULT:ACQUIRE",
        "STXMSIM:DEFAULT:COUNTS", timeout=30)
    acq.wait_for_connection(timeout=30)
    dwell.write(150.0, wait=True)
    t0 = time.monotonic()
    acq.write(1, wait=True, timeout=60)
    assert time.monotonic() - t0 >= 0.13
    assert counts.read().data[0] > 0
```

Notes:
- `pipython` is a hard import inside `E712Controller.py` (module-level `from pipython import ...`) even for sim — the driver `__init__.py` guard means `E712Controller` may be ABSENT from `pystxmcontrol.drivers`. **Check first**: `$PY -c "import pystxmcontrol.drivers as d; print(hasattr(d,'E712Controller'))"`. If False, `pip install pipython` into the lightfall venv (pure-python GCS lib, safe) and record it in NOTES-environment.md. The `importorskip` guard keeps the suite honest either way; with pipython installed the e2e MUST run, not skip — verify no skips in the final run.
- ophyd's caproto control layer: if `EpicsMotor` connection stalls, check `ophyd.set_cl("caproto")` as a fallback at fixture time, and ensure `EPICS_CA_ADDR_LIST` includes every spawned port (the accumulated-list behavior from Task 5).

- [ ] **Step 2: Run — iterate until green (this is integration debugging, expect env iteration)**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs/test_e2e_ophyd.py -v`
Expected end state: 3 PASS, 0 skips.

- [ ] **Step 3: Full suite; commit**

Run: `PYTHONPATH=$PWD $PY -m pytest tests/iocs -v` → everything green.

```bash
git add tests/iocs/test_e2e_ophyd.py
git commit -m "test(iocs): e2e - ophyd EpicsMotor + full fly line + ACQUIRE completion over real CA"
```

If pipython was installed, also update `C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\NOTES-environment.md` (plugin repo, separate commit there): add a line under the Task-6 dep table: `pipython | <ver> | E712Controller import (sim + hardware)`.

---

### Task 11: README + PV surface docs (`pystxmcontrol/iocs/README.md`)

**Files:**
- Create: `pystxmcontrol/iocs/README.md`

**Interfaces:** none (docs). Upstreamable to David as part of the single-PR package.

- [ ] **Step 1: Write the README** covering, in this order (all content is already fixed by earlier tasks — transcribe, don't invent):
  1. What this is (one paragraph: caproto IOC layer over pystxmcontrol drivers; spec §1 motivation condensed, including the performance answer: line loop runs IOC-side, EPICS is control/reporting plane only).
  2. Install: `pip install pystxmcontrol[iocs]`.
  3. Quick start: `stxm-iocs --station 7011` (+ table of CLI flags from Task 9).
  4. PV surface tables: motor record fields (VAL/RBV/DMOV/MOVN/STOP/HLM/LLM/EGU/VELO + semantics), FLY group (all PVs + the INDEX write-then-increment ordering contract, stated verbatim: "clients monitor :INDEX; when it increments, all :DATA:* and :POS waveforms for that line are already written"), DAQ group (ACQUIRE put-completion semantics), shutter group.
  5. Naming: `STXM{station}:{controller}:{axis}` + per-entry `"epics": {"pv": ...}` override; note that motor.json/daq.json stay the single source of truth and are never modified by this layer.
  6. Coexistence/migration (spec §6): repoint motor.json entries at `epicsMotor` with the new PV names; hardware single-ownership warning (an IOC and the legacy server must not share a serial port; shutter/gate note re `--no-shutter-iocs`).
  7. Derived motors: co-located vs cross-controller (CA-composed; start order handled by supervisor; `simulation: 0` requirement for CA-composed entries).
  8. Testing: how to run the suite; `EPICS_CA_MAX_ARRAY_BYTES=1000000` recommendation for long lines.
  9. Not in v1 (spec §9 list) + the hardware benchmark pointer (Task 12).

- [ ] **Step 2: Commit**

```bash
git add pystxmcontrol/iocs/README.md
git commit -m "docs(iocs): README - usage, PV surface, ordering contract, migration notes"
```

---

### Task 12: Hardware benchmark stub (plan task only — needs beamline time)

**Files:**
- Create: `pystxmcontrol/iocs/benchmark.py`

**Interfaces:** none yet. This task ships a RUNNABLE skeleton whose hardware sections raise `NotImplementedError` with instructions — it is the named placeholder for the spec-§7 benchmark with David.

- [ ] **Step 1: Write the stub**

```python
"""Fly-line benchmark: native pystxmcontrol server vs caproto IOC path.

NEEDS BEAMLINE TIME + HARDWARE (E712 + keysight). Run with David.
Acceptance (spec 2026-07-12 §7): no measurable line-rate regression;
target < 2 % line-turnaround overhead vs the native scan server.

Usage (once implemented):
    python -m pystxmcontrol.iocs.benchmark --lines 100 --npoints 1000 --dwell 1.0
"""
from __future__ import annotations

import argparse


def bench_ioc_path(lines: int, npoints: int, dwell_ms: float) -> list[float]:
    """Time `lines` fly lines through STXM{station}:E712:FLY PVs.

    Implementation sketch (do NOT run in sim - sim timings are meaningless):
    ARM once, then per line: t0 = perf_counter(); put GO with wait=True;
    record perf_counter() - t0. Return per-line turnaround seconds.
    """
    raise NotImplementedError("needs hardware; see module docstring")


def bench_native_path(lines: int, npoints: int, dwell_ms: float) -> list[float]:
    """Same measurement through David's native scan server (line_image scan),
    same hardware, same trajectory. Coordinate with David for the driver call
    sequence (controller/scans/line_image.py)."""
    raise NotImplementedError("needs hardware; see module docstring")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lines", type=int, default=100)
    parser.add_argument("--npoints", type=int, default=1000)
    parser.add_argument("--dwell", type=float, default=1.0)
    args = parser.parse_args(argv)
    ioc = bench_ioc_path(args.lines, args.npoints, args.dwell)
    native = bench_native_path(args.lines, args.npoints, args.dwell)
    import statistics
    m_i, m_n = statistics.median(ioc), statistics.median(native)
    print(f"native median {m_n * 1000:.2f} ms | ioc median {m_i * 1000:.2f} ms "
          f"| overhead {(m_i / m_n - 1) * 100:+.2f}%")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Sanity-check it imports, commit**

Run: `PYTHONPATH=$PWD $PY -c "import pystxmcontrol.iocs.benchmark"` → no error.

```bash
git add pystxmcontrol/iocs/benchmark.py
git commit -m "chore(iocs): hardware benchmark stub (needs beamline time with David)"
```

---

### Task 13: Whole-branch verification

- [ ] **Step 1: Full test suite, fresh shell**

```bash
cd /c/Users/rp/PycharmProjects/ncs/lightfall-pystxmcontrol/_pystxmcontrol_iocs_wt
PYTHONPATH=$PWD /c/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/iocs -v
```
Expected: all PASS, 0 skipped (except the documented pipython skip ONLY if pipython was deliberately not installed — Task 10 should have installed it).

- [ ] **Step 2: Import-isolation regression** (Global Constraint):

```bash
PYTHONPATH=$PWD /c/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -c "import sys, pystxmcontrol, pystxmcontrol.drivers, pystxmcontrol.controller.server; assert 'caproto' not in sys.modules; print('base package clean')"
```

- [ ] **Step 3: Live supervisor smoke** (manual, ~60 s): in one shell run
`PYTHONPATH=$PWD $PY -m pystxmcontrol.iocs.supervisor --station SIM --status-interval 5` — expect the status table showing all IOCs RUNNING with the shipped sim config; in another shell `PYTHONPATH=$PWD $PY -c "from caproto.threading.client import Context; ctx=Context(); (pv,)=ctx.get_pvs('STXMSIM:MCL:FineX'); pv.wait_for_connection(timeout=15); pv.write(3.0, wait=True); print('live fleet OK')"` with `EPICS_CA_ADDR_LIST=127.0.0.1 EPICS_CA_AUTO_ADDR_LIST=NO`. Ctrl-C the supervisor; expect clean shutdown. (Default ports here — fine for a manual smoke, no test suite running concurrently.)

- [ ] **Step 4:** Follow superpowers:requesting-code-review then superpowers:finishing-a-development-branch. Branch stays LOCAL (no push — Ron drives). Named follow-ups (record, do not do): upstream PR to David; CSM-plugin/iocular supervision; spec #3 Lightfall migration; hardware benchmark (Task 12).

---

## Self-review notes (spec §-by-§ coverage)

- §2.1 hybrid per driver → Tasks 4 (thin mirrors) + 8 (E712 fly). §2.2 motor families + core DAQs, detectors out → config.py wraps all available motor drivers, daq_ioc keysight; no detector code anywhere. §2.3 derived in caproto → Task 5. §2.4 standalone supervisor reading David's configs → Task 9. §2.5 leaf subpackage, guarded → Tasks 1/13. §2.6 mock motor record fields → Task 3. §2.7 re-sequencing → no Lightfall changes in this plan.
- §3.3 naming → Task 2. §4.1 → Task 3. §4.2 → Task 5. §4.3 → Task 8 (all listed PVs incl. INDEX contract). §4.4 → Tasks 6/7. §4.5 → MAX_LINE=16384 (128 KB float64 max, within the documented 1 MB EPICS_CA_MAX_ARRAY_BYTES; README notes it).
- §7 unit (limits/DMOV/STOP) → Task 3; e2e (EpicsMotor + fly line + ordering + ACQUIRE) → Task 10; benchmark stub → Task 12.
- Known intentional deviations: none. Known risk areas flagged inline as "Implementer caution" (caproto record-field putter attachment, dynamic pvproperty creation, `start_server` signature, enum value normalization, multi-port CA client env). These are test-pinned: tests define the contract, implementation may adapt.
