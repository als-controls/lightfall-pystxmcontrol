# Lightfall EPICS Migration (spec #3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate lightfall-pystxmcontrol's device layer from in-process pystxmcontrol driver wrappers to classic-ophyd EPICS clients of the spec-#2 caproto IOCs, leaving plans/viz/Tiled contract byte-identical.

**Architecture:** Axes become stock `ophyd.EpicsMotor` (happi entries only). A new `StxmCounter(ophyd.Device)` of `EpicsSignal`s replaces `PystxmCounter`; a new `StxmLineFlyer(ophyd.Device)` drives the FLY PVGroup and emits the identical one-event-per-line collect output. The happi DB is generated from the plugin's own sim motor/daq JSONs via spec #2's `pystxmcontrol.iocs.config.load_fleet`, so PV names cannot drift. Sim mode = run the spec-#2 IOC fleet; the in-process sim factories and ophyd-async wrappers are deleted.

**Tech Stack:** classic ophyd 1.11.1 with `OPHYD_CONTROL_LAYER=caproto`, caproto 1.3.0 (+ **netifaces** — required), bluesky RunEngine, happi, spec-#2 `pystxmcontrol.iocs` (from the LOCAL fork worktree), pytest.

## Global Constraints

- **Repo:** `C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol` (local `main`, no remote pushes by us). Work in a worktree at `.worktrees/epics-migration`, branch `feature/epics-migration` off `main`.
- **Interpreter:** ALWAYS `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python` (`$PY` below). Never bare python/pytest. Tests from the worktree root run with `PYTHONPATH=<worktree>/src` prepended (the editable install points at the MAIN checkout) — the conftest also injects the IOC-layer path (see Task 1), but `$PYTHONPATH` for the package itself must be set on the command line.
- **Spec-#2 IOC layer** comes from env var `PYSTXMCONTROL_IOCS_SRC`, default `C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\_pystxmcontrol_iocs_wt` (branch `feature/caproto-iocs`, HEAD `460d27d`). Tests FAIL loudly if missing — never skip. Do not modify anything under that worktree.
- **Transport env:** `OPHYD_CONTROL_LAYER=caproto` must be set before any `ophyd` import (conftest + plugin module do this defensively). `netifaces` must be importable (installed 2026-07-12). Per-test CA isolation: random ports via `EPICS_CAS_SERVER_PORT` + `EPICS_CA_SERVER_PORT` (server) and accumulated `EPICS_CA_ADDR_LIST="127.0.0.1:<p1> 127.0.0.1:<p2> …"`, `EPICS_CA_AUTO_ADDR_LIST=NO` (client + every child env).
- **caproto client gotchas (verified in spec #2):** enum PVs cannot be written as bare native strings from the threading client — write integer indices (ophyd `EpicsSignal.set` on enums: pin behavior during implementation; fall back to int). Reads with `string=True` return enum strings.
- **Contract v1 is frozen:** the new flyer's `describe_collect()`/`collect()` output shapes and keys (`X_DATA_KEY="SampleX"`, `Y_DATA_KEY="SampleY"`, counts under the flyer's `.name`, one event per line) must match `contract.py` and the committed golden fixture. `tests/test_contract.py` and `tests/test_golden_fixture.py` must pass UNCHANGED.
- **Deleted, not kept:** `config.make_sim_motor`/`make_sim_counter`, `PystxmAxis`, `PystxmCounter`, the in-process `PystxmLineFlyer` internals. `DEFAULT_AXES`/`DEFAULT_COUNTER` dicts are replaced by the packaged sim JSONs.
- **Commits:** explicit `git add <paths>` only. Every commit message ends with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01PFykQo3UJmNXTg3kxLHKxv`
- **Deferred (spec §7):** scan-panel/viz changes beyond docs, spec #1 contract, hardware (7011) happi DB, pyepics, changes to the spec-#2 IOC layer.

## Reference facts (verified 2026-07-12)

- Current flyer contract (`src/lightfall_pystxmcontrol/flyer.py:24-25,66-82`): class constants `X_DATA_KEY="SampleX"`, `Y_DATA_KEY="SampleY"`; `describe_collect()` returns `{"primary": {X: array[nx], Y: number, <name>: array[nx]}}`; `collect()` yields ONE dict `{"time", "data": {X: ndarray, Y: float, name: ndarray}, "timestamps": {...}}`. Plans call `flyer.prepare(y=…, x_start=…, x_stop=…, nx=…, dwell=…)` synchronously, then `bps.kickoff(flyer, wait=True)` / `bps.complete(flyer, wait=True)` / `bps.collect(flyer)` (`plans.py:13-19`).
- `plan_plugin.py:23`: `FLYER_DEVICE_CLASS = f"{PystxmLineFlyer.__module__}.{PystxmLineFlyer.__name__}"` — follows whatever class it imports; keep this pattern with the new class.
- happi backend: `plugin.py` points at packaged `pystxm_happi.json`; `tests/test_plugin_backend.py` asserts device-name set `{"SampleX","SampleY","Counter1","STXMLineFlyer","energy"}` — keep these names.
- Spec-#2 IOC surface (all PVs relative to prefixes below; sim station `SIM`): motor records `STXMSIM:E712:SampleX` etc. (`.VAL` put-completion = move done, `.RBV/.DMOV/.STOP/.HLM/.LLM`); FLY group `STXMSIM:E712:FLY:{START,STOP,NPOINTS,DWELL,AXIS,MODE,ARM,GO,ABORT,STATE,ERROR,INDEX,POS,DATA:<daqkey>}` — ARM put validates (STATE→ARMED(1) or ERROR(3) + `:ERROR` text), GO put-completion = line done, INDEX write-then-increment contract, STATE enum strings `IDLE/ARMED/FLYING/ERROR`; DAQ group `STXMSIM:DEFAULT:{DWELL,MODE,ACQUIRE,COUNTS,COUNTS:WF,RATE}` with ACQUIRE put-completion. Supervisor `plan_fleet(fleet, slice_dir)` returns ordered `IocPlan(name, module, slice_path, delay)`; when an E712 group exists it absorbs ALL daq entries (no standalone daq IOC) and raises on >1 E712 group.
- `pystxmcontrol.iocs.config.load_fleet(motor_json, daq_json, station) -> FleetConfig` with `motor_pv: dict[key -> full PV]`, `daqs[i].prefix`, `controller_groups[i].label`. E712 label for a single E712 controller = `"E712"`; fly prefix = `STXM{station}:{label}:FLY`; daq prefix = `STXM{station}:{KEY.upper()}`.
- Spec-#2 test fixture pattern to copy (from `_pystxmcontrol_iocs_wt/tests/iocs/conftest.py`): `_free_udp_port()` random 40000-60000 bind-test; spawn `sys.executable -m <module> --slice <path> --quiet` with per-child `EPICS_CAS_SERVER_PORT` **and** `EPICS_CA_SERVER_PORT` (caproto server binds via the latter — spec-#2 verified), accumulated `EPICS_CA_ADDR_LIST` in `os.environ` AND every child env, `EPICS_CA_AUTO_ADDR_LIST=NO`, `PYTHONPATH` including the iocs worktree; ~3 s startup sleep; terminate/kill in teardown.
- ophyd classic: `EpicsMotor(prefix, name=…)` renames `user_readback` to the device name (read key = name). `EpicsSignal(..., put_complete=True)`: `set()` returns a Status completed on CA put-callback. `Cpt = ophyd.Component`.
- The lightfall venv (3.14) has: ophyd 1.11.1, caproto 1.3.0, netifaces, bluesky 1.14.6, happi, pipython/matplotlib/pylibftdi, lightfall (editable), lightfall_pystxmcontrol (editable → MAIN checkout — hence PYTHONPATH discipline in the worktree).

## File structure (final)

```
src/lightfall_pystxmcontrol/sim_motor.json    # packaged sim fleet config (David's format)
src/lightfall_pystxmcontrol/sim_daq.json
src/lightfall_pystxmcontrol/devices.py        # StxmCounter (EpicsSignal device) — old classes deleted
src/lightfall_pystxmcontrol/flyer.py          # StxmLineFlyer (EpicsSignal flyer) — rewritten
src/lightfall_pystxmcontrol/epics_env.py      # OPHYD_CONTROL_LAYER guard helper
src/lightfall_pystxmcontrol/config.py         # sim-JSON path helpers only (factories deleted)
src/lightfall_pystxmcontrol/plan_plugin.py    # import swap (FLYER_DEVICE_CLASS follows)
src/lightfall_pystxmcontrol/pystxm_happi.json # regenerated
scripts/build_pystxm_happi_db.py              # rewritten over load_fleet
tests/conftest.py                             # + iocs-src bootstrap, ports, fleet fixture
tests/test_devices_epics.py                   # StxmCounter unit tests (replaces test_counter.py)
tests/test_flyer_epics.py                     # StxmLineFlyer unit tests (replaces test_flyer*.py)
tests/test_e2e_plans_epics.py                 # RunEngine e2e over the fleet (replaces test_fly_raster/test_energy_stack_plan sim paths)
README.md / docs updates                      # sim workflow = stxm-iocs
```

---

### Task 1: Worktree, sim fleet JSONs, EPICS test infrastructure

**Files:**
- Create: worktree `.worktrees/epics-migration` (branch `feature/epics-migration`)
- Create: `src/lightfall_pystxmcontrol/sim_motor.json`, `src/lightfall_pystxmcontrol/sim_daq.json`
- Create: `src/lightfall_pystxmcontrol/epics_env.py`
- Modify: `src/lightfall_pystxmcontrol/config.py` (ADD path helpers; leave old factories in place until Task 4 deletes them)
- Modify: `tests/conftest.py` (append fixtures; keep existing `fake_ipc`)
- Test: `tests/test_epics_fixture.py`

**Interfaces:**
- Produces:
  - `config.sim_motor_json() -> str` / `config.sim_daq_json() -> str` — absolute paths to the packaged JSONs (via `importlib.resources.files("lightfall_pystxmcontrol")`).
  - `epics_env.ensure_caproto_layer() -> None` — `os.environ.setdefault("OPHYD_CONTROL_LAYER", "caproto")`; if `ophyd` is already imported with a different cl, call `ophyd.set_cl("caproto")`; also `import netifaces` and raise a clear ImportError if missing.
  - conftest fixtures: `iocs_src` (session; resolves `PYSTXMCONTROL_IOCS_SRC`, default `<repo>/_pystxmcontrol_iocs_wt`, `pytest.fail` if missing, `sys.path.insert(0, …)` so `pystxmcontrol.iocs` resolves to the spec-#2 worktree), `ca_ports` (accumulating port allocator), `stxm_fleet` (session-scoped: `plan_fleet` over the sim JSONs → spawn every IocPlan as a subprocess with per-IOC ports; yields a namespace with `.addr_list`, `.motor_pv`, `.fly_prefix`, `.daq_prefix`; teardown terminates all).
- Session-scoped fleet: ONE fleet for the whole test session (spawning ~4 IOCs takes seconds; per-test fleets would be minutes).

- [ ] **Step 1: Create worktree**

```bash
cd /c/Users/rp/PycharmProjects/ncs/lightfall-pystxmcontrol
git worktree add .worktrees/epics-migration -b feature/epics-migration main
```

All later steps run inside `.worktrees/epics-migration`; `$PY` = `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python`; test command prefix:

```bash
PYTHONPATH="$PWD/src" $PY -m pytest …
```

Confirm `.worktrees/` is ignored: `grep -q '^\.worktrees/' .gitignore || echo ".worktrees/" >> .gitignore` (commit the gitignore line with Task 1 if added).

- [ ] **Step 2: Write the sim fleet JSONs**

`src/lightfall_pystxmcontrol/sim_motor.json` — David's format, chosen so the fleet runs on Windows (E712 + XPS sim only; NO mcl/bcs entries):

```json
{
    "SampleX": {
        "index": 0, "type": "primary", "axis": "x", "driver": "E712Motor",
        "controllerID": "192.168.1.201", "port": 5000, "controller": "E712Controller",
        "max velocity": 1000.0, "minValue": -100.0, "maxValue": 100.0,
        "offset": 0.0, "units": 1.0, "display": true, "simulation": 1
    },
    "SampleY": {
        "index": 1, "type": "primary", "axis": "y", "driver": "E712Motor",
        "controllerID": "192.168.1.201", "port": 5000, "controller": "E712Controller",
        "max velocity": 1000.0, "minValue": -100.0, "maxValue": 100.0,
        "offset": 0.0, "units": 1.0, "display": true, "simulation": 1
    },
    "energy": {
        "index": 2, "type": "primary", "axis": "x", "driver": "xpsMotor",
        "controllerID": "192.168.1.254", "port": 0, "controller": "xpsController",
        "max velocity": 1000.0, "minValue": 250.0, "maxValue": 2500.0,
        "offset": 0.0, "units": 1.0, "display": true, "simulation": 1
    }
}
```

`src/lightfall_pystxmcontrol/sim_daq.json` (key `default` is load-bearing — the FLY data waveform is `FLY:DATA:default`):

```json
{
    "default": {
        "index": 0, "name": "Counter1", "type": "point", "driver": "keysight53230A",
        "address": "sim", "trigger_mode": "line", "measurement_mode": "TOT",
        "port": 5025, "channel": 1, "oversampling_factor": 1, "ndim": 0,
        "gate": false, "record": true, "simulation": true
    }
}
```

(`"gate": false` — no shutter IOC needed in the sim fleet.)

Resulting PVs (via `load_fleet(..., station="SIM")`): `STXMSIM:E712:SampleX`, `STXMSIM:E712:SampleY`, `STXMSIM:XPS:energy`, DAQ prefix `STXMSIM:DEFAULT`, FLY prefix `STXMSIM:E712:FLY` (daq absorbed into the E712 slice by `plan_fleet`).

- [ ] **Step 3: Write `epics_env.py` and config path helpers**

`src/lightfall_pystxmcontrol/epics_env.py`:

```python
"""EPICS transport guard: classic ophyd over caproto's control layer.

Must run before any ophyd import. netifaces is REQUIRED — it is an optional
caproto dependency, but CA address-list discovery breaks without it.
"""
import os
import sys


def ensure_caproto_layer() -> None:
    try:
        import netifaces  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "netifaces is required for the EPICS transport "
            "(optional caproto dep; pip install netifaces)") from exc
    os.environ.setdefault("OPHYD_CONTROL_LAYER", "caproto")
    if "ophyd" in sys.modules:  # imported before us with another layer?
        import ophyd
        if getattr(ophyd, "cl", None) is not None and ophyd.cl.name != "caproto":
            ophyd.set_cl("caproto")
```

Append to `src/lightfall_pystxmcontrol/config.py` (do not delete anything yet):

```python
from importlib.resources import files as _files


def sim_motor_json() -> str:
    """Absolute path to the packaged sim fleet motor config."""
    return str(_files("lightfall_pystxmcontrol") / "sim_motor.json")


def sim_daq_json() -> str:
    return str(_files("lightfall_pystxmcontrol") / "sim_daq.json")
```

- [ ] **Step 4: Write the conftest fixtures + failing fixture test**

Append to `tests/conftest.py`:

```python
# ---- EPICS fleet fixtures (spec #3) -------------------------------------
import os
import random
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_IOCS_SRC = Path(
    r"C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\_pystxmcontrol_iocs_wt")


@pytest.fixture(scope="session")
def iocs_src() -> Path:
    src = Path(os.environ.get("PYSTXMCONTROL_IOCS_SRC", _DEFAULT_IOCS_SRC))
    if not (src / "pystxmcontrol" / "iocs" / "supervisor.py").exists():
        pytest.fail(
            f"spec-#2 IOC layer not found at {src}. Set PYSTXMCONTROL_IOCS_SRC "
            "to the pystxmcontrol fork checkout (branch feature/caproto-iocs).")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return src


def _free_udp_port() -> int:
    for _ in range(50):
        port = random.randint(40000, 60000)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free UDP port found")


@pytest.fixture(scope="session")
def stxm_fleet(iocs_src, tmp_path_factory):
    """Spawn the full sim IOC fleet (spec-#2 supervisor plan) once per session."""
    from lightfall_pystxmcontrol import config, epics_env
    epics_env.ensure_caproto_layer()
    from pystxmcontrol.iocs.config import load_fleet
    from pystxmcontrol.iocs.supervisor import plan_fleet

    slice_dir = tmp_path_factory.mktemp("stxm_slices")
    fleet = load_fleet(config.sim_motor_json(), config.sim_daq_json(), station="SIM")
    plans = plan_fleet(fleet, str(slice_dir))

    addr_entries: list[str] = []
    procs: list[subprocess.Popen] = []
    for plan in plans:
        port = _free_udp_port()
        addr_entries.append(f"127.0.0.1:{port}")
        env = dict(os.environ)
        env.update({
            "EPICS_CAS_SERVER_PORT": str(port),
            "EPICS_CA_SERVER_PORT": str(port),   # caproto server binds via this
            "EPICS_CA_ADDR_LIST": " ".join(addr_entries),
            "EPICS_CA_AUTO_ADDR_LIST": "NO",
            "PYTHONPATH": os.pathsep.join(
                [str(iocs_src), str(REPO_ROOT / "src")]),
        })
        procs.append(subprocess.Popen(
            [sys.executable, "-m", plan.module, "--slice", plan.slice_path,
             "--quiet"],
            env=env))
        time.sleep(0.5)

    addr_list = " ".join(addr_entries)
    os.environ["EPICS_CA_ADDR_LIST"] = addr_list
    os.environ["EPICS_CA_AUTO_ADDR_LIST"] = "NO"
    time.sleep(3.0)
    dead = [p.args for p in procs if p.poll() is not None]
    assert not dead, f"IOC(s) exited early: {dead}"

    e712_label = next(g.label for g in fleet.controller_groups
                      if g.controller_cls == "E712Controller")
    yield SimpleNamespace(
        addr_list=addr_list,
        motor_pv=fleet.motor_pv,
        fly_prefix=f"STXMSIM:{e712_label}:FLY",
        daq_prefix=fleet.daqs[0].prefix,
    )
    for p in procs:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
```

`tests/test_epics_fixture.py`:

```python
"""The sim fleet spawns and its PVs are reachable over real CA."""


def test_fleet_pvs_connect(stxm_fleet):
    from caproto.threading.client import Context
    ctx = Context()
    names = [
        stxm_fleet.motor_pv["SampleX"],
        stxm_fleet.motor_pv["SampleY"],
        stxm_fleet.motor_pv["energy"],
        f"{stxm_fleet.daq_prefix}:COUNTS",
        f"{stxm_fleet.fly_prefix}:STATE",
    ]
    pvs = ctx.get_pvs(*names, timeout=20)
    for pv in pvs:
        pv.wait_for_connection(timeout=20)
    assert all(pv.connected for pv in pvs)


def test_motor_pv_naming(stxm_fleet):
    assert stxm_fleet.motor_pv["SampleX"] == "STXMSIM:E712:SampleX"
    assert stxm_fleet.motor_pv["energy"] == "STXMSIM:XPS:energy"
    assert stxm_fleet.daq_prefix == "STXMSIM:DEFAULT"
    assert stxm_fleet.fly_prefix == "STXMSIM:E712:FLY"
```

- [ ] **Step 5: Run to verify failure**

Run: `PYTHONPATH="$PWD/src" $PY -m pytest tests/test_epics_fixture.py -v`
Expected: FAIL — `sim_motor_json` missing before Step 2/3 files exist, or fleet fixture errors. (Write test first, then Steps 2-4 files, then re-run.)

- [ ] **Step 6: Run until green**

Run: `PYTHONPATH="$PWD/src" $PY -m pytest tests/test_epics_fixture.py -v`
Expected: 2 PASS (~15 s including fleet startup).
Then confirm no regression: `PYTHONPATH="$PWD/src" $PY -m pytest tests -x -q --ignore=tests/test_epics_fixture.py` — the pre-existing suite must still pass untouched.

- [ ] **Step 7: Commit**

```bash
git add src/lightfall_pystxmcontrol/sim_motor.json src/lightfall_pystxmcontrol/sim_daq.json \
        src/lightfall_pystxmcontrol/epics_env.py src/lightfall_pystxmcontrol/config.py \
        tests/conftest.py tests/test_epics_fixture.py
git commit -m "feat(epics): sim fleet JSONs + session IOC-fleet test fixture over spec-#2 layer"
```

---

### Task 2: `StxmCounter` — EpicsSignal counter device

**Files:**
- Modify: `src/lightfall_pystxmcontrol/devices.py` (REPLACE contents — old `PystxmAxis`/`PystxmCounter` deleted here; Task 4 fixes the remaining importers)
- Test: `tests/test_devices_epics.py`
- Delete: `tests/test_counter.py`, `tests/test_axis.py`, `tests/test_energy_axis.py` (superseded: axes are stock EpicsMotor — covered in Tasks 4/5)

**Interfaces:**
- Produces: `devices.StxmCounter(prefix, *, name)` — classic `ophyd.Device`; components `dwell` (`:DWELL`, EpicsSignal, kind config), `acquire` (`:ACQUIRE`, EpicsSignal put_complete=True, kind omitted), `counts` (`:COUNTS`, EpicsSignalRO, kind hinted, renamed to the bare device name), `rate` (`:RATE`, EpicsSignalRO, normal). `trigger() -> Status` = `self.acquire.set(1)` (completes when the IOC finishes the acquisition). `read()` keys on the bare device name (old behavior).

- [ ] **Step 1: Write the failing tests**

`tests/test_devices_epics.py`:

```python
"""StxmCounter against the live sim DAQ IOC."""
import time

import pytest


@pytest.fixture(scope="module")
def counter(stxm_fleet):
    from lightfall_pystxmcontrol.devices import StxmCounter
    c = StxmCounter(stxm_fleet.daq_prefix, name="Counter1")
    c.wait_for_connection(timeout=20)
    return c


def test_trigger_completes_after_acquisition(counter):
    counter.dwell.set(150.0).wait(timeout=10)   # ms
    t0 = time.monotonic()
    st = counter.trigger()
    st.wait(timeout=30)
    assert time.monotonic() - t0 >= 0.13, "trigger returned before acquisition"
    assert st.success


def test_read_keys_on_device_name(counter):
    counter.dwell.set(5.0).wait(timeout=10)
    counter.trigger().wait(timeout=30)
    reading = counter.read()
    assert "Counter1" in reading
    assert reading["Counter1"]["value"] > 0
    desc = counter.describe()
    assert "Counter1" in desc


def test_counts_hinted(counter):
    assert "Counter1" in counter.hints.get("fields", [])
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH="$PWD/src" $PY -m pytest tests/test_devices_epics.py -v`
Expected: ImportError — `StxmCounter` doesn't exist.

- [ ] **Step 3: Replace `src/lightfall_pystxmcontrol/devices.py`**

```python
"""Classic-ophyd EPICS devices for the spec-#2 pystxmcontrol IOC layer.

Axes need no wrapper: they are stock ``ophyd.EpicsMotor`` instances created
straight from happi entries (the IOC motor record's .VAL put-completion makes
``move()`` block until the move is done).
"""
from . import epics_env

epics_env.ensure_caproto_layer()  # before any ophyd import

from ophyd import Component as Cpt  # noqa: E402
from ophyd import Device, EpicsSignal, EpicsSignalRO  # noqa: E402


class StxmCounter(Device):
    """Point-mode counter over the spec-#2 DAQ IOC group.

    ``trigger()`` puts 1 to :ACQUIRE with put-completion — the returned Status
    finishes when the IOC has completed the acquisition and updated :COUNTS.
    """

    dwell = Cpt(EpicsSignal, ":DWELL", kind="config")
    acquire = Cpt(EpicsSignal, ":ACQUIRE", put_complete=True, kind="omitted")
    counts = Cpt(EpicsSignalRO, ":COUNTS", kind="hinted")
    rate = Cpt(EpicsSignalRO, ":RATE", kind="normal")

    def __init__(self, prefix, *, name, **kwargs):
        super().__init__(prefix, name=name, **kwargs)
        # Read/describe key on the bare device name (matches the pre-EPICS
        # PystxmCounter behavior and the plans/viz expectations).
        self.counts.name = self.name

    def trigger(self):
        return self.acquire.set(1)
```

- [ ] **Step 4: Run until green**

Run: `PYTHONPATH="$PWD/src" $PY -m pytest tests/test_devices_epics.py -v`
Expected: 3 PASS. If `put_complete` behaves unexpectedly under the caproto layer, verify with a REPL against the live fleet before changing approach — the IOC side is proven; the pin point is ophyd's put-callback plumbing.

- [ ] **Step 5: Delete superseded tests, run their absence**

```bash
git rm tests/test_counter.py tests/test_axis.py tests/test_energy_axis.py
```
(Old `devices.py` classes are gone, so these can no longer import. Task 4 handles the remaining importers — `flyer.py` still imports `PystxmAxis` until Task 3 rewrites it; expect `tests/test_flyer*.py` etc. to be temporarily broken from this commit until Tasks 3-4. That is acceptable ONLY within this plan's sequence; note it in the commit message.)

- [ ] **Step 6: Commit**

```bash
git add src/lightfall_pystxmcontrol/devices.py tests/test_devices_epics.py
git rm -q tests/test_counter.py tests/test_axis.py tests/test_energy_axis.py 2>/dev/null || true
git commit -m "feat(epics): StxmCounter over DAQ IOC; drop ophyd-async axis/counter wrappers (flyer/plans fixed in follow-on tasks)"
```

---

### Task 3: `StxmLineFlyer` — EPICS flyer over the FLY PVGroup

**Files:**
- Modify: `src/lightfall_pystxmcontrol/flyer.py` (REPLACE contents)
- Test: `tests/test_flyer_epics.py`
- Delete: `tests/test_flyer.py`, `tests/test_flyer_keys.py`, `tests/test_backend_flyer.py` (superseded; backend-level flyer coverage returns in Task 4's happi tests + Task 5's e2e)

**Interfaces:**
- Consumes: FLY PVGroup surface (Reference facts) — GO put-completion = line done; INDEX write-then-increment.
- Produces: `flyer.StxmLineFlyer(prefix, *, name="STXMLineFlyer", daq_key="default")` — classic `ophyd.Device`, `Flyable + Collectable`:
  - class constants `X_DATA_KEY = "SampleX"`, `Y_DATA_KEY = "SampleY"` (unchanged — `plans.py` reads `flyer.X_DATA_KEY`).
  - `prepare(*, y, x_start, x_stop, nx, dwell)` — synchronous: puts START/STOP/NPOINTS/DWELL (each `.set(...).wait(timeout=10)`), puts ARM (put_complete, wait), then verifies STATE == "ARMED" else `RuntimeError` carrying the `:ERROR` text; stashes `y`, `nx`, and `index0 = index.get()`.
  - `kickoff() -> Status` — starts the GO put (`self._go_status = self.go.set(1)`, put_complete) and returns `NullStatus()` (the line is "kicked off" once the put is dispatched; completion is `complete()`'s business).
  - `complete() -> Status` — returns `self._go_status` (completes when the IOC finishes the line).
  - `collect()` — verifies `index.get() == index0 + 1` and STATE == "ARMED" (else `RuntimeError(error text)`, so a failed row emits no event — line atomicity preserved), then reads `:POS` and `:DATA:{daq_key}` and yields the SAME one-event dict as before.
  - `describe_collect()` — same shape as before with `"source"` strings `f"epics:{prefix}:POS"` / `"epics:y-setpoint"` / `f"epics:{prefix}:DATA:{daq_key}"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_flyer_epics.py`:

```python
"""StxmLineFlyer against the live sim E712 FLY IOC."""
import numpy as np
import pytest


@pytest.fixture(scope="module")
def flyer(stxm_fleet):
    from lightfall_pystxmcontrol.flyer import StxmLineFlyer
    fl = StxmLineFlyer(stxm_fleet.fly_prefix, name="Counter1")
    fl.wait_for_connection(timeout=20)
    return fl


def test_one_cycle_yields_one_line_event(flyer):
    nx = 6
    flyer.prepare(y=2.0, x_start=-3.0, x_stop=3.0, nx=nx, dwell=1.0)
    flyer.kickoff().wait(timeout=30)
    flyer.complete().wait(timeout=60)
    events = list(flyer.collect())
    assert len(events) == 1
    data = events[0]["data"]
    assert len(data["Counter1"]) == nx
    assert (np.asarray(data["Counter1"]) > 0).all()
    assert len(data["SampleX"]) == nx
    assert data["SampleX"][0] == pytest.approx(-3.0)
    assert data["SampleX"][-1] == pytest.approx(3.0)
    assert data["SampleY"] == pytest.approx(2.0)


def test_describe_collect_reports_arrays(flyer):
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0)
    desc = flyer.describe_collect()["primary"]
    assert desc["Counter1"]["dtype"] == "array"
    assert desc["Counter1"]["shape"] == [4]
    assert desc["SampleX"]["dtype"] == "array"
    assert desc["SampleX"]["shape"] == [4]
    assert desc["SampleY"]["dtype"] == "number"


def test_prepare_rejects_out_of_limit_line(flyer):
    with pytest.raises(RuntimeError, match="(?i)limit"):
        flyer.prepare(y=0.0, x_start=-5000.0, x_stop=1.0, nx=4, dwell=1.0)
    # recovery: a valid prepare works afterwards
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0)


def test_consecutive_rows_index_advances(flyer):
    for row, y in enumerate((0.0, 1.0)):
        flyer.prepare(y=y, x_start=-2.0, x_stop=2.0, nx=5, dwell=1.0)
        flyer.kickoff().wait(timeout=30)
        flyer.complete().wait(timeout=60)
        (event,) = list(flyer.collect())
        assert event["data"]["SampleY"] == pytest.approx(y)
        assert len(event["data"]["Counter1"]) == 5
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH="$PWD/src" $PY -m pytest tests/test_flyer_epics.py -v`
Expected: ImportError / TypeError — new class absent.

- [ ] **Step 3: Replace `src/lightfall_pystxmcontrol/flyer.py`**

```python
"""EPICS line flyer driving the spec-#2 FLY PVGroup (classic ophyd).

Per row: prepare() writes the line config and ARMs (validated IOC-side);
kickoff() dispatches the GO put (put-completion = line done); complete()
returns that put's Status; collect() verifies the INDEX increment (the IOC's
write-then-increment contract guarantees the waveforms are fresh once INDEX
moved) and emits ONE event with the same keys/shapes as the pre-EPICS flyer,
so contract.py, plans, and viz are untouched.
"""
import time as _time
from collections.abc import Iterator

import numpy as np
from bluesky.protocols import Collectable, Flyable

from . import epics_env

epics_env.ensure_caproto_layer()  # before any ophyd import

from ophyd import Component as Cpt  # noqa: E402
from ophyd import Device, EpicsSignal, EpicsSignalRO  # noqa: E402
from ophyd.status import Status  # noqa: E402

_DAQ_KEY = "default"  # sim_daq.json key; FLY data waveform is :DATA:{key}


def _null_status() -> Status:
    st = Status()
    st.set_finished()
    return st


class StxmLineFlyer(Device, Flyable, Collectable):
    X_DATA_KEY = "SampleX"
    Y_DATA_KEY = "SampleY"

    x_start = Cpt(EpicsSignal, ":START", kind="config")
    x_stop = Cpt(EpicsSignal, ":STOP", kind="config")
    npoints = Cpt(EpicsSignal, ":NPOINTS", kind="config")
    dwell = Cpt(EpicsSignal, ":DWELL", kind="config")
    arm = Cpt(EpicsSignal, ":ARM", put_complete=True, kind="omitted")
    go = Cpt(EpicsSignal, ":GO", put_complete=True, kind="omitted")
    abort = Cpt(EpicsSignal, ":ABORT", kind="omitted")
    state = Cpt(EpicsSignalRO, ":STATE", string=True, kind="omitted")
    error = Cpt(EpicsSignalRO, ":ERROR", string=True, kind="omitted")
    index = Cpt(EpicsSignalRO, ":INDEX", kind="omitted")
    pos = Cpt(EpicsSignalRO, ":POS", kind="omitted")
    data = Cpt(EpicsSignalRO, f":DATA:{_DAQ_KEY}", kind="omitted")

    def __init__(self, prefix, *, name="STXMLineFlyer", **kwargs):
        super().__init__(prefix, name=name, **kwargs)
        self._row = None
        self._index0 = None
        self._go_status = None

    # -- per-row protocol ---------------------------------------------------
    def prepare(self, *, y: float, x_start: float, x_stop: float,
                nx: int, dwell: float) -> None:
        for sig, value in ((self.x_start, float(x_start)),
                           (self.x_stop, float(x_stop)),
                           (self.npoints, int(nx)),
                           (self.dwell, float(dwell))):
            sig.set(value).wait(timeout=10)
        self.arm.set(1).wait(timeout=30)
        state = self.state.get()
        if state != "ARMED":
            raise RuntimeError(
                f"{self.name}: ARM failed (STATE={state}): {self.error.get()}")
        self._row = {"y": float(y), "nx": int(nx)}
        self._index0 = int(self.index.get())
        self._go_status = None

    def kickoff(self) -> Status:
        if self._row is None:
            raise RuntimeError(f"{self.name}: kickoff() before prepare()")
        self._go_status = self.go.set(1)  # put-completion == line done
        return _null_status()

    def complete(self) -> Status:
        if self._go_status is None:
            raise RuntimeError(f"{self.name}: complete() before kickoff()")
        return self._go_status

    # -- collection ----------------------------------------------------------
    def describe_collect(self) -> dict:
        nx = self._row["nx"]
        return {"primary": {
            self.X_DATA_KEY: {"source": f"epics:{self.prefix}:POS",
                              "dtype": "array", "shape": [nx]},
            self.Y_DATA_KEY: {"source": "epics:y-setpoint",
                              "dtype": "number", "shape": []},
            self.name: {"source": f"epics:{self.prefix}:DATA:{_DAQ_KEY}",
                        "dtype": "array", "shape": [nx]},
        }}

    def collect(self) -> Iterator[dict]:
        r = self._row
        idx = int(self.index.get())
        state = self.state.get()
        if idx != self._index0 + 1 or state != "ARMED":
            raise RuntimeError(
                f"{self.name}: line failed (INDEX {self._index0}->{idx}, "
                f"STATE={state}): {self.error.get()}")
        x = np.asarray(self.pos.get(), dtype=float)[: r["nx"]]
        counts = np.asarray(self.data.get(), dtype=float)[: r["nx"]]
        ts = _time.time()
        yield {
            "time": ts,
            "data": {self.X_DATA_KEY: x, self.Y_DATA_KEY: r["y"],
                     self.name: counts},
            "timestamps": {self.X_DATA_KEY: ts, self.Y_DATA_KEY: ts,
                           self.name: ts},
        }
```

**Implementer cautions:**
- `state = Cpt(..., string=True)` should return the enum string under the caproto layer; if it returns an index, compare against `STATES = ("IDLE","ARMED","FLYING","ERROR")` — pin with a REPL against the live fleet and adjust BOTH prepare and collect consistently.
- The IOC's ERROR PV is a char waveform reported as string; `error.get()` may return bytes — normalize with `str(...)`.
- If `EpicsSignal.set()` with `put_complete=True` under the caproto layer does not block on the server's async putter (i.e., `st.wait()` returns immediately), verify against `test_trigger_completes_after_acquisition`-style timing before working around; the DAQ counter test in Task 2 pins the same mechanism.

- [ ] **Step 4: Run until green**

Run: `PYTHONPATH="$PWD/src" $PY -m pytest tests/test_flyer_epics.py tests/test_devices_epics.py -v`
Expected: all PASS.

- [ ] **Step 5: Delete superseded flyer tests, commit**

```bash
git rm tests/test_flyer.py tests/test_flyer_keys.py tests/test_backend_flyer.py
git add src/lightfall_pystxmcontrol/flyer.py tests/test_flyer_epics.py
git commit -m "feat(epics): StxmLineFlyer drives the FLY PVGroup; identical collect contract"
```

---

### Task 4: happi DB over `load_fleet`, plan_plugin swap, delete sim factories

**Files:**
- Modify: `scripts/build_pystxm_happi_db.py` (REPLACE contents)
- Modify: `src/lightfall_pystxmcontrol/plan_plugin.py:17` (import swap only)
- Modify: `src/lightfall_pystxmcontrol/config.py` (DELETE `DEFAULT_AXES`, `DEFAULT_COUNTER`, `make_sim_motor`, `make_sim_counter`; keep the two path helpers)
- Regenerate: `src/lightfall_pystxmcontrol/pystxm_happi.json`
- Modify: `tests/test_happi_db.py`, `tests/test_happi_entry_shape.py`, `tests/test_plugin_backend.py`, `tests/test_plan_plugin.py` (expectations)
- Check/Modify: `src/lightfall_pystxmcontrol/scan_panel.py` and `tests/test_plugin_integration.py` for references to removed names (grep; update imports/constants only — no behavior changes)
- Delete: `scripts/smoke_gridscan.py`, `scripts/smoke_raw.py`, `scripts/smoke_getline.py`, `scripts/smoke_flyscan_lightfall.py`, `scripts/smoke_energy_stack.py` if they import the deleted factories (verify each with grep first; keep any that don't)

**Interfaces:**
- Consumes: `StxmCounter`, `StxmLineFlyer`, `config.sim_motor_json()/sim_daq_json()`, spec-#2 `load_fleet` (imported from `PYSTXMCONTROL_IOCS_SRC` — the build script takes `--iocs-src` with the same default as conftest and does the same `sys.path.insert`).
- Produces: regenerated `pystxm_happi.json` with the SAME device names `{SampleX, SampleY, energy, Counter1, STXMLineFlyer}`; axes `device_class="ophyd.EpicsMotor"` `prefix=<motor_pv>`; counter `device_class="lightfall_pystxmcontrol.devices.StxmCounter"` `prefix="STXMSIM:DEFAULT"`; flyer `device_class="lightfall_pystxmcontrol.flyer.StxmLineFlyer"` `prefix="STXMSIM:E712:FLY"`. `FLYER_DEVICE_CLASS` becomes `"lightfall_pystxmcontrol.flyer.StxmLineFlyer"` automatically.

- [ ] **Step 1: Establish how the backend derives `category="motor"`**

Before touching tests: read `lightfall/devices/backends/happi.py` (lightfall venv source, `C:/Users/rp/PycharmProjects/ncs/lightfall/src/lightfall/devices/backends/happi.py`) and find how a happi item maps to `DeviceInfo.category`. The old `PystxmAxis` entries matched `DeviceFilter(category="motor")` (verified in the Phase-2b spike), so whatever drove that (device-class heuristics, kwargs, or an extra happi field) must be reproduced for `ophyd.EpicsMotor` entries. Record the mechanism in the report; if it's name/class-heuristic based, `EpicsMotor` almost certainly qualifies — write the Step-2 test to pin it.

- [ ] **Step 2: Update the failing tests first**

`tests/test_plugin_backend.py` — the name-set assertion stays IDENTICAL (names unchanged). Add a category pin:

```python
def test_axes_are_motor_category():
    plugin = PystxmBackendPlugin()
    backend = plugin.create_backend()
    backend.connect()
    by_name = {d.name: d for d in backend.list_devices(active_only=False)}
    for axis in ("SampleX", "SampleY", "energy"):
        assert "motor" in str(by_name[axis].category).lower()
```

`tests/test_happi_entry_shape.py` / `tests/test_happi_db.py`: update `device_class` expectations to `ophyd.EpicsMotor` / `lightfall_pystxmcontrol.devices.StxmCounter` / `lightfall_pystxmcontrol.flyer.StxmLineFlyer` and assert each entry's `prefix` equals the PV listed in the Interfaces block above (exact strings). `tests/test_plan_plugin.py`: `FLYER_DEVICE_CLASS == "lightfall_pystxmcontrol.flyer.StxmLineFlyer"`.

- [ ] **Step 3: Run to verify failures**

Run: `PYTHONPATH="$PWD/src" $PY -m pytest tests/test_happi_db.py tests/test_happi_entry_shape.py tests/test_plugin_backend.py tests/test_plan_plugin.py -v`
Expected: FAIL on old device_class strings/DB contents.

- [ ] **Step 4: Rewrite `scripts/build_pystxm_happi_db.py`**

```python
"""Generate pystxm_happi.json from the packaged sim fleet JSONs.

PV prefixes come from spec #2's fleet model (pystxmcontrol.iocs.config), so
naming can never drift between the IOCs and this plugin. Re-run + commit the
JSON after changing sim_motor.json/sim_daq.json.

    <lightfall-venv>/python scripts/build_pystxm_happi_db.py [--station SIM]
        [--iocs-src <pystxmcontrol fork checkout>]
"""
import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_IOCS_SRC = Path(
    r"C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\_pystxmcontrol_iocs_wt")
OUT = (Path(__file__).resolve().parents[1]
       / "src" / "lightfall_pystxmcontrol" / "pystxm_happi.json")


def build(station: str, iocs_src: Path) -> None:
    if str(iocs_src) not in sys.path:
        sys.path.insert(0, str(iocs_src))
    import happi
    from happi.backends.json_db import JSONBackend
    from pystxmcontrol.iocs.config import load_fleet

    from lightfall_pystxmcontrol import config

    fleet = load_fleet(config.sim_motor_json(), config.sim_daq_json(),
                       station=station)
    e712_label = next(g.label for g in fleet.controller_groups
                      if g.controller_cls == "E712Controller")

    OUT.write_text(json.dumps({}))
    client = happi.Client(database=JSONBackend(str(OUT)))

    for key, pv in fleet.motor_pv.items():
        client.add_item(happi.OphydItem(
            name=key, device_class="ophyd.EpicsMotor",
            args=[], prefix=pv, kwargs={"name": "{{name}}"}, active=True))

    client.add_item(happi.OphydItem(
        name="Counter1",
        device_class="lightfall_pystxmcontrol.devices.StxmCounter",
        args=[], prefix=fleet.daqs[0].prefix,
        kwargs={"name": "{{name}}"}, active=True))

    client.add_item(happi.OphydItem(
        name="STXMLineFlyer",
        device_class="lightfall_pystxmcontrol.flyer.StxmLineFlyer",
        args=[], prefix=f"STXM{station}:{e712_label}:FLY",
        kwargs={"name": "{{name}}"}, active=True))

    print(f"Wrote {OUT} ({len(client.search())} devices)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--station", default="SIM")
    p.add_argument("--iocs-src", default=os.environ.get(
        "PYSTXMCONTROL_IOCS_SRC", str(DEFAULT_IOCS_SRC)))
    a = p.parse_args()
    build(a.station, Path(a.iocs_src))
```

Note: if Step 1 found that `category="motor"` needs an explicit happi field (e.g. `OphydItem` extra metadata or a different container class), add it to the axis `add_item` calls per the discovered mechanism — do not invent a field name; use exactly what `HappiBackend` reads.

- [ ] **Step 5: Regenerate the DB, swap the plan_plugin import, prune config.py**

```bash
PYTHONPATH="$PWD/src" $PY scripts/build_pystxm_happi_db.py
```

`plan_plugin.py:17`: `from .flyer import PystxmLineFlyer` → `from .flyer import StxmLineFlyer` and `FLYER_DEVICE_CLASS = f"{StxmLineFlyer.__module__}.{StxmLineFlyer.__name__}"` (line 23). Nothing else in the file changes.

`config.py`: delete `DEFAULT_AXES`, `DEFAULT_COUNTER`, `make_sim_motor`, `make_sim_counter`; module docstring becomes `"""Paths to the packaged sim fleet configs (see spec #3)."""`; keep only the two helpers.

Grep-and-fix remaining importers:

```bash
grep -rn "make_sim_\|PystxmAxis\|PystxmCounter\|PystxmLineFlyer\|DEFAULT_AXES\|DEFAULT_COUNTER" src scripts tests --include=*.py
```
- `scan_panel.py`: update any import/constant reference (expected: none or FLYER_DEVICE_CLASS only — verify).
- `tests/test_plugin_integration.py`, `tests/test_fly_raster.py`, `tests/test_grid_scan.py`, `tests/test_energy_stack_plan.py`, `tests/test_energy_stack_plugin.py`: those exercising plans with sim devices are rewritten/absorbed in Task 5 — for THIS task, only fix imports if trivially possible; otherwise `git rm` here and note that Task 5 restores the coverage (list each file you remove in the commit message).
- Smoke scripts that import deleted factories: `git rm` them (verify each with the grep first). `scripts/make_golden_fixture.py` is handled in Task 5.

- [ ] **Step 6: Run until green**

Run: `PYTHONPATH="$PWD/src" $PY -m pytest tests/test_happi_db.py tests/test_happi_entry_shape.py tests/test_plugin_backend.py tests/test_plan_plugin.py tests/test_devices_epics.py tests/test_flyer_epics.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/build_pystxm_happi_db.py src/lightfall_pystxmcontrol/pystxm_happi.json \
        src/lightfall_pystxmcontrol/plan_plugin.py src/lightfall_pystxmcontrol/config.py \
        tests/test_happi_db.py tests/test_happi_entry_shape.py tests/test_plugin_backend.py tests/test_plan_plugin.py
# plus any git rm'd files and scan_panel/integration edits from Step 5
git commit -m "feat(epics): happi DB generated from spec-#2 fleet model; EpicsMotor axes; sim factories deleted"
```

---

### Task 5: e2e — RunEngine plans over the fleet, contract validation, golden fixture script

**Files:**
- Create: `tests/test_e2e_plans_epics.py`
- Modify: `scripts/make_golden_fixture.py` (rewrite to use the fleet + new flyer; the COMMITTED golden fixture file is NOT regenerated)
- Restore coverage removed in Task 4 (fly-raster/energy-stack plan behavior)

**Interfaces:**
- Consumes: `stxm_fleet` fixture, `StxmLineFlyer`, `ophyd.EpicsMotor`, `plans.stxm_fly_raster`/`stxm_energy_stack`, `contract.validate_run_documents`.

- [ ] **Step 1: Write the failing e2e tests**

`tests/test_e2e_plans_epics.py`:

```python
"""RunEngine e2e: plans over the live sim fleet; contract v1 must hold."""
import numpy as np
import pytest


@pytest.fixture(scope="module")
def devices(stxm_fleet):
    from ophyd import EpicsMotor
    from lightfall_pystxmcontrol.flyer import StxmLineFlyer
    y = EpicsMotor(stxm_fleet.motor_pv["SampleY"], name="SampleY")
    energy = EpicsMotor(stxm_fleet.motor_pv["energy"], name="energy")
    flyer = StxmLineFlyer(stxm_fleet.fly_prefix, name="Counter1")
    for d in (y, energy, flyer):
        d.wait_for_connection(timeout=30)
    return {"y": y, "energy": energy, "flyer": flyer}


def _run(plan):
    from bluesky import RunEngine
    docs = []
    RE = RunEngine({})
    RE(plan, lambda name, doc: docs.append((name, doc)))
    return docs


def test_fly_raster_end_to_end(devices):
    from lightfall_pystxmcontrol.plans import stxm_fly_raster
    ny, nx = 4, 8
    docs = _run(stxm_fly_raster(
        devices["flyer"], devices["y"],
        y_start=-2.0, y_stop=2.0, ny=ny,
        x_start=-3.0, x_stop=3.0, nx=nx, dwell=1.0))
    names = [n for n, _ in docs]
    assert names[0] == "start" and names[-1] == "stop"
    events = [d for n, d in docs if n == "event"]
    assert len(events) == ny
    for ev in events:
        assert len(ev["data"]["Counter1"]) == nx
        assert len(ev["data"]["SampleX"]) == nx
        assert (np.asarray(ev["data"]["Counter1"]) > 0).all()
    ys = [ev["data"]["SampleY"] for ev in events]
    assert ys == sorted(ys)
    (_, stop_doc) = docs[-1]
    assert stop_doc["exit_status"] == "success"


def test_energy_stack_end_to_end_contract(devices):
    from lightfall_pystxmcontrol import contract
    from lightfall_pystxmcontrol.plans import stxm_energy_stack
    energies = [400.0, 401.0]
    ny, nx = 3, 5
    docs = _run(stxm_energy_stack(
        devices["flyer"], devices["energy"], devices["y"],
        energies=energies, y_start=-1.0, y_stop=1.0, ny=ny,
        x_start=-2.0, x_stop=2.0, nx=nx, dwell_ms=1.0))
    events = [d for n, d in docs if n == "event"]
    assert len(events) == len(energies) * ny
    contract.validate_run_documents(docs)


def test_slow_axis_actually_moved(devices, stxm_fleet):
    """The RunEngine's bps.mv drives the real motor record."""
    from caproto.threading.client import Context
    ctx = Context()
    (rbv,) = ctx.get_pvs(stxm_fleet.motor_pv["SampleY"] + ".RBV")
    rbv.wait_for_connection(timeout=15)
    from lightfall_pystxmcontrol.plans import stxm_fly_raster
    _run(stxm_fly_raster(devices["flyer"], devices["y"],
                         y_start=0.0, y_stop=4.0, ny=2,
                         x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0))
    assert abs(rbv.read().data[0] - 4.0) < 1e-3
```

(Check `contract.validate_run_documents`'s exact signature in `contract.py` before running — if it takes `(start, descriptors, events, stop)` or similar rather than the raw doc list, adapt the call; the assertion intent is unchanged.)

- [ ] **Step 2: Run to verify failure** — new file collects, tests fail/error until the plumbing is right.

- [ ] **Step 3: Iterate until green**

Run: `PYTHONPATH="$PWD/src" $PY -m pytest tests/test_e2e_plans_epics.py -v`
Expected: 3 PASS. Common pin points: EpicsMotor needs the fleet's addr-list env (session fixture already set `os.environ`); RunEngine runs plans in its own thread — classic ophyd is thread-safe here (same pattern as beamline use).

- [ ] **Step 4: Rewrite `scripts/make_golden_fixture.py`**

Replace its device construction with: spawn nothing — document at top that it now REQUIRES a running sim fleet (`stxm-iocs`-style or the test fixture), construct `StxmLineFlyer(fly_prefix, name="Counter1")` + `EpicsMotor`s from the same PV names as the happi DB, and keep the rest of the fixture-writing logic unchanged. Do NOT regenerate the committed fixture file. Verify the script at least imports: `PYTHONPATH="$PWD/src" $PY -c "import scripts.make_golden_fixture" 2>/dev/null || PYTHONPATH="$PWD/src" $PY -X importtime scripts/make_golden_fixture.py --help` (adapt to the script's actual arg surface; an import/`--help` sanity check is enough).

- [ ] **Step 5: Contract guard + full suite**

Run: `PYTHONPATH="$PWD/src" $PY -m pytest tests/test_contract.py tests/test_golden_fixture.py -v` — MUST pass unchanged (frozen contract).
Then: `PYTHONPATH="$PWD/src" $PY -m pytest tests -v` — everything green.

- [ ] **Step 6: Commit**

```bash
git add tests/test_e2e_plans_epics.py scripts/make_golden_fixture.py
git commit -m "test(epics): RunEngine e2e over the sim fleet; contract v1 validated end-to-end"
```

---

### Task 6: Docs — sim workflow, README, env requirements

**Files:**
- Modify: `README.md` (or the repo's top-level usage doc — locate the section describing sim usage/demo)
- Modify: `NOTES-environment.md` (append spec-#3 env facts)

- [ ] **Step 1: Update README**

Replace the in-process-sim instructions with the EPICS workflow (transcribe, don't invent — verify each command):

```
## Simulated STXM (EPICS)

1. Start the sim IOC fleet (spec #2 layer, pystxmcontrol fork):
   PYTHONPATH=<pystxmcontrol-fork> python -m pystxmcontrol.iocs.supervisor \
       --station SIM \
       --motor-config src/lightfall_pystxmcontrol/sim_motor.json \
       --daq-config   src/lightfall_pystxmcontrol/sim_daq.json
   The supervisor prints an EPICS_CA_ADDR_LIST line (per-IOC ports) and writes
   it to <slice_dir>/EPICS_CA_ADDR_LIST.txt — export it for any client,
   including Lightfall.
2. Environment: OPHYD_CONTROL_LAYER=caproto (set automatically on plugin
   import), netifaces installed (REQUIRED — optional caproto dep, breaks
   without it), EPICS_CA_AUTO_ADDR_LIST=NO plus the addr list above.
3. Start Lightfall; the pystxmcontrol backend connects over CA.
Tests: PYTHONPATH=src <lightfall-venv-python> -m pytest tests  (spawns its own
fleet; needs PYSTXMCONTROL_IOCS_SRC or the default fork worktree present).
```

Note the hardware path: regenerate the happi DB with `--station 7011` + real motor/daq JSONs (follow-up; not in this repo yet).

- [ ] **Step 2: Append env facts to NOTES-environment.md**

One short section: netifaces installed 2026-07-12 (REQUIRED); OPHYD_CONTROL_LAYER=caproto; tests depend on `PYSTXMCONTROL_IOCS_SRC` (default `_pystxmcontrol_iocs_wt`) until spec #2 merges; session-scoped fleet fixture spawns ~4 IOC subprocesses on random ports.

- [ ] **Step 3: Commit**

```bash
git add README.md NOTES-environment.md
git commit -m "docs(epics): sim workflow via stxm-iocs; netifaces + env requirements"
```

---

### Task 7: Whole-branch verification

- [ ] **Step 1: Full suite twice, fresh shell**

```bash
cd /c/Users/rp/PycharmProjects/ncs/lightfall-pystxmcontrol/.worktrees/epics-migration
PYTHONPATH="$PWD/src" C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests -v
```
Run twice; all PASS both times (fleet fixture stability). Zero skips.

- [ ] **Step 2: Grep for stragglers**

```bash
grep -rn "make_sim_\|PystxmAxis\|PystxmCounter\|PystxmLineFlyer\|DEFAULT_AXES\|DEFAULT_COUNTER\|ophyd_async" src scripts tests --include=*.py
```
Expected: no hits in `src/` (except any deliberate `ophyd_async` usage that survived — there should be none). Fix anything found.

- [ ] **Step 3: Manual smoke (once, ~2 min)**

Start the fleet per the README instructions, then in a second shell (with the printed addr list + `EPICS_CA_AUTO_ADDR_LIST=NO`):

```bash
PYTHONPATH="$PWD/src" $PY -c "
from lightfall_pystxmcontrol import epics_env; epics_env.ensure_caproto_layer()
from ophyd import EpicsMotor
from lightfall_pystxmcontrol.flyer import StxmLineFlyer
from lightfall_pystxmcontrol.plans import stxm_fly_raster
from bluesky import RunEngine
y = EpicsMotor('STXMSIM:E712:SampleY', name='SampleY'); y.wait_for_connection(timeout=20)
fl = StxmLineFlyer('STXMSIM:E712:FLY', name='Counter1'); fl.wait_for_connection(timeout=20)
n = []
RunEngine({})(stxm_fly_raster(fl, y, y_start=-2, y_stop=2, ny=3, x_start=-2, x_stop=2, nx=6, dwell=1.0),
              lambda nm, d: n.append(nm))
print('docs:', n); assert n.count('event') == 3; print('manual smoke OK')"
```

- [ ] **Step 4:** superpowers:requesting-code-review (whole branch) → superpowers:finishing-a-development-branch. Branch stays LOCAL. Named follow-ups: hardware (7011) happi DB + real motor/daq configs; repoint tests/`hardware` extra when spec #2 merges; scan-panel UX for the addr-list env.

---

## Self-review notes

- Spec §2.1/§3.1 EpicsMotor axes → Task 4 (happi only) + Task 5 e2e. §3.2 counter → Task 2. §3.3 flyer → Task 3 (identical collect contract; `FLYER_DEVICE_CLASS` follows the class per §3.3). §2.2 transport + netifaces → Task 1 `epics_env` + Global Constraints. §2.3 EPICS-only/sim=stxm-iocs → Tasks 1 (fleet fixture), 4 (factories deleted), 6 (README). §4 happi via load_fleet → Task 4. §5 workflow → Task 6. §6 unit/e2e/env → Tasks 2/3/5, `PYSTXMCONTROL_IOCS_SRC` fail-loudly in Task 1. §7 non-goals respected (no scan-panel behavior changes; only import fixes).
- Known intra-plan breakage window: Tasks 2-4 intentionally leave some old tests broken mid-sequence; each task's commit message names it, and Task 4 Step 5 / Task 5 restore or replace all coverage. Task 7 Step 2 guards against stragglers.
- Type consistency checked: `StxmCounter(prefix, *, name)`, `StxmLineFlyer(prefix, *, name)`, `prepare(*, y, x_start, x_stop, nx, dwell)`, `config.sim_motor_json()`, fixture attrs `.motor_pv/.fly_prefix/.daq_prefix/.addr_list` used identically across Tasks 1-5.
