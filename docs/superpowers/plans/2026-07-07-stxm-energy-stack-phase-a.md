# STXM Energy Stack (Option-5 Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Phase A vertical slice of the option-5 design (spec: `docs/superpowers/specs/2026-07-07-stxm-lightfall-option5-design.md`): sim energy axis → `stxm_energy_stack` plan → Tiled → STXM scan-definition panel + live stack visualization in Lightfall.

**Architecture:** Everything lands in this repo (`lightfall-pystxmcontrol`); zero lightfall-core changes, zero changes to David's pystxmcontrol. A new `contract.py` module is the single normative implementation of the spec's §4 Tiled run-layout contract (start-doc `stxm` block, `(iE, iy)` ordering, NaN-fill); the plan, the visualization, and the tests all import it. The panel and viz follow the existing repo idioms (`BasePanel`/`PanelPlugin`, `BaseVisualization`/`PluginType(type_name="visualization")`, happi-generated device DB).

**Tech Stack:** Python 3.10+, ophyd-async, bluesky 1.14.6, PySide6 + pyqtgraph, happi (JSON backend), Tiled client, pytest + pytest-qt.

## Global Constraints

- Run tests with the lightfall venv, never bare pytest:
  `QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest <path> -v`
  (bash: `export QT_QPA_PLATFORM=offscreen` first, or prefix per-command).
- If executing in a git worktree: editable installs resolve to the MAIN checkout — set `PYTHONPATH=src` (from repo root) for every pytest/python invocation or you silently test the wrong code.
- bluesky 1.14.6 paginates `collect` → documents are `event_page`, not `event`; per-event arrays are `doc["data"][key][i]`.
- Dwell is MILLISECONDS end-to-end (spec §3.2). `flyer.prepare(dwell=...)` already takes ms.
- Never subscribe to a scalar Tiled column facet (500s + hangs `start_in_thread`); live subscriptions are array nodes or the stream's `internal` table node only (spec §2.1 rule 5, enforced by core's `_resolve_active_node` — nothing in this plan subscribes manually except the smoke script, which subscribes to the flyer array node).
- The contract array order is `data[iE, iy, ix]`, C-order; `ix=0 ↔ x_extent[0]`, `iy=0 ↔ y_extent[0]`; descending extents legal (spec §4.1).
- No pystxmcontrol GUI imports; driver imports stay factory-local in `config.py` (spec §2.1).
- Commit after every task with the message given in the task.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `src/lightfall_pystxmcontrol/config.py` | modify | add `energy` axis to `DEFAULT_AXES` (eV-scale limits) |
| `src/lightfall_pystxmcontrol/pystxm_happi.json` | regenerate | device DB (gains `energy`, 5 entries) |
| `src/lightfall_pystxmcontrol/flyer.py` | modify | data-key class constants; fix colliding default name |
| `src/lightfall_pystxmcontrol/contract.py` | create | §4 contract: constants, start-doc builder, index decode, cube reshape, document validator |
| `src/lightfall_pystxmcontrol/plans.py` | modify | `_fly_rows` shared row machinery; `stxm_energy_stack`; extents in fly-raster md |
| `src/lightfall_pystxmcontrol/plan_plugin.py` | modify | `_stxm_energy_stack_ui` adapter + `StxmEnergyStackPlanPlugin` |
| `src/lightfall_pystxmcontrol/image_render.py` | create | `ImageRenderMixin` extracted from `stxm_map_viz.py` (updateImage + auto-LUT) |
| `src/lightfall_pystxmcontrol/stxm_map_viz.py` | modify | use `ImageRenderMixin` (behavior unchanged) |
| `src/lightfall_pystxmcontrol/stxm_stack_viz.py` | create | `StxmStackVisualization` + `StxmStackVizPlugin` |
| `src/lightfall_pystxmcontrol/energy_ranges.py` | create | energy-ranges model/expansion + editor widget |
| `src/lightfall_pystxmcontrol/scan_panel.py` | create | `STXMScanPanel` + `StxmScanPanelPlugin` |
| `src/lightfall_pystxmcontrol/manifest.py` | modify | +3 `PluginEntry` rows (plan, visualization, panel) |
| `scripts/make_golden_fixture.py` | create | regenerate the golden contract fixture |
| `scripts/smoke_energy_stack.py` | create | e2e smoke: BlueskyEngine + Tiled layout + live stack |
| `tests/test_energy_axis.py` | create | Task 2 tests |
| `tests/test_flyer_keys.py` | create | Task 3 tests |
| `tests/test_contract.py` | create | Task 4 tests |
| `tests/test_energy_stack_plan.py` | create | Task 5 tests |
| `tests/test_energy_stack_plugin.py` | create | Task 6 tests |
| `tests/fixtures/golden_energy_stack_run.json` | create | golden run documents (structure-validated) |
| `tests/test_golden_fixture.py` | create | Task 7 tests |
| `tests/test_stxm_stack_viz.py` | create | Tasks 9–10 tests |
| `tests/test_energy_ranges.py` | create | Task 11 tests |
| `tests/test_scan_panel.py` | create | Tasks 12–13 tests |

---

### Task 1: Base branch setup

**Files:** none (git only)

The dwell-unit work (`fix/stxm-dwell-unit-discovery`, one commit ahead) touches the same two files this plan extends (`plans.py`, `plan_plugin.py`) and its content is assumed by the code below (the `Unit("ms")` annotations). Merge it first so Phase A builds on it.

- [ ] **Step 1: Merge the dwell-unit branch into main**

```bash
cd C:/Users/rp/PycharmProjects/ncs/lightfall-pystxmcontrol
git checkout main
git merge fix/stxm-dwell-unit-discovery -m "Merge fix/stxm-dwell-unit-discovery: dwell unit surfaced in plan discovery"
```

Expected: fast-forward-ish merge, no conflicts (the branch only edits `plans.py`/`plan_plugin.py` docstrings/annotations; main's extra commits are docs).

- [ ] **Step 2: Create the feature branch**

```bash
git checkout -b feature/stxm-energy-stack
```

- [ ] **Step 3: Verify the suite is green before starting**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ -x -q
```

Expected: all tests PASS. If not, STOP and report — do not build on a red base.

---

### Task 2: Sim energy axis (config + happi DB)

**Files:**
- Modify: `src/lightfall_pystxmcontrol/config.py`
- Regenerate: `src/lightfall_pystxmcontrol/pystxm_happi.json` (via `scripts/build_pystxm_happi_db.py`)
- Test: `tests/test_energy_axis.py`

**Interfaces:**
- Produces: `config.DEFAULT_AXES["energy"]` — axis-config dict with `minValue=250.0, maxValue=2500.0` (eV). Happi DB entry `energy` (device_class `lightfall_pystxmcontrol.devices.PystxmAxis`). Later tasks reference the device name `"energy"`.

Spec §3.1. CRITICAL: `xpsMotor.moveTo` enforces `axis_config` soft limits **even in simulation** (`SoftwareLimitError`); a ±100 clone rejects eV setpoints.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_energy_axis.py
"""Task 2: sim energy axis — eV-scale limits, happi entry, movable in sim."""
import asyncio
import json
from importlib.resources import files

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmAxis


def test_energy_in_default_axes_with_ev_limits():
    cfg = config.DEFAULT_AXES["energy"]
    assert cfg["minValue"] == 250.0
    assert cfg["maxValue"] == 2500.0
    assert cfg["axis"] == "X"  # sim xpsMotor axis label; placeholder physics (spec §3.1)


def test_happi_db_has_energy_entry():
    db = json.loads(files("lightfall_pystxmcontrol").joinpath("pystxm_happi.json").read_text())
    assert "energy" in db, f"happi DB entries: {sorted(db)}"
    entry = db["energy"]
    assert entry["device_class"] == "lightfall_pystxmcontrol.devices.PystxmAxis"
    assert entry["kwargs"]["axis_config"]["minValue"] == 250.0
    assert entry["kwargs"]["axis_config"]["maxValue"] == 2500.0
    assert len(db) == 5  # SampleX, SampleY, Counter1, STXMLineFlyer, energy


def test_energy_axis_moves_to_ev_setpoint_in_sim():
    axis = PystxmAxis(config.DEFAULT_AXES["energy"], name="energy")

    async def _go():
        await axis.connect(mock=False)
        await axis.set(700.0)  # a realistic C-edge-ish eV value
        return await axis.readback.get_value()

    assert asyncio.run(_go()) == 700.0  # would raise SoftwareLimitError with ±100 limits
```

- [ ] **Step 2: Run it to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_energy_axis.py -v
```

Expected: FAIL — `KeyError: 'energy'` (config), missing happi entry.

- [ ] **Step 3: Add the axis to config.py**

In `src/lightfall_pystxmcontrol/config.py`, extend `DEFAULT_AXES`:

```python
DEFAULT_AXES = {
    "SampleX": {"axis": "X", "units": 1.0, "offset": 0.0,
                "minValue": -100.0, "maxValue": 100.0},
    "SampleY": {"axis": "Y", "units": 1.0, "offset": 0.0,
                "minValue": -100.0, "maxValue": 100.0},
    # Sim energy axis (spec §3.1): an energy-shaped Movable, NOT the real
    # derivedEnergy zone-plate physics (Phase B). eV-scale soft limits are
    # load-bearing: xpsMotor.moveTo raises SoftwareLimitError even in sim.
    "energy": {"axis": "X", "units": 1.0, "offset": 0.0,
               "minValue": 250.0, "maxValue": 2500.0},
}
```

- [ ] **Step 4: Regenerate the happi DB**

```bash
C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/build_pystxm_happi_db.py
```

Expected output: `Wrote .../pystxm_happi.json (5 devices)`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_energy_axis.py tests/test_happi_db.py tests/test_config.py -v
```

Expected: PASS (including the pre-existing happi/config tests — if `test_happi_db.py` asserts a device count of 4, update that assertion to 5 in this task).

- [ ] **Step 6: Commit**

```bash
git add src/lightfall_pystxmcontrol/config.py src/lightfall_pystxmcontrol/pystxm_happi.json tests/test_energy_axis.py tests/test_happi_db.py
git commit -m "feat: sim energy axis with eV-scale soft limits (Phase A, spec 3.1)"
```

---

### Task 3: Flyer data-key constants + default-name fix

**Files:**
- Modify: `src/lightfall_pystxmcontrol/flyer.py`
- Test: `tests/test_flyer_keys.py`

**Interfaces:**
- Produces: `PystxmLineFlyer.X_DATA_KEY = "SampleX"`, `PystxmLineFlyer.Y_DATA_KEY = "SampleY"` (class attrs naming the hardcoded event keys), and default `name="STXMLineFlyer"` (was `"Counter1"`, colliding with the counter device's field — spec §4.1).
- Consumed by: Task 5 (plan records `x_motor=flyer.X_DATA_KEY`), Task 14 (smoke).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_flyer_keys.py
"""Task 3: flyer data-key constants + non-colliding default name."""
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
from lightfall_pystxmcontrol import config


def test_data_key_class_constants():
    assert PystxmLineFlyer.X_DATA_KEY == "SampleX"
    assert PystxmLineFlyer.Y_DATA_KEY == "SampleY"


def test_default_name_matches_happi_entry_not_counter():
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"])
    assert flyer.name == "STXMLineFlyer"  # was "Counter1" — collided with the counter device


def test_describe_collect_uses_constants():
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"])
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0)
    desc = flyer.describe_collect()["primary"]
    assert set(desc) == {PystxmLineFlyer.X_DATA_KEY, PystxmLineFlyer.Y_DATA_KEY, "STXMLineFlyer"}
```

- [ ] **Step 2: Run it to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_flyer_keys.py -v
```

Expected: FAIL — `AttributeError: X_DATA_KEY`, name == "Counter1".

- [ ] **Step 3: Implement in flyer.py**

In `src/lightfall_pystxmcontrol/flyer.py`: add class constants, change the default name, and use the constants in `describe_collect`/`collect` (pure refactor of the hardcoded strings):

```python
class PystxmLineFlyer(Flyable, Collectable):
    # Event data keys for the derived fast-axis positions and the slow-axis
    # setpoint. These are the literal keys emitted in collect(); the plan
    # records X_DATA_KEY as the contract's x_motor (spec §4.1 provenance).
    X_DATA_KEY = "SampleX"
    Y_DATA_KEY = "SampleY"

    def __init__(self, daq_config: dict, x_axis_config: dict, name: str = "STXMLineFlyer"):
```

In `describe_collect`, replace the three literal keys:

```python
    def describe_collect(self) -> dict:
        nx = self._row["nx"]
        return {"primary": {
            self.X_DATA_KEY: {"source": "sim:linspace", "dtype": "array", "shape": [nx]},
            self.Y_DATA_KEY: {"source": "sim:y", "dtype": "number", "shape": []},
            self._name: {"source": "sim:getLine", "dtype": "array", "shape": [nx]},
        }}
```

In `collect`, likewise:

```python
    def collect(self) -> Iterator[dict]:
        r = self._row
        x = np.linspace(r["x_start"], r["x_stop"], r["nx"])
        ts = _time.time()
        yield {
            "time": ts,
            "data": {self.X_DATA_KEY: x, self.Y_DATA_KEY: r["y"], self._name: self._counts},
            "timestamps": {self.X_DATA_KEY: ts, self.Y_DATA_KEY: ts, self._name: ts},
        }
```

- [ ] **Step 4: Run the full suite (the default-name change can touch existing tests)**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ -q
```

Expected: PASS. (Existing tests construct the flyer with an explicit `name=` so they are unaffected; if any relied on the old default, update them to pass `name="Counter1"` explicitly.)

- [ ] **Step 5: Commit**

```bash
git add src/lightfall_pystxmcontrol/flyer.py tests/test_flyer_keys.py
git commit -m "feat: flyer data-key constants; default name STXMLineFlyer (no Counter1 collision)"
```

---

### Task 4: `contract.py` — the normative §4 implementation

**Files:**
- Create: `src/lightfall_pystxmcontrol/contract.py`
- Test: `tests/test_contract.py`

**Interfaces:**
- Produces (all consumed by Tasks 5, 7, 9, 14):
  - `CONTRACT_VERSION = 1`, `PLAN_NAME_ENERGY_STACK = "stxm_energy_stack"`
  - `stxm_start_md(*, energies, ny, nx, dwell_ms, x_extent, y_extent, x_motor, y_motor, energy_motor, data_field) -> dict` — full start-doc md (top-level `plan_name`, `motors`, `detectors` + nested `stxm` block per spec §4.1)
  - `decode_line_index(row: int, ny: int) -> tuple[int, int]` — `(iE, iy) = divmod(row, ny)`; `row == seq_num - 1 == array push offset[0]` (spec §4.2)
  - `cube_from_rows(rows, shape) -> np.ndarray` — `(k, nx)` rows → `(nE, ny, nx)` cube, NaN-filled missing lines (spec §4.3)
  - `validate_run_documents(docs: list[tuple[str, dict]]) -> list[str]` — structural §4 check; empty list = valid

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_contract.py
"""Task 4: the normative Tiled run-layout contract (spec §4)."""
import numpy as np

from lightfall_pystxmcontrol import contract


def _md(nE=2, ny=3, nx=4):
    return contract.stxm_start_md(
        energies=[500.0 + 10 * i for i in range(nE)], ny=ny, nx=nx, dwell_ms=1.0,
        x_extent=[-5.0, 5.0], y_extent=[-2.0, 2.0],
        x_motor="SampleX", y_motor="SampleY", energy_motor="energy",
        data_field="STXMLineFlyer",
    )


def test_start_md_block():
    md = _md()
    assert md["plan_name"] == "stxm_energy_stack"
    s = md["stxm"]
    assert s["contract_version"] == 1
    assert s["shape"] == [2, 3, 4]
    assert s["energies"] == [500.0, 510.0]
    assert s["dwell_ms"] == 1.0
    assert s["x_extent"] == [-5.0, 5.0] and s["y_extent"] == [-2.0, 2.0]
    assert s["x_motor"] == "SampleX" and s["y_motor"] == "SampleY"
    assert s["energy_motor"] == "energy"
    assert s["data_field"] == "STXMLineFlyer"
    assert md["motors"] == ["energy", "SampleY"] and md["detectors"] == ["STXMLineFlyer"]


def test_decode_line_index():
    ny = 3
    assert contract.decode_line_index(0, ny) == (0, 0)
    assert contract.decode_line_index(2, ny) == (0, 2)
    assert contract.decode_line_index(3, ny) == (1, 0)
    assert contract.decode_line_index(5, ny) == (1, 2)


def test_cube_from_rows_full():
    rows = np.arange(6 * 4, dtype=float).reshape(6, 4)
    cube = contract.cube_from_rows(rows, (2, 3, 4))
    assert cube.shape == (2, 3, 4)
    assert np.array_equal(cube[0, 0], rows[0])
    assert np.array_equal(cube[1, 2], rows[5])
    assert not np.isnan(cube).any()


def test_cube_from_rows_partial_nan_fills_whole_lines():
    rows = np.ones((4, 4))  # 4 of 6 lines acquired
    cube = contract.cube_from_rows(rows, (2, 3, 4))
    assert not np.isnan(cube[0]).any()          # first energy complete
    assert not np.isnan(cube[1, 0]).any()       # E1 row 0 acquired
    assert np.isnan(cube[1, 1]).all()           # missing lines are whole-NaN (spec §4.2 atomicity)
    assert np.isnan(cube[1, 2]).all()


def test_cube_from_rows_empty():
    cube = contract.cube_from_rows(np.empty((0, 4)), (2, 3, 4))
    assert np.isnan(cube).all()


def _docs(nE=2, ny=3, nx=4, n_lines=None, exit_status="success"):
    """Minimal fabricated document stream in the contract layout."""
    n = nE * ny if n_lines is None else n_lines
    docs = [("start", {**_md(nE, ny, nx), "uid": "u1"})]
    for i in range(n):
        docs.append(("event_page", {
            "seq_num": [i + 1],
            "data": {"STXMLineFlyer": [list(np.ones(nx))],
                     "SampleX": [list(np.zeros(nx))], "SampleY": [0.0]},
        }))
    docs.append(("stop", {"exit_status": exit_status, "num_events": {"primary": n}}))
    return docs


def test_validate_ok():
    assert contract.validate_run_documents(_docs()) == []


def test_validate_flags_wrong_line_length():
    docs = _docs()
    docs[1][1]["data"]["STXMLineFlyer"] = [[1.0, 2.0]]  # nx=4 expected
    assert any("shape" in e or "length" in e for e in contract.validate_run_documents(docs))


def test_validate_flags_success_with_missing_lines():
    errors = contract.validate_run_documents(_docs(n_lines=4, exit_status="success"))
    assert errors, "successful run must have nE*ny events"


def test_validate_partial_run_is_valid_when_not_success():
    assert contract.validate_run_documents(_docs(n_lines=4, exit_status="fail")) == []


def test_validate_missing_stop_doc_is_valid_partial_run():
    # Spec §4.3: a missing stop doc is a valid partial run, same as a
    # non-success stop doc, as long as line count is within capacity.
    docs = [d for d in _docs(n_lines=4) if d[0] != "stop"]
    assert contract.validate_run_documents(docs) == []


def test_validate_missing_stop_doc_still_flags_over_capacity():
    docs = [d for d in _docs(n_lines=7) if d[0] != "stop"]  # nE*ny == 6
    errors = contract.validate_run_documents(docs)
    assert any("capacity" in e for e in errors)


def test_validate_flags_malformed_shape_wrong_length():
    docs = _docs()
    docs[0][1]["stxm"]["shape"] = [2, 3]
    errors = contract.validate_run_documents(docs)
    assert any("shape" in e for e in errors)


def test_validate_flags_malformed_shape_wrong_type():
    docs = _docs()
    docs[0][1]["stxm"]["shape"] = "2x3x4"
    errors = contract.validate_run_documents(docs)
    assert any("shape" in e for e in errors)


def test_validate_flags_event_missing_data_key():
    docs = [
        ("start", {**_md(nE=1, ny=2, nx=4), "uid": "u1"}),
        ("event_page", {"seq_num": [1]}),  # no "data" key at all
        ("event_page", {"seq_num": [2], "data": {"STXMLineFlyer": [list(np.ones(4))]}}),
        ("stop", {"exit_status": "fail", "num_events": {"primary": 1}}),
    ]
    errors = contract.validate_run_documents(docs)
    assert any("data" in e for e in errors)
```

- [ ] **Step 2: Run to verify failure**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_contract.py -v
```

Expected: FAIL — `ModuleNotFoundError: lightfall_pystxmcontrol.contract`.

- [ ] **Step 3: Implement contract.py**

```python
# src/lightfall_pystxmcontrol/contract.py
"""STXM Tiled run-layout contract v1 — the normative implementation of spec §4.

Single source of truth for the start-doc ``stxm`` block, the line-ordering
rule (seq_num = iE*ny + iy + 1; array push offset row == seq_num - 1), and
the NaN-fill rule for partial runs. The plan (producer), the stack
visualization (consumer), and the golden-fixture validator all import this
module; nothing else may re-encode these rules.

Spec: docs/superpowers/specs/2026-07-07-stxm-lightfall-option5-design.md §4.
"""
from __future__ import annotations

import numpy as np

CONTRACT_VERSION = 1
PLAN_NAME_ENERGY_STACK = "stxm_energy_stack"


def stxm_start_md(*, energies, ny, nx, dwell_ms, x_extent, y_extent,
                  x_motor, y_motor, energy_motor, data_field) -> dict:
    """Build the full start-document metadata for an energy-stack run (§4.1)."""
    energies = [float(e) for e in energies]
    return {
        "plan_name": PLAN_NAME_ENERGY_STACK,
        "motors": [energy_motor, y_motor],
        "detectors": [data_field],
        "stxm": {
            "contract_version": CONTRACT_VERSION,
            "shape": [len(energies), int(ny), int(nx)],
            "energies": energies,
            "dwell_ms": float(dwell_ms),
            "x_extent": [float(x_extent[0]), float(x_extent[1])],
            "y_extent": [float(y_extent[0]), float(y_extent[1])],
            "x_motor": x_motor,
            "y_motor": y_motor,
            "energy_motor": energy_motor,
            "data_field": data_field,
        },
    }


def decode_line_index(row: int, ny: int) -> tuple[int, int]:
    """Map a 0-based line index (== seq_num - 1 == push offset row) to (iE, iy)."""
    return divmod(int(row), int(ny))


def cube_from_rows(rows, shape) -> np.ndarray:
    """Reshape a (k, nx) line-row array into an (nE, ny, nx) cube, NaN-filling
    unacquired lines (§4.3; lines are atomic per §4.2, so fill is whole-line)."""
    nE, ny, nx = (int(v) for v in shape)
    flat = np.full((nE * ny, nx), np.nan, dtype=float)
    rows = np.asarray(rows, dtype=float)
    if rows.ndim == 2 and rows.shape[1] == nx and rows.shape[0] > 0:
        k = min(rows.shape[0], nE * ny)
        flat[:k] = rows[:k]
    return flat.reshape(nE, ny, nx)


def validate_run_documents(docs: list[tuple[str, dict]]) -> list[str]:
    """Structurally validate a (name, doc) stream against contract v1.

    Returns a list of human-readable violations; empty means valid. This is
    the executable form of spec §4 used by the golden-fixture test and the
    smoke script.
    """
    errors: list[str] = []
    names = [n for n, _ in docs]
    if not names or names[0] != "start":
        return ["first document must be 'start'"]
    start = docs[0][1]
    s = start.get("stxm")
    if not isinstance(s, dict):
        return ["start doc has no 'stxm' block"]
    for key in ("contract_version", "shape", "energies", "dwell_ms", "x_extent",
                "y_extent", "x_motor", "y_motor", "energy_motor", "data_field"):
        if key not in s:
            errors.append(f"stxm block missing '{key}'")
    if errors:
        return errors
    if s["contract_version"] != CONTRACT_VERSION:
        errors.append(f"contract_version {s['contract_version']} != {CONTRACT_VERSION}")
    shape = s["shape"]
    if (not isinstance(shape, (list, tuple)) or len(shape) != 3
            or not all(isinstance(v, int) for v in shape)):
        errors.append(f"stxm block 'shape' must be a 3-int sequence, got {shape!r}")
        return errors
    nE, ny, nx = shape
    if len(s["energies"]) != nE:
        errors.append(f"len(energies)={len(s['energies'])} != nE={nE}")
    if start.get("plan_name") != PLAN_NAME_ENERGY_STACK:
        errors.append(f"plan_name {start.get('plan_name')!r} != {PLAN_NAME_ENERGY_STACK!r}")

    field = s["data_field"]
    seq = 0
    for name, doc in docs[1:]:
        if name not in ("event", "event_page"):
            continue
        data = doc.get("data")
        if not isinstance(data, dict):
            errors.append(f"{name} doc missing 'data'")
            continue
        seqs = doc["seq_num"] if isinstance(doc.get("seq_num"), list) else [doc.get("seq_num")]
        rows = data.get(field)
        if rows is None:
            errors.append(f"event data missing field {field!r}")
            continue
        if not isinstance(rows, list):  # bare event: single array
            rows = [rows]
        for sn, line in zip(seqs, rows):
            seq += 1
            if sn != seq:
                errors.append(f"seq_num {sn} out of order (expected {seq})")
            if len(line) != nx:
                errors.append(f"line {sn} length {len(line)} != nx={nx} (atomic lines, §4.2)")
    # A missing stop doc is a valid partial run (spec §4.3): treat it like a
    # non-success partial. The success-line-count check only applies when a
    # stop doc with exit_status == "success" is present; the capacity check
    # always applies.
    stops = [d for n, d in docs if n == "stop"]
    if stops:
        status = stops[0].get("exit_status")
        if status == "success" and seq != nE * ny:
            errors.append(f"success run has {seq} lines, expected {nE * ny}")
    if seq > nE * ny:
        errors.append(f"{seq} lines exceeds shape capacity {nE * ny}")
    return errors
```

- [ ] **Step 4: Run to verify pass**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_contract.py -v
```

Expected: PASS (all 14).

- [ ] **Step 5: Commit**

```bash
git add src/lightfall_pystxmcontrol/contract.py tests/test_contract.py
git commit -m "feat: contract.py — normative STXM Tiled run-layout contract v1 (spec 4)"
```

---

### Task 5: `stxm_energy_stack` plan (+ `_fly_rows` refactor)

**Files:**
- Modify: `src/lightfall_pystxmcontrol/plans.py`
- Test: `tests/test_energy_stack_plan.py`

**Interfaces:**
- Consumes: `contract.stxm_start_md`, `flyer.X_DATA_KEY` (Task 3/4).
- Produces: `stxm_energy_stack(flyer, energy_axis, y_axis, *, energies, y_start, y_stop, ny, x_start, x_stop, nx, dwell_ms, md=None)` generator; `stxm_fly_raster` gains `x_extent`/`y_extent` in its md (so the scan panel can position prior fly-raster images in motor coords, Task 12).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_energy_stack_plan.py
"""Task 5: stxm_energy_stack — documents-level contract tests (spec §3.2, §4)."""
import asyncio

import numpy as np
import pytest
from bluesky import RunEngine

from lightfall_pystxmcontrol import config, contract
from lightfall_pystxmcontrol.devices import PystxmAxis
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
from lightfall_pystxmcontrol.plans import stxm_energy_stack, stxm_fly_raster

NE, NY, NX = 2, 3, 4
ENERGIES = [500.0, 510.0]


def _devices(flyer_cls=PystxmLineFlyer):
    flyer = flyer_cls(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"])
    y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")
    en = PystxmAxis(config.DEFAULT_AXES["energy"], name="energy")

    async def _c():
        await flyer.connect(mock=False)
        await y.connect(mock=False)
        await en.connect(mock=False)
    asyncio.run(_c())
    return flyer, en, y


def _run(flyer, en, y):
    docs = []
    RE = RunEngine()
    RE(stxm_energy_stack(flyer, en, y, energies=ENERGIES,
                         y_start=-2, y_stop=2, ny=NY,
                         x_start=-4, x_stop=4, nx=NX, dwell_ms=1.0),
       lambda n, d: docs.append((n, d)))
    return docs


def test_emits_nE_times_ny_lines_and_validates():
    docs = _run(*_devices())
    names = [n for n, _ in docs]
    assert names.count("event_page") == NE * NY
    assert contract.validate_run_documents(docs) == [], contract.validate_run_documents(docs)


def test_start_doc_stxm_block():
    docs = _run(*_devices())
    start = next(d for n, d in docs if n == "start")
    s = start["stxm"]
    assert s["shape"] == [NE, NY, NX]
    assert s["energies"] == ENERGIES
    assert s["data_field"] == "STXMLineFlyer"
    assert s["x_motor"] == "SampleX" and s["y_motor"] == "SampleY"
    assert s["energy_motor"] == "energy"
    assert s["x_extent"] == [-4.0, 4.0] and s["y_extent"] == [-2.0, 2.0]


def test_line_shape_and_positive_counts():
    docs = _run(*_devices())
    for _, d in [x for x in docs if x[0] == "event_page"]:
        line = np.asarray(d["data"]["STXMLineFlyer"][0])
        assert line.shape == (NX,)
        assert (line > 0).all()


def test_energy_moves_between_frames():
    flyer, en, y = _devices()
    docs = _run(flyer, en, y)
    # After the run the energy axis sits at the last setpoint.
    assert asyncio.run(en.readback.get_value()) == ENERGIES[-1]


class _PoisonFlyer(PystxmLineFlyer):
    """Raises in complete() on the (k+1)-th row — mid-row abort simulation."""
    FAIL_AT_ROW = 4  # 0-based global line index

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._rows_done = 0

    def complete(self):
        if self._rows_done == self.FAIL_AT_ROW:
            raise RuntimeError("detector died mid-row")
        self._rows_done += 1
        return super().complete()


def test_abort_mid_row_emits_no_partial_event():
    flyer, en, y = _devices(_PoisonFlyer)
    docs = []
    RE = RunEngine()
    with pytest.raises(RuntimeError):
        RE(stxm_energy_stack(flyer, en, y, energies=ENERGIES,
                             y_start=-2, y_stop=2, ny=NY,
                             x_start=-4, x_stop=4, nx=NX, dwell_ms=1.0),
           lambda n, d: docs.append((n, d)))
    names = [n for n, _ in docs]
    assert names.count("event_page") == _PoisonFlyer.FAIL_AT_ROW  # only whole lines
    for _, d in [x for x in docs if x[0] == "event_page"]:
        assert len(d["data"]["STXMLineFlyer"][0]) == NX  # every emitted line is full (§4.2)
    stop = next(d for n, d in docs if n == "stop")
    assert stop["exit_status"] != "success"
    assert contract.validate_run_documents(docs) == []  # partial runs are valid data (§4.3)


def test_fly_raster_records_extents():
    flyer, _, y = _devices()
    docs = []
    RE = RunEngine()
    RE(stxm_fly_raster(flyer, y, y_start=-2, y_stop=2, ny=2,
                       x_start=-4, x_stop=4, nx=NX, dwell=1.0),
       lambda n, d: docs.append((n, d)))
    start = next(d for n, d in docs if n == "start")
    assert start["x_extent"] == [-4.0, 4.0] and start["y_extent"] == [-2.0, 2.0]
```

- [ ] **Step 2: Run to verify failure**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_energy_stack_plan.py -v
```

Expected: FAIL — `ImportError: cannot import name 'stxm_energy_stack'`.

- [ ] **Step 3: Implement in plans.py**

Replace the body of `stxm_fly_raster`'s loop with a shared helper and add the new plan. Full new content of the changed region:

```python
# src/lightfall_pystxmcontrol/plans.py
import numpy as np
import bluesky.plan_stubs as bps
from bluesky.preprocessors import run_decorator

from . import contract


def _fly_rows(flyer, y_axis, *, y_start, y_stop, ny, x_start, x_stop, nx, dwell_ms):
    """Shared per-row line-fly machinery: mv slow axis, prepare/kickoff/
    complete/collect the flyer once per row. Lines are atomic: an exception
    in complete() emits no event for that row (spec §4.2)."""
    for y in np.linspace(y_start, y_stop, ny):
        yield from bps.mv(y_axis, y)
        flyer.prepare(y=float(y), x_start=x_start, x_stop=x_stop,
                      nx=nx, dwell=dwell_ms)
        yield from bps.kickoff(flyer, wait=True)
        yield from bps.complete(flyer, wait=True)
        yield from bps.collect(flyer)


def stxm_fly_raster(flyer, y_axis, *, y_start, y_stop, ny,
                    x_start, x_stop, nx, dwell, md=None):
    """Step the slow axis (Y), fly the fast axis (X) per row.

    Emits one event per line (the flyer's collect): SampleX[nx], SampleY, <flyer>[nx].

    Units: y_start/y_stop/x_start/x_stop in micrometers (um); ``dwell`` is the
    per-point count time in MILLISECONDS (ms), not seconds — it is passed
    unchanged to keysight53230A.config(), whose sim getLine() sleeps
    ``dwell/1000 * nx`` seconds. So dwell=1000 -> 1 s/point.
    """
    _md = {"plan_name": "stxm_fly_raster", "shape": [ny, nx],
           "motors": [y_axis.name], "detectors": [flyer.name],
           # Extents in motor coords so consumers (e.g. the STXM scan panel)
           # can place this image in the motor coordinate frame.
           "x_extent": [float(x_start), float(x_stop)],
           "y_extent": [float(y_start), float(y_stop)]}
    if md:
        _md.update(md)

    @run_decorator(md=_md)
    def _inner():
        yield from _fly_rows(flyer, y_axis, y_start=y_start, y_stop=y_stop, ny=ny,
                             x_start=x_start, x_stop=x_stop, nx=nx, dwell_ms=dwell)

    return (yield from _inner())


def stxm_energy_stack(flyer, energy_axis, y_axis, *, energies,
                      y_start, y_stop, ny, x_start, x_stop, nx,
                      dwell_ms, md=None):
    """Energy-stack STXM: for each energy, move the energy axis then fly a
    full (ny, nx) image with the per-row line flyer (spec §3.2).

    One run, one ``primary`` stream, ``len(energies) * ny`` line events of
    shape (nx,). Ordering contract: seq_num = iE*ny + iy + 1 (spec §4.2).
    Units: positions um; ``dwell_ms`` MILLISECONDS end-to-end.
    """
    _md = contract.stxm_start_md(
        energies=energies, ny=ny, nx=nx, dwell_ms=dwell_ms,
        x_extent=[x_start, x_stop], y_extent=[y_start, y_stop],
        x_motor=flyer.X_DATA_KEY, y_motor=y_axis.name,
        energy_motor=energy_axis.name, data_field=flyer.name,
    )
    if md:
        _md.update(md)

    @run_decorator(md=_md)
    def _inner():
        for e in _md["stxm"]["energies"]:
            yield from bps.mv(energy_axis, e)
            yield from _fly_rows(flyer, y_axis, y_start=y_start, y_stop=y_stop,
                                 ny=ny, x_start=x_start, x_stop=x_stop, nx=nx,
                                 dwell_ms=dwell_ms)

    return (yield from _inner())
```

- [ ] **Step 4: Run new + existing plan tests**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_energy_stack_plan.py tests/test_fly_raster.py tests/test_plan_plugin.py -v
```

Expected: PASS (the `_fly_rows` refactor must keep `test_fly_raster.py` green).

- [ ] **Step 5: Commit**

```bash
git add src/lightfall_pystxmcontrol/plans.py tests/test_energy_stack_plan.py
git commit -m "feat: stxm_energy_stack plan on shared _fly_rows; extents in fly-raster md"
```

---

### Task 6: Plan UI adapter + manifest entry

**Files:**
- Modify: `src/lightfall_pystxmcontrol/plan_plugin.py`, `src/lightfall_pystxmcontrol/manifest.py`
- Test: `tests/test_energy_stack_plugin.py`

**Interfaces:**
- Consumes: `stxm_energy_stack` (Task 5), `FLYER_DEVICE_CLASS` (existing).
- Produces: `StxmEnergyStackPlanPlugin` (name `"stxm_energy_stack"`, category `"stxm"`); manifest `PluginEntry("plan", "stxm_energy_stack", "lightfall_pystxmcontrol.plan_plugin:StxmEnergyStackPlanPlugin")`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_energy_stack_plugin.py
"""Task 6: UI adapter + plan plugin for stxm_energy_stack."""
from lightfall_pystxmcontrol.plan_plugin import StxmEnergyStackPlanPlugin


def test_identity():
    p = StxmEnergyStackPlanPlugin()
    assert p.name == "stxm_energy_stack"
    assert p.category == "stxm"


def test_parameters():
    info = StxmEnergyStackPlanPlugin().get_plan_info()
    names = {p.name for p in info.parameters}
    assert names == {"flyer", "energy_axis", "y_axis", "energies",
                     "y_start", "y_stop", "ny", "x_start", "x_stop", "nx", "dwell_ms"}


def test_manifest_has_entry():
    from lightfall_pystxmcontrol.manifest import manifest
    entries = {(e.type_name, e.name) for e in manifest.plugins}
    assert ("plan", "stxm_energy_stack") in entries


def test_adapter_runs_and_validates():
    import asyncio
    from bluesky import RunEngine
    from lightfall_pystxmcontrol import config, contract
    from lightfall_pystxmcontrol.devices import PystxmAxis
    from lightfall_pystxmcontrol.flyer import PystxmLineFlyer

    plan_func = StxmEnergyStackPlanPlugin().get_plan_function()
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"])
    y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")
    en = PystxmAxis(config.DEFAULT_AXES["energy"], name="energy")

    async def _c():
        await flyer.connect(mock=False); await y.connect(mock=False); await en.connect(mock=False)
    asyncio.run(_c())

    docs = []
    RE = RunEngine()
    RE(plan_func(flyer, en, y, energies=[500.0, 510.0],
                 y_start=-2, y_stop=2, ny=2, x_start=-4, x_stop=4, nx=4, dwell_ms=1.0),
       lambda n, d: docs.append((n, d)))
    assert contract.validate_run_documents(docs) == []
```

- [ ] **Step 2: Run to verify failure**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_energy_stack_plugin.py -v
```

Expected: FAIL — `ImportError: StxmEnergyStackPlanPlugin`.

- [ ] **Step 3: Implement the adapter + plugin (append to plan_plugin.py)**

```python
# append to src/lightfall_pystxmcontrol/plan_plugin.py
from .plans import stxm_energy_stack


def _stxm_energy_stack_ui(
    flyer: Annotated[Any, DeviceFilter(device_class=FLYER_DEVICE_CLASS)],
    energy_axis: Annotated[Any, DeviceFilter(category="motor", name_pattern="energy")],
    y_axis: Annotated[Any, DeviceFilter(category="motor")],
    *,
    energies: list[float],
    y_start: Annotated[float, Unit("um")] = -5.0,
    y_stop: Annotated[float, Unit("um")] = 5.0,
    ny: Annotated[int, Range(1, 10000)] = 6,
    x_start: Annotated[float, Unit("um")] = -5.0,
    x_stop: Annotated[float, Unit("um")] = 5.0,
    nx: Annotated[int, Range(1, 10000)] = 10,
    dwell_ms: Annotated[float, Unit("ms")] = 1.0,
) -> Generator[Any, Any, Any]:
    """Energy-stack STXM: an (ny, nx) fly image at each energy (eV list).

    UNITS: positions um; dwell_ms is per-point count time in MILLISECONDS.
    ``energies`` is the flat eV setpoint list (the scan panel expands ranges).

    UI-facing adapter: delegates to the pure ``plans.stxm_energy_stack``.
    """
    return (yield from stxm_energy_stack(
        flyer, energy_axis, y_axis, energies=energies,
        y_start=y_start, y_stop=y_stop, ny=ny,
        x_start=x_start, x_stop=x_stop, nx=nx, dwell_ms=dwell_ms, md=None))


class StxmEnergyStackPlanPlugin(PlanPlugin):
    """Contributes the STXM energy-stack plan to Lightfall's plan registry."""

    @property
    def name(self) -> str:
        return "stxm_energy_stack"

    @property
    def category(self) -> str:
        return "stxm"

    def get_plan_function(self) -> Callable[..., Generator[Any, Any, Any]]:
        return _stxm_energy_stack_ui
```

- [ ] **Step 4: Add the manifest entry**

In `src/lightfall_pystxmcontrol/manifest.py`, append to `plugins=[...]`:

```python
        PluginEntry(
            "plan",
            "stxm_energy_stack",
            "lightfall_pystxmcontrol.plan_plugin:StxmEnergyStackPlanPlugin",
        ),
```

- [ ] **Step 5: Run to verify pass**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_energy_stack_plugin.py tests/test_plan_plugin.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/lightfall_pystxmcontrol/plan_plugin.py src/lightfall_pystxmcontrol/manifest.py tests/test_energy_stack_plugin.py
git commit -m "feat: stxm_energy_stack UI adapter + plan plugin + manifest entry"
```

---

### Task 7: Golden contract fixture

**Files:**
- Create: `scripts/make_golden_fixture.py`, `tests/fixtures/golden_energy_stack_run.json`, `tests/test_golden_fixture.py`

**Interfaces:**
- Consumes: `stxm_energy_stack`, `contract.validate_run_documents`.
- Produces: the checked-in golden documents JSON — the executable definition of §4 for future consumers (spec §7).

- [ ] **Step 1: Write the generator script**

```python
# scripts/make_golden_fixture.py
"""Regenerate tests/fixtures/golden_energy_stack_run.json from a sim run.

Counts are Poisson (non-deterministic); the fixture is validated STRUCTURALLY
(contract.validate_run_documents), never on exact values. Rerun after any
intentional contract change and commit the result.

    C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/make_golden_fixture.py
"""
import asyncio
import json
from pathlib import Path

import numpy as np
from bluesky import RunEngine

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmAxis
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
from lightfall_pystxmcontrol.plans import stxm_energy_stack

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_energy_stack_run.json"


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


def main() -> None:
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"])
    y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")
    en = PystxmAxis(config.DEFAULT_AXES["energy"], name="energy")

    async def _c():
        await flyer.connect(mock=False); await y.connect(mock=False); await en.connect(mock=False)
    asyncio.run(_c())

    docs = []
    RE = RunEngine()
    RE(stxm_energy_stack(flyer, en, y, energies=[500.0, 510.0],
                         y_start=-2, y_stop=2, ny=3,
                         x_start=-4, x_stop=4, nx=4, dwell_ms=1.0),
       lambda n, d: docs.append([n, _jsonable(dict(d))]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(docs, indent=1))
    print(f"Wrote {OUT} ({len(docs)} documents)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_golden_fixture.py
"""Task 7: the checked-in golden run must satisfy the contract validator."""
import json
from pathlib import Path

from lightfall_pystxmcontrol import contract

FIXTURE = Path(__file__).parent / "fixtures" / "golden_energy_stack_run.json"


def test_golden_fixture_exists_and_validates():
    docs = [(n, d) for n, d in json.loads(FIXTURE.read_text())]
    errors = contract.validate_run_documents(docs)
    assert errors == [], errors


def test_golden_fixture_shape_is_2x3x4():
    docs = json.loads(FIXTURE.read_text())
    start = next(d for n, d in docs if n == "start")
    assert start["stxm"]["shape"] == [2, 3, 4]
```

- [ ] **Step 3: Run test to verify it fails, generate, re-run**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_golden_fixture.py -v
# Expected: FAIL (FileNotFoundError)
C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/make_golden_fixture.py
# Expected: "Wrote .../golden_energy_stack_run.json (N documents)"
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_golden_fixture.py -v
# Expected: PASS
```

- [ ] **Step 4: Commit**

```bash
git add scripts/make_golden_fixture.py tests/fixtures/golden_energy_stack_run.json tests/test_golden_fixture.py
git commit -m "feat: golden energy-stack run fixture — executable contract definition"
```

---

### Task 8: Extract `ImageRenderMixin` (refactor, no behavior change)

**Files:**
- Create: `src/lightfall_pystxmcontrol/image_render.py`
- Modify: `src/lightfall_pystxmcontrol/stxm_map_viz.py`

**Interfaces:**
- Produces: `ImageRenderMixin` with `_render()`, `_ensure_view()`, `_auto_level_range()`, `_on_levels_changed()`, and attributes `_image`, `_image_view`, `_auto_levels`, `_applying_auto_levels`. Consumed by `StxmMapVisualization` (this task) and `StxmStackVisualization` (Task 9).

The auto-LUT + `ImageItem.updateImage` rendering in `stxm_map_viz.py` (`_render`, `_auto_level_range`, `_ensure_view`, `_on_levels_changed` — lines 142–209) is needed verbatim by the stack viz. Extract it; the existing `tests/test_stxm_map_viz.py` is the regression gate.

- [ ] **Step 1: Create the mixin — move the four methods verbatim**

```python
# src/lightfall_pystxmcontrol/image_render.py
"""Shared pyqtgraph image rendering: ImageItem.updateImage + auto-LUT.

Extracted verbatim from StxmMapVisualization (Phase 2c) so the 2-D map and
the 3-D stack visualizations render identically. Host classes provide
``self._image`` (2-D ndarray | None) and inherit QWidget.
"""
from __future__ import annotations

import numpy as np


class ImageRenderMixin:
    """Mixin: lazy pg.ImageView + lightweight updateImage + auto-LUT levels."""

    def _init_render_state(self) -> None:
        self._image: np.ndarray | None = None
        self._image_view = None
        self._auto_levels: bool = True
        self._applying_auto_levels: bool = False

    # The following four methods are moved UNCHANGED from stxm_map_viz.py
    # (Phase 2c): _render, _auto_level_range, _ensure_view, _on_levels_changed.
    # [Copy the method bodies exactly as they exist at stxm_map_viz.py lines
    #  142-209; do not edit them in flight.]
```

Move (do not copy) the four method bodies from `stxm_map_viz.py` into the mixin, unchanged. In `stxm_map_viz.py`:

```python
from .image_render import ImageRenderMixin


class StxmMapVisualization(ImageRenderMixin, BaseVisualization):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._init_render_state()
```

(Delete the four moved methods and the four `__init__` state lines from `stxm_map_viz.py`; everything else stays.)

- [ ] **Step 2: Run the full existing viz test file — the regression gate**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_stxm_map_viz.py -v
```

Expected: ALL PASS, unchanged. Any failure means the move was not verbatim — fix before proceeding.

- [ ] **Step 3: Commit**

```bash
git add src/lightfall_pystxmcontrol/image_render.py src/lightfall_pystxmcontrol/stxm_map_viz.py
git commit -m "refactor: extract ImageRenderMixin from stxm_map_viz (no behavior change)"
```

---

### Task 9: `StxmStackVisualization` core (allocation, blit, refresh, NaN)

**Files:**
- Create: `src/lightfall_pystxmcontrol/stxm_stack_viz.py`
- Test: `tests/test_stxm_stack_viz.py`

**Interfaces:**
- Consumes: `contract.decode_line_index`, `contract.cube_from_rows`, `contract.PLAN_NAME_ENERGY_STACK`, `ImageRenderMixin` (Task 8).
- Produces: `StxmStackVisualization(ImageRenderMixin, BaseVisualization)` with `current_cube() -> np.ndarray | None`, `current_frame_index() -> int`, `set_frame_index(i)`, `follow_live` bool property. Task 10 adds the slider UI; Task 14 (smoke) drives it via StreamBridge.

Key facts the implementer must know:
- The Tiled node under `run["primary"][data_field]` is a **2-D** growing array of shape `(k, nx)` (one row per line event) — the `(nE, ny, nx)` cube is `contract.cube_from_rows` of it. Live pushes carry `offset=(row, 0)` with `row == seq_num - 1`.
- `can_handle` must return **96** — the existing 2-D map viz scores 95 on ANY run containing the flyer key (its primary-probe fallback), including stack runs; the stack viz must outscore it.
- The start-doc `stxm` block is read via `run.metadata["start"]["stxm"]`; the data field comes from `stxm["data_field"]`, never a hardcoded string (spec §4.1).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_stxm_stack_viz.py
"""Tasks 9-10: StxmStackVisualization — allocation, blit, refresh, NaN, slider."""
import numpy as np


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


STXM_BLOCK = {
    "contract_version": 1, "shape": [2, 3, 4],
    "energies": [500.0, 510.0], "dwell_ms": 1.0,
    "x_extent": [-4.0, 4.0], "y_extent": [-2.0, 2.0],
    "x_motor": "SampleX", "y_motor": "SampleY", "energy_motor": "energy",
    "data_field": "STXMLineFlyer",
}


class _FakeNode:
    def __init__(self, rows):
        self._rows = np.asarray(rows, dtype=float)

    def read(self):
        return self._rows


class _FakeRun:
    def __init__(self, rows=None, stxm=STXM_BLOCK, plan_name="stxm_energy_stack"):
        self.metadata = {"start": {"plan_name": plan_name, **({"stxm": stxm} if stxm else {})}}
        self._rows = rows

    def __getitem__(self, key):
        if key == "primary" and self._rows is not None:
            return {STXM_BLOCK["data_field"]: _FakeNode(self._rows)}
        raise KeyError(key)


def _make_array_data(row, line, offset_none=False):
    class _Fake:
        type = "array-data"

        def __init__(self):
            self.offset = None if offset_none else (row, 0)
            self.shape = (1, len(line))

        def data(self):
            return np.asarray(line).reshape(1, -1)
    return _Fake()


def _viz(run=None):
    from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization
    _qapp()
    v = StxmStackVisualization()
    if run is not None:
        v.set_run(run)
        v.set_stream("primary")
    return v


class TestCanHandle:
    def test_scores_96_on_plan_name(self):
        from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization
        assert StxmStackVisualization.can_handle(_FakeRun()) == 96

    def test_outscores_map_viz_on_stack_runs(self):
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization
        from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization
        run = _FakeRun(rows=np.ones((1, 4)))
        assert StxmStackVisualization.can_handle(run) > StxmMapVisualization.can_handle(run)

    def test_zero_on_other_plan(self):
        from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization
        assert StxmStackVisualization.can_handle(_FakeRun(plan_name="grid_scan", stxm=None)) == 0

    def test_zero_on_broken_run(self):
        from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization

        class _Broken:
            @property
            def metadata(self):
                raise RuntimeError("no catalog")
        assert StxmStackVisualization.can_handle(_Broken()) == 0


class TestAllocationAndBlit:
    def test_allocates_from_start_doc(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        cube = v.current_cube()
        assert cube is not None and cube.shape == (2, 3, 4)
        assert np.isnan(cube).all()

    def test_blit_decodes_iE_iy_from_offset(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        line = np.arange(4, dtype=float) + 1.0
        v.on_stream_update(_make_array_data(row=4, line=line))  # (iE, iy) = divmod(4, 3) = (1, 1)
        cube = v.current_cube()
        assert np.array_equal(cube[1, 1], line)
        assert np.isnan(cube[0, 0]).all()

    def test_follow_live_tracks_current_energy(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        assert v.follow_live is True
        v.on_stream_update(_make_array_data(row=4, line=np.ones(4)))
        assert v.current_frame_index() == 1  # follows iE of the last blit

    def test_out_of_bounds_row_dropped(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        v.on_stream_update(_make_array_data(row=99, line=np.ones(4)))
        assert np.isnan(v.current_cube()).all()

    def test_offset_none_falls_back_to_refresh(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        calls = []
        v.refresh = lambda: calls.append(1)
        v.on_stream_update(_make_array_data(row=0, line=np.ones(4), offset_none=True))
        assert calls


class TestRefresh:
    def test_refresh_reads_rows_and_nan_fills(self):
        rows = np.ones((4, 4))  # 4 of 6 lines
        v = _viz(_FakeRun(rows=rows))
        cube = v.current_cube()
        assert not np.isnan(cube[0]).any()
        assert np.isnan(cube[1, 1]).all() and np.isnan(cube[1, 2]).all()

    def test_get_fields_from_start_doc(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        assert v.get_fields() == ["STXMLineFlyer"]

    def test_no_stxm_block_is_safe(self):
        v = _viz()
        v.set_run(_FakeRun(plan_name="stxm_energy_stack", stxm=None))
        v.set_stream("primary")  # must not raise
        assert v.current_cube() is None
```

- [ ] **Step 2: Run to verify failure**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_stxm_stack_viz.py -v
```

Expected: FAIL — `ModuleNotFoundError: stxm_stack_viz`.

- [ ] **Step 3: Implement the visualization core**

```python
# src/lightfall_pystxmcontrol/stxm_stack_viz.py
"""Live 3-D STXM energy-stack visualization (spec §3.4).

Consumes the contract (§4): allocates an (nE, ny, nx) cube from the start-doc
``stxm`` block (NEW machinery — the 2-D map has no production allocation
path), blits per-line array-data pushes at (iE, iy) = divmod(offset_row, ny),
and falls back to a full Tiled re-read (refresh) otherwise. The Tiled node is
a growing (k, nx) 2-D array; the cube view of it is contract.cube_from_rows.

Displays one energy frame at a time. Live-follow: the displayed frame tracks
the energy being acquired; user slider interaction suspends follow until the
Follow toggle re-enables it (Task 10 adds the widgets).
"""
from __future__ import annotations

from typing import Any

import numpy as np
from lightfall.plugins.types import PluginType
from lightfall.visualization.base_visualization import BaseVisualization

from . import contract
from .image_render import ImageRenderMixin


class StxmStackVisualization(ImageRenderMixin, BaseVisualization):
    viz_name = "stxm_stack"
    viz_display_name = "STXM Energy Stack"
    viz_icon = "layers-triple"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._init_render_state()
        self._cube: np.ndarray | None = None
        self._stxm: dict | None = None
        self._frame: int = 0
        self._follow_live: bool = True

    # ---------------- cube state ----------------

    def current_cube(self) -> np.ndarray | None:
        return self._cube

    def current_frame_index(self) -> int:
        return self._frame

    @property
    def follow_live(self) -> bool:
        return self._follow_live

    def set_frame_index(self, i: int) -> None:
        """Programmatic frame selection (slider calls this via Task 10)."""
        if self._cube is None:
            return
        self._frame = int(np.clip(i, 0, self._cube.shape[0] - 1))
        self._show_frame()

    def _show_frame(self) -> None:
        if self._cube is None:
            return
        self._image = self._cube[self._frame]
        self._render()

    # ---------------- streaming ----------------

    def on_stream_update(self, update: Any) -> None:
        if getattr(update, "type", None) != "array-data":
            self.refresh()
            return
        offset = getattr(update, "offset", None)
        if offset is None or self._cube is None or self._stxm is None:
            self.refresh()
            return
        nE, ny, nx = self._stxm["shape"]
        row = offset[0]
        if not (0 <= row < nE * ny):
            return
        line = np.asarray(update.data()).reshape(-1)
        if line.size != nx:
            return
        iE, iy = contract.decode_line_index(row, ny)
        self._cube[iE, iy] = line
        if self._follow_live:
            self._frame = iE
        if iE == self._frame:
            self._show_frame()

    # ---------------- BaseVisualization ----------------

    @staticmethod
    def can_handle(run: Any) -> int:
        """96: must outscore the 2-D map viz (95), whose primary-probe fallback
        also matches stack runs (they contain the same flyer key)."""
        try:
            start = (getattr(run, "metadata", None) or {}).get("start", {}) or {}
            if start.get("plan_name") == contract.PLAN_NAME_ENERGY_STACK:
                return 96
            return 0
        except Exception:
            return 0

    def set_run(self, run: Any) -> None:
        self._run = run
        try:
            self._stxm = run.metadata["start"]["stxm"]
        except Exception:
            self._stxm = None
        self._cube = None
        self._frame = 0

    def get_streams(self) -> list[str]:
        return ["primary"]

    def set_stream(self, stream_name: str) -> None:
        self._stream_name = stream_name
        self.refresh()

    def get_fields(self) -> list[str]:
        return [self._stxm["data_field"]] if self._stxm else []

    def set_field(self, field_name: str) -> None:
        self._field_name = field_name

    def refresh(self) -> None:
        """Re-read the (k, nx) rows node and rebuild the NaN-filled cube."""
        if self._stxm is None:
            return
        rows = np.empty((0, self._stxm["shape"][2]))
        node = self._rows_node()
        if node is not None:
            try:
                arr = np.asarray(node.read())
                if arr.ndim == 2:
                    rows = arr
            except Exception:
                pass
        self._cube = contract.cube_from_rows(rows, self._stxm["shape"])
        self._show_frame()

    def _rows_node(self):
        if self._run is None or self._stxm is None:
            return None
        try:
            return self._run["primary"][self._stxm["data_field"]]
        except Exception:
            return None


class StxmStackVizPlugin(PluginType):
    """Registers StxmStackVisualization with the VisualizationRegistry."""

    type_name = "visualization"

    @property
    def name(self) -> str:
        return "stxm_stack"

    def get_viz_class(self) -> type[StxmStackVisualization]:
        return StxmStackVisualization

    def get_introspection_data(self) -> dict:
        data = super().get_introspection_data()
        data["viz_name"] = StxmStackVisualization.viz_name
        data["viz_display_name"] = StxmStackVisualization.viz_display_name
        return data
```

- [ ] **Step 4: Run to verify pass**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_stxm_stack_viz.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lightfall_pystxmcontrol/stxm_stack_viz.py tests/test_stxm_stack_viz.py
git commit -m "feat: StxmStackVisualization core — start-doc allocation, offset blit, NaN refresh"
```

---

### Task 10: Stack viz UI (slider + live-follow) + manifest entry

**Files:**
- Modify: `src/lightfall_pystxmcontrol/stxm_stack_viz.py`, `src/lightfall_pystxmcontrol/manifest.py`
- Test: append to `tests/test_stxm_stack_viz.py`

**Interfaces:**
- Produces: energy slider (`QSlider`, horizontal) + "Follow" `QCheckBox` under the image; user slider interaction sets `follow_live=False`; checking Follow re-enables and jumps to the latest acquired frame. Manifest gains `PluginEntry("visualization", "stxm_stack", ...)`.

- [ ] **Step 1: Write the failing tests (append to tests/test_stxm_stack_viz.py)**

```python
class TestSliderAndFollow:
    def test_slider_updates_frame_and_suspends_follow(self):
        v = _viz(_FakeRun(rows=np.ones((6, 4))))
        v._ensure_controls()
        v._slider.setValue(1)
        v._on_slider_moved(1)  # simulate user drag (sliderMoved is user-only)
        assert v.current_frame_index() == 1
        assert v.follow_live is False

    def test_follow_checkbox_reenables_and_jumps_to_latest(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        v._ensure_controls()
        v._on_slider_moved(0)
        assert v.follow_live is False
        v.on_stream_update(_make_array_data(row=4, line=np.ones(4)))  # iE=1 acquired
        assert v.current_frame_index() == 0  # follow suspended — stays put
        v._follow_box.setChecked(True)
        assert v.follow_live is True
        assert v.current_frame_index() == 1  # jumped to latest acquired energy

    def test_slider_range_matches_nE(self):
        v = _viz(_FakeRun(rows=np.ones((6, 4))))
        v._ensure_controls()
        assert (v._slider.minimum(), v._slider.maximum()) == (0, 1)


class TestStackVizPlugin:
    def test_plugin_identity(self):
        from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVizPlugin
        p = StxmStackVizPlugin()
        assert p.name == "stxm_stack"
        assert StxmStackVizPlugin.type_name == "visualization"

    def test_manifest_has_entry(self):
        from lightfall_pystxmcontrol.manifest import manifest
        entries = {(e.type_name, e.name) for e in manifest.plugins}
        assert ("visualization", "stxm_stack") in entries
```

- [ ] **Step 2: Run to verify failure**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_stxm_stack_viz.py -k "Slider or Plugin" -v
```

Expected: FAIL — `AttributeError: _ensure_controls`.

- [ ] **Step 3: Implement the controls**

Add to `StxmStackVisualization` (and update `_show_frame`/`on_stream_update`/`refresh` to call `_sync_controls()` after state changes):

```python
    def _ensure_controls(self) -> None:
        """Lazily build slider + follow checkbox below the image view."""
        if getattr(self, "_slider", None) is not None:
            return
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QSlider

        self._ensure_view()  # ImageRenderMixin: builds the ImageView + layout
        self._slider = QSlider(Qt.Horizontal, self)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        self._follow_box = QCheckBox("Follow", self)
        self._follow_box.setChecked(self._follow_live)
        self._follow_box.toggled.connect(self._on_follow_toggled)
        self._energy_label = QLabel("", self)
        row = QHBoxLayout()
        row.addWidget(self._slider, 1)
        row.addWidget(self._energy_label, 0)
        row.addWidget(self._follow_box, 0)
        self.layout().addLayout(row)
        self._sync_controls()

    def _on_slider_moved(self, value: int) -> None:
        """USER slider interaction suspends live-follow (spec §3.4)."""
        self._follow_live = False
        if getattr(self, "_follow_box", None) is not None:
            self._follow_box.setChecked(False)
        self.set_frame_index(value)

    def _on_follow_toggled(self, checked: bool) -> None:
        self._follow_live = bool(checked)
        if checked:
            self.set_frame_index(self._latest_frame)

    def _sync_controls(self) -> None:
        if getattr(self, "_slider", None) is None or self._cube is None:
            return
        self._slider.setMaximum(self._cube.shape[0] - 1)
        self._slider.blockSignals(True)
        self._slider.setValue(self._frame)
        self._slider.blockSignals(False)
        if self._stxm:
            e = self._stxm["energies"][self._frame]
            self._energy_label.setText(f"{e:g} eV [{self._frame + 1}/{self._cube.shape[0]}]")
```

Track the latest acquired frame: initialize `self._latest_frame = 0` in `__init__`; in `on_stream_update` after a successful blit set `self._latest_frame = iE`. Call `self._ensure_controls()` at the top of `_show_frame()` and `self._sync_controls()` at its end.

- [ ] **Step 4: Add the manifest entry**

```python
        PluginEntry(
            "visualization",
            "stxm_stack",
            "lightfall_pystxmcontrol.stxm_stack_viz:StxmStackVizPlugin",
        ),
```

- [ ] **Step 5: Run the whole viz test file**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_stxm_stack_viz.py -v
```

Expected: PASS (all Task 9 + Task 10 tests).

- [ ] **Step 6: Commit**

```bash
git add src/lightfall_pystxmcontrol/stxm_stack_viz.py src/lightfall_pystxmcontrol/manifest.py tests/test_stxm_stack_viz.py
git commit -m "feat: stack viz energy slider + live-follow; visualization manifest entry"
```

---

### Task 11: Energy-ranges editor

**Files:**
- Create: `src/lightfall_pystxmcontrol/energy_ranges.py`
- Test: `tests/test_energy_ranges.py`

**Interfaces:**
- Produces: `expand_ranges(ranges: list[tuple[float, float, int]]) -> list[float]` (pure); `EnergyRangesEditor(QWidget)` with `.ranges() -> list[tuple[float, float, int]]`, `.energies() -> list[float]`, `.add_range(start, stop, n)`, `.remove_selected()`, Qt signal `changed`. Consumed by Task 12/13 (panel).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_energy_ranges.py
"""Task 11: energy-range expansion + editor widget (spec §3.3)."""
import pytest


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class TestExpandRanges:
    def test_single_range(self):
        from lightfall_pystxmcontrol.energy_ranges import expand_ranges
        assert expand_ranges([(500.0, 520.0, 3)]) == [500.0, 510.0, 520.0]

    def test_multiple_ranges_concatenate(self):
        from lightfall_pystxmcontrol.energy_ranges import expand_ranges
        assert expand_ranges([(500.0, 510.0, 2), (700.0, 700.0, 1)]) == [500.0, 510.0, 700.0]

    def test_single_point_range(self):
        from lightfall_pystxmcontrol.energy_ranges import expand_ranges
        assert expand_ranges([(600.0, 640.0, 1)]) == [600.0]

    def test_empty(self):
        from lightfall_pystxmcontrol.energy_ranges import expand_ranges
        assert expand_ranges([]) == []

    def test_n_below_one_rejected(self):
        from lightfall_pystxmcontrol.energy_ranges import expand_ranges
        with pytest.raises(ValueError):
            expand_ranges([(500.0, 510.0, 0)])


class TestEditorWidget:
    def test_add_and_expand(self, qtbot):
        from lightfall_pystxmcontrol.energy_ranges import EnergyRangesEditor
        _qapp()
        ed = EnergyRangesEditor()
        qtbot.addWidget(ed)
        ed.add_range(500.0, 520.0, 3)
        ed.add_range(700.0, 700.0, 1)
        assert ed.ranges() == [(500.0, 520.0, 3), (700.0, 700.0, 1)]
        assert ed.energies() == [500.0, 510.0, 520.0, 700.0]

    def test_changed_signal(self, qtbot):
        from lightfall_pystxmcontrol.energy_ranges import EnergyRangesEditor
        _qapp()
        ed = EnergyRangesEditor()
        qtbot.addWidget(ed)
        with qtbot.waitSignal(ed.changed, timeout=1000):
            ed.add_range(500.0, 510.0, 2)

    def test_remove_selected(self, qtbot):
        from lightfall_pystxmcontrol.energy_ranges import EnergyRangesEditor
        _qapp()
        ed = EnergyRangesEditor()
        qtbot.addWidget(ed)
        ed.add_range(500.0, 510.0, 2)
        ed.add_range(700.0, 710.0, 2)
        ed._table.selectRow(0)
        ed.remove_selected()
        assert ed.ranges() == [(700.0, 710.0, 2)]
```

- [ ] **Step 2: Run to verify failure**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_energy_ranges.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# src/lightfall_pystxmcontrol/energy_ranges.py
"""Energy-range definition: rows of (start, stop, n_points) expanding to the
flat eV list the stxm_energy_stack plan takes (spec §3.3). Absorbs the
FUNCTION of pystxmcontrol's energyDef.py on Lightfall idioms — no code import.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox, QHBoxLayout, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)


def expand_ranges(ranges: list[tuple[float, float, int]]) -> list[float]:
    """Expand (start, stop, n) rows to a flat energies list.

    n == 1 yields [start]. n < 1 raises ValueError. Rows concatenate in order;
    no dedup (a shared boundary point appearing twice is the user's intent).
    """
    energies: list[float] = []
    for start, stop, n in ranges:
        if n < 1:
            raise ValueError(f"range ({start}, {stop}) needs n >= 1, got {n}")
        energies.extend(float(v) for v in np.linspace(start, stop, int(n)))
    return energies


class EnergyRangesEditor(QWidget):
    """Table of (start eV, stop eV, points) rows + add/remove controls."""

    changed = Signal()

    _COLS = ("Start (eV)", "Stop (eV)", "Points")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._table = QTableWidget(0, len(self._COLS), self)
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._start = QDoubleSpinBox(self); self._start.setRange(0.0, 100000.0); self._start.setValue(500.0)
        self._stop = QDoubleSpinBox(self); self._stop.setRange(0.0, 100000.0); self._stop.setValue(520.0)
        self._n = QSpinBox(self); self._n.setRange(1, 100000); self._n.setValue(3)
        add = QPushButton("Add", self)
        add.clicked.connect(lambda: self.add_range(self._start.value(), self._stop.value(), self._n.value()))
        rm = QPushButton("Remove", self)
        rm.clicked.connect(self.remove_selected)

        row = QHBoxLayout()
        for w in (self._start, self._stop, self._n, add, rm):
            row.addWidget(w)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(row)
        lay.addWidget(self._table)

    def add_range(self, start: float, stop: float, n: int) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        for c, v in enumerate((start, stop, int(n))):
            item = QTableWidgetItem(str(v))
            # Cells are read-only (spec §3.3 defines the surface as add/remove
            # rows only): inline editing would bypass the `changed` signal and
            # feed unguarded float()/int() parsing in ranges(). Rows are
            # edited by remove + re-add; inline editing (with validation and
            # changed wiring) is deliberately out of scope for this slice.
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(r, c, item)
        self.changed.emit()

    def remove_selected(self) -> None:
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._table.removeRow(r)
        if rows:
            self.changed.emit()

    def ranges(self) -> list[tuple[float, float, int]]:
        out = []
        for r in range(self._table.rowCount()):
            out.append((float(self._table.item(r, 0).text()),
                        float(self._table.item(r, 1).text()),
                        int(self._table.item(r, 2).text())))
        return out

    def energies(self) -> list[float]:
        return expand_ranges(self.ranges())
```

- [ ] **Step 4: Run to verify pass**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_energy_ranges.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lightfall_pystxmcontrol/energy_ranges.py tests/test_energy_ranges.py
git commit -m "feat: energy-ranges editor + expansion (absorbs energyDef function)"
```

---

### Task 12: Scan panel core — context image, region ROI, kwargs mapping

**Files:**
- Create: `src/lightfall_pystxmcontrol/scan_panel.py`
- Test: `tests/test_scan_panel.py`

**Interfaces:**
- Consumes: `EnergyRangesEditor` (Task 11); lightfall core `BasePanel`/`PanelMetadata` (`lightfall.ui.panels.base`), `TiledService` (`lightfall.services.tiled_service`).
- Produces: `STXMScanPanel(BasePanel)` with injectable deps (`catalog=`, `engine=`, `tiled_client=`) resolved lazily to singletons when None; `region_to_plan_kwargs(pos, size) -> dict` (pure); `load_run(uid)`; `set_manual_extents(x0, x1, y0, y1)`. Task 13 adds devices/validation/submit.

Key facts:
- `BasePanel.__init__(parent)` calls `self._setup_ui()` at its end — set injectable attrs BEFORE `super().__init__()`.
- Tiled read idiom (core `VisualizationPanel._resolve_entry`): `TiledService.get_instance()`, check `.is_connected`, `client[uid]`, `KeyError -> None`.
- pyqtgraph: `ImageItem.setOpts(axisOrder="row-major")` so `data[iy, ix]` renders iy-vertical; `ImageItem.setRect(QRectF(x0, y0, w, h))` places the image in motor coordinates, making `RectROI` state directly motor coords. Descending extents (spec §4.1) are handled by normalizing rect origin/size to min/width.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scan_panel.py
"""Tasks 12-13: STXM scan-definition panel (spec §3.3)."""
import numpy as np
import pytest
from unittest.mock import MagicMock


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _FakeNode:
    def __init__(self, arr):
        self._arr = np.asarray(arr, dtype=float)

    def read(self):
        return self._arr


class _FakeEntry:
    """Duck-type of a Tiled BlueskyRun entry for a completed fly-raster run."""
    def __init__(self, arr, x_extent=(-4.0, 4.0), y_extent=(-2.0, 2.0),
                 plan="stxm_fly_raster", detectors=("STXMLineFlyer",)):
        self.metadata = {"start": {
            "plan_name": plan, "detectors": list(detectors),
            "x_extent": list(x_extent), "y_extent": list(y_extent),
        }}
        self._arr = arr

    def __getitem__(self, key):
        if key == "primary":
            return {"STXMLineFlyer": _FakeNode(self._arr)}
        raise KeyError(key)


class _FakeTiledClient(dict):
    pass


def _panel(qtbot, client=None, catalog=None, engine=None):
    from lightfall_pystxmcontrol.scan_panel import STXMScanPanel
    _qapp()
    p = STXMScanPanel(catalog=catalog or MagicMock(), engine=engine or MagicMock(),
                      tiled_client=client if client is not None else _FakeTiledClient())
    qtbot.addWidget(p)
    return p


class TestRegionMapping:
    def test_region_to_plan_kwargs(self):
        from lightfall_pystxmcontrol.scan_panel import region_to_plan_kwargs
        kw = region_to_plan_kwargs(pos=(-3.0, -1.0), size=(2.0, 3.0))
        assert kw == {"x_start": -3.0, "x_stop": -1.0, "y_start": -1.0, "y_stop": 2.0}


class TestContextImage:
    def test_load_run_positions_image_in_motor_coords(self, qtbot):
        client = _FakeTiledClient()
        client["u1"] = _FakeEntry(np.ones((3, 5)))
        p = _panel(qtbot, client=client)
        p.load_run("u1")
        assert p.current_extents() == (-4.0, 4.0, -2.0, 2.0)
        r = p._image_item.boundingRect()  # placed via setRect in motor coords
        assert (r.left(), r.top(), r.width(), r.height()) == (-4.0, -2.0, 8.0, 4.0)

    def test_load_run_missing_uid_sets_error_not_raise(self, qtbot):
        p = _panel(qtbot, client=_FakeTiledClient())
        p.load_run("nope")  # must not raise
        assert "nope" in p._status_label.text()

    def test_manual_extents_without_run(self, qtbot):
        p = _panel(qtbot, client=_FakeTiledClient())
        p.set_manual_extents(-10.0, 10.0, -5.0, 5.0)
        assert p.current_extents() == (-10.0, 10.0, -5.0, 5.0)

    def test_descending_extents_normalized_for_display(self, qtbot):
        client = _FakeTiledClient()
        client["u1"] = _FakeEntry(np.ones((3, 5)), x_extent=(4.0, -4.0))
        p = _panel(qtbot, client=client)
        p.load_run("u1")  # spec §4.1: descending extents are legal
        r = p._image_item.boundingRect()
        assert (r.left(), r.width()) == (-4.0, 8.0)


class TestRegionRoi:
    def test_region_kwargs_from_roi_state(self, qtbot):
        p = _panel(qtbot)
        p.set_manual_extents(-10.0, 10.0, -5.0, 5.0)
        p._roi.setPos((-3.0, -1.0))
        p._roi.setSize((2.0, 3.0))
        kw = p.region_kwargs()
        assert kw == {"x_start": -3.0, "x_stop": -1.0, "y_start": -1.0, "y_stop": 2.0}
```

- [ ] **Step 2: Run to verify failure**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_scan_panel.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement the panel core**

```python
# src/lightfall_pystxmcontrol/scan_panel.py
"""STXM scan-definition panel (spec §3.3).

Absorbs the FUNCTION of pystxmcontrol's scanDef/regionDef/energyDef GUI on
Lightfall idioms: draw a region on a prior image (loaded THROUGH TILED, in
motor coordinates), define energy ranges, pick devices, submit the
stxm_energy_stack plan via get_engine().submit(). No pystxmcontrol imports.

Injectable deps (catalog=, engine=, tiled_client=) follow the XPCS panel's
testability pattern; None means "resolve the Lightfall singleton lazily".
"""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import (
    QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QWidget,
)

from lightfall.ui.panels.base import BasePanel, PanelMetadata

from .energy_ranges import EnergyRangesEditor


def region_to_plan_kwargs(pos: tuple[float, float], size: tuple[float, float]) -> dict:
    """Map a RectROI (pos, size) in motor coords to plan geometry kwargs.

    pyqtgraph RectROI pos is the rect origin (min-x, min-y) and size is
    positive, so start < stop always; scan direction is the plan's business.
    """
    x0, y0 = float(pos[0]), float(pos[1])
    w, h = float(size[0]), float(size[1])
    return {"x_start": x0, "x_stop": x0 + w, "y_start": y0, "y_stop": y0 + h}


class STXMScanPanel(BasePanel):
    panel_metadata: ClassVar[PanelMetadata] = PanelMetadata(
        id="lightfall_pystxmcontrol.panels.stxm_scan",
        name="STXM Scan",
        description="Define and launch STXM energy-stack scans.",
        icon="microscope",
        category="Acquisition",
        default_area="left",
        proactive_init=False,
    )

    def __init__(self, parent: QWidget | None = None, *,
                 catalog: Any = None, engine: Any = None,
                 tiled_client: Any = None) -> None:
        # Injectables BEFORE super().__init__ — BasePanel calls _setup_ui() there.
        self._catalog_override = catalog
        self._engine_override = engine
        self._tiled_client_override = tiled_client
        self._extents: tuple[float, float, float, float] | None = None
        super().__init__(parent)

    # ---------------- dependency resolution ----------------

    def _catalog(self) -> Any:
        if self._catalog_override is not None:
            return self._catalog_override
        from lightfall.devices import DeviceCatalog
        return DeviceCatalog.get_instance()

    def _engine(self) -> Any:
        if self._engine_override is not None:
            return self._engine_override
        from lightfall.acquire.engine import get_engine
        return get_engine()

    def _tiled_client(self) -> Any:
        if self._tiled_client_override is not None:
            return self._tiled_client_override
        from lightfall.services.tiled_service import TiledService
        svc = TiledService.get_instance()
        return svc.client if svc.is_connected else None

    # ---------------- UI ----------------

    def _setup_ui(self) -> None:
        import pyqtgraph as pg

        # Context image row: uid + load, manual extents
        self._uid_edit = QLineEdit(self)
        self._uid_edit.setPlaceholderText("prior run uid")
        load_btn = QPushButton("Load run", self)
        load_btn.clicked.connect(lambda: self.load_run(self._uid_edit.text().strip()))
        self._status_label = QLabel("", self)
        top = QHBoxLayout()
        top.addWidget(self._uid_edit, 1)
        top.addWidget(load_btn, 0)

        # Manual extents (used when no prior run is loaded)
        self._ext_boxes = []
        ext_row = QHBoxLayout()
        ext_row.addWidget(QLabel("Extents x0,x1,y0,y1:", self))
        for default in (-10.0, 10.0, -10.0, 10.0):
            b = QDoubleSpinBox(self)
            b.setRange(-1e6, 1e6)
            b.setValue(default)
            self._ext_boxes.append(b)
            ext_row.addWidget(b)
        apply_ext = QPushButton("Apply", self)
        apply_ext.clicked.connect(
            lambda: self.set_manual_extents(*(b.value() for b in self._ext_boxes)))
        ext_row.addWidget(apply_ext)

        # Image + region ROI (motor coordinates via ImageItem.setRect)
        self._plot = pg.PlotWidget(self)
        self._plot.setAspectLocked(False)
        self._image_item = pg.ImageItem()
        self._image_item.setOpts(axisOrder="row-major")  # data[iy, ix], iy vertical
        self._plot.addItem(self._image_item)
        self._roi = pg.RectROI(pos=(-5.0, -5.0), size=(10.0, 10.0), pen="y")
        self._plot.addItem(self._roi)

        # Pixels
        pix_row = QHBoxLayout()
        pix_row.addWidget(QLabel("nx:", self))
        self._nx = QSpinBox(self); self._nx.setRange(1, 10000); self._nx.setValue(10)
        pix_row.addWidget(self._nx)
        pix_row.addWidget(QLabel("ny:", self))
        self._ny = QSpinBox(self); self._ny.setRange(1, 10000); self._ny.setValue(6)
        pix_row.addWidget(self._ny)
        pix_row.addWidget(QLabel("dwell (ms):", self))
        self._dwell = QDoubleSpinBox(self); self._dwell.setRange(0.01, 60000.0); self._dwell.setValue(1.0)
        pix_row.addWidget(self._dwell)

        # Energy ranges
        self._energy_editor = EnergyRangesEditor(self)

        self._layout.addLayout(top)
        self._layout.addWidget(self._status_label)
        self._layout.addLayout(ext_row)
        self._layout.addWidget(self._plot)
        self._layout.addLayout(pix_row)
        self._layout.addWidget(self._energy_editor)
        self._setup_submit_ui()  # Task 13 (no-op placeholder until then)

    def _setup_submit_ui(self) -> None:
        """Extended in Task 13 with device pickers, validation, and Launch."""

    # ---------------- context image ----------------

    def load_run(self, uid: str) -> None:
        """Load a prior run's map through Tiled and place it in motor coords.

        Follows core VisualizationPanel._resolve_entry: disconnected -> None,
        KeyError -> not found. Never raises; failures land in the status label.
        """
        client = self._tiled_client()
        if client is None:
            self._status_label.setText("Tiled not connected")
            return
        try:
            entry = client[uid]
        except KeyError:
            self._status_label.setText(f"run {uid!r} not found")
            return
        except Exception as e:
            self._status_label.setText(f"load failed: {e}")
            return
        try:
            start = entry.metadata["start"]
            field = (start.get("stxm") or {}).get("data_field") \
                or (start.get("detectors") or [None])[0]
            arr = np.asarray(entry["primary"][field].read(), dtype=float)
            x_extent = start.get("x_extent") or (start.get("stxm") or {}).get("x_extent")
            y_extent = start.get("y_extent") or (start.get("stxm") or {}).get("y_extent")
        except Exception as e:
            self._status_label.setText(f"unreadable run: {e}")
            return
        if arr.ndim == 3:  # stack cube rows already reshaped upstream — take frame 0
            arr = arr[0]
        if arr.ndim != 2 or x_extent is None or y_extent is None:
            self._status_label.setText("run has no 2-D map with extents")
            return
        self._show_image(arr, tuple(x_extent), tuple(y_extent))
        self._status_label.setText(f"loaded {uid[:8]}… shape={arr.shape}")

    def set_manual_extents(self, x0: float, x1: float, y0: float, y1: float) -> None:
        self._show_image(None, (x0, x1), (y0, y1))

    def _show_image(self, arr: np.ndarray | None,
                    x_extent: tuple[float, float], y_extent: tuple[float, float]) -> None:
        self._extents = (float(x_extent[0]), float(x_extent[1]),
                         float(y_extent[0]), float(y_extent[1]))
        # Normalize for display; descending extents are legal (spec §4.1).
        x_lo, x_hi = sorted((self._extents[0], self._extents[1]))
        y_lo, y_hi = sorted((self._extents[2], self._extents[3]))
        if arr is not None:
            self._image_item.setImage(arr)
            self._image_item.setRect(QRectF(x_lo, y_lo, x_hi - x_lo, y_hi - y_lo))
        self._roi.setPos((x_lo + (x_hi - x_lo) * 0.25, y_lo + (y_hi - y_lo) * 0.25))
        self._roi.setSize(((x_hi - x_lo) * 0.5, (y_hi - y_lo) * 0.5))
        self._plot.setRange(xRange=(x_lo, x_hi), yRange=(y_lo, y_hi))

    def current_extents(self) -> tuple[float, float, float, float] | None:
        return self._extents

    def region_kwargs(self) -> dict:
        pos = self._roi.pos()
        size = self._roi.size()
        return region_to_plan_kwargs((pos.x(), pos.y()), (size.x(), size.y()))
```

- [ ] **Step 4: Run to verify pass**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_scan_panel.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lightfall_pystxmcontrol/scan_panel.py tests/test_scan_panel.py
git commit -m "feat: STXM scan panel core — Tiled context image, motor-coord region ROI"
```

---

### Task 13: Scan panel — devices, validation, submit + panel plugin

**Files:**
- Modify: `src/lightfall_pystxmcontrol/scan_panel.py`, `src/lightfall_pystxmcontrol/manifest.py`
- Test: append to `tests/test_scan_panel.py`

**Interfaces:**
- Consumes: `DeviceCatalog` API (`list_devices(category=...)`, `get_device_by_name(name)`, `get_ophyd_device(name)`; happi limits at `DeviceInfo.metadata["kwargs"]["axis_config"]`), `get_engine().submit(procedure, name=...)`, `plans.stxm_energy_stack`.
- Produces: `validate_scan() -> list[str]`; `launch() -> str | None` (procedure id or None); `StxmScanPanelPlugin(PanelPlugin)`; manifest `PluginEntry("panel", "stxm_scan", ..., preload=True)`.

- [ ] **Step 1: Write the failing tests (append to tests/test_scan_panel.py)**

```python
class _FakeDeviceInfo:
    def __init__(self, name, min_v=-100.0, max_v=100.0):
        self.name = name
        self.metadata = {"kwargs": {"axis_config": {"minValue": min_v, "maxValue": max_v}}}


class _FakeCatalog:
    """Duck-type of DeviceCatalog for the pystxm sim device set."""
    def __init__(self):
        self._infos = {
            "SampleY": _FakeDeviceInfo("SampleY"),
            "energy": _FakeDeviceInfo("energy", 250.0, 2500.0),
            "STXMLineFlyer": _FakeDeviceInfo("STXMLineFlyer"),
        }
        self._ophyd = {k: MagicMock(name=k) for k in self._infos}
        for k, m in self._ophyd.items():
            m.name = k
        # flyer needs the contract attrs the plan reads
        self._ophyd["STXMLineFlyer"].X_DATA_KEY = "SampleX"

    def get_device_by_name(self, name):
        return self._infos.get(name)

    def get_ophyd_device(self, name):
        return self._ophyd.get(name)


class TestValidationAndSubmit:
    def _ready_panel(self, qtbot, engine=None):
        p = _panel(qtbot, catalog=_FakeCatalog(), engine=engine or MagicMock())
        p.set_manual_extents(-10.0, 10.0, -5.0, 5.0)
        p._flyer_name = "STXMLineFlyer"
        p._energy_name = "energy"
        p._y_name = "SampleY"
        p._energy_editor.add_range(500.0, 510.0, 2)
        return p

    def test_valid_scan_has_no_errors(self, qtbot):
        p = self._ready_panel(qtbot)
        assert p.validate_scan() == []

    def test_empty_energies_rejected(self, qtbot):
        p = self._ready_panel(qtbot)
        p._energy_editor._table.setRowCount(0)
        assert any("energ" in e.lower() for e in p.validate_scan())

    def test_energy_outside_soft_limits_rejected(self, qtbot):
        p = self._ready_panel(qtbot)
        p._energy_editor.add_range(3000.0, 3000.0, 1)  # > maxValue 2500
        assert any("limit" in e.lower() for e in p.validate_scan())

    def test_region_outside_y_limits_rejected(self, qtbot):
        p = self._ready_panel(qtbot)
        p._roi.setPos((-3.0, -200.0))  # y below SampleY minValue -100
        p._roi.setSize((2.0, 3.0))
        assert any("limit" in e.lower() for e in p.validate_scan())

    def test_launch_submits_plan_with_name(self, qtbot):
        engine = MagicMock()
        engine.submit.return_value = "proc-1"
        p = self._ready_panel(qtbot, engine=engine)
        assert p.launch() == "proc-1"
        assert engine.submit.call_count == 1
        _, kwargs = engine.submit.call_args
        assert kwargs.get("name") == "stxm_energy_stack"

    def test_launch_blocked_when_invalid(self, qtbot):
        engine = MagicMock()
        p = self._ready_panel(qtbot, engine=engine)
        p._energy_editor._table.setRowCount(0)
        assert p.launch() is None
        engine.submit.assert_not_called()


class TestPanelPlugin:
    def test_plugin_identity_and_panel_class(self):
        from lightfall_pystxmcontrol.scan_panel import StxmScanPanelPlugin, STXMScanPanel
        p = StxmScanPanelPlugin()
        assert p.name == "stxm_scan"
        assert p.get_panel_class() is STXMScanPanel
        assert p.panel_id == "lightfall_pystxmcontrol.panels.stxm_scan"

    def test_manifest_has_preloaded_panel_entry(self):
        from lightfall_pystxmcontrol.manifest import manifest
        entry = next(e for e in manifest.plugins if e.type_name == "panel")
        assert entry.name == "stxm_scan"
        assert entry.preload is True
```

- [ ] **Step 2: Run to verify failure**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_scan_panel.py -k "Validation or PanelPlugin" -v
```

Expected: FAIL — `AttributeError: validate_scan` / import errors.

- [ ] **Step 3: Implement devices/validation/submit**

Replace the `_setup_submit_ui` placeholder and add the methods + plugin class:

```python
    def _setup_submit_ui(self) -> None:
        from PySide6.QtWidgets import QComboBox

        # Device pickers (Phase A: flyer selection IS the channel selection,
        # spec §3.3; its name lands in the contract as data_field).
        self._flyer_name = "STXMLineFlyer"
        self._energy_name = "energy"
        self._y_name = "SampleY"

        dev_row = QHBoxLayout()
        self._device_combos: dict[str, Any] = {}
        for label, attr, names in (
            ("Detector:", "_flyer_name", ["STXMLineFlyer"]),
            ("Energy:", "_energy_name", ["energy"]),
            ("Y axis:", "_y_name", ["SampleY", "SampleX"]),
        ):
            dev_row.addWidget(QLabel(label, self))
            combo = QComboBox(self)
            combo.addItems(names)
            combo.currentTextChanged.connect(
                lambda text, a=attr: setattr(self, a, text))
            self._device_combos[attr] = combo
            dev_row.addWidget(combo)

        self._errors_label = QLabel("", self)
        self._errors_label.setWordWrap(True)
        self._launch_btn = QPushButton("Launch energy stack", self)
        self._launch_btn.clicked.connect(self.launch)

        self._layout.addLayout(dev_row)
        self._layout.addWidget(self._errors_label)
        self._layout.addWidget(self._launch_btn)

    # ---------------- validation + submit ----------------

    def _axis_limits(self, device_name: str) -> tuple[float, float] | None:
        """Soft limits from the happi entry kwargs (spec §3.3: PystxmAxis
        exposes no limits on the ophyd device itself)."""
        info = self._catalog().get_device_by_name(device_name)
        try:
            cfg = info.metadata["kwargs"]["axis_config"]
            return float(cfg["minValue"]), float(cfg["maxValue"])
        except Exception:
            return None

    def validate_scan(self) -> list[str]:
        errors: list[str] = []
        try:
            energies = self._energy_editor.energies()
        except ValueError as e:
            return [str(e)]
        if not energies:
            errors.append("no energies defined")
        region = self.region_kwargs()
        if self._nx.value() < 1 or self._ny.value() < 1:
            errors.append("nx and ny must be >= 1")
        lim = self._axis_limits(self._energy_name)
        if lim and energies:
            lo, hi = lim
            bad = [e for e in energies if not (lo <= e <= hi)]
            if bad:
                errors.append(f"energies outside soft limits [{lo}, {hi}]: {bad[:3]}")
        lim = self._axis_limits(self._y_name)
        if lim:
            lo, hi = lim
            if not (lo <= region["y_start"] and region["y_stop"] <= hi):
                errors.append(f"region Y outside soft limits [{lo}, {hi}]")
        # X limits live on the flyer's embedded fast axis config
        info = self._catalog().get_device_by_name(self._flyer_name)
        try:
            cfg = info.metadata["kwargs"]["x_axis_config"]
            lo, hi = float(cfg["minValue"]), float(cfg["maxValue"])
            if not (lo <= region["x_start"] and region["x_stop"] <= hi):
                errors.append(f"region X outside soft limits [{lo}, {hi}]")
        except Exception:
            pass
        return errors

    def launch(self) -> str | None:
        """Validate, build the plan generator, submit. Returns procedure id."""
        errors = self.validate_scan()
        self._errors_label.setText("; ".join(errors))
        if errors:
            return None
        catalog = self._catalog()
        flyer = catalog.get_ophyd_device(self._flyer_name)
        energy = catalog.get_ophyd_device(self._energy_name)
        y = catalog.get_ophyd_device(self._y_name)
        if not all((flyer, energy, y)):
            self._errors_label.setText("devices not connected")
            return None
        from .plans import stxm_energy_stack
        plan = stxm_energy_stack(
            flyer, energy, y,
            energies=self._energy_editor.energies(),
            ny=self._ny.value(), nx=self._nx.value(),
            dwell_ms=self._dwell.value(),
            **self.region_kwargs(),
        )
        pid = self._engine().submit(plan, name="stxm_energy_stack")
        self._status_label.setText(f"submitted: {pid}")
        return pid


class StxmScanPanelPlugin(PanelPlugin):
    """Contributes the STXM scan-definition panel."""

    @property
    def name(self) -> str:
        return "stxm_scan"

    def get_panel_class(self) -> type[BasePanel]:
        return STXMScanPanel
```

Add the imports at the top of `scan_panel.py`:

```python
from lightfall.plugins.panel_plugin import PanelPlugin
```

- [ ] **Step 4: Add the manifest entry (preloaded, like core panel plugins)**

```python
        PluginEntry(
            "panel",
            "stxm_scan",
            "lightfall_pystxmcontrol.scan_panel:StxmScanPanelPlugin",
            preload=True,
        ),
```

- [ ] **Step 5: Run the full panel test file**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_scan_panel.py -v
```

Expected: PASS (Tasks 12 + 13).

- [ ] **Step 6: Commit**

```bash
git add src/lightfall_pystxmcontrol/scan_panel.py src/lightfall_pystxmcontrol/manifest.py tests/test_scan_panel.py
git commit -m "feat: scan panel devices/validation/submit + panel plugin + manifest entry"
```

---

### Task 14: E2E smoke + README + full suite

**Files:**
- Create: `scripts/smoke_energy_stack.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above; mirrors `scripts/smoke_stxm_live_map.py` (local streaming Tiled server + `TiledService` + `BlueskyEngine` + `StreamBridge`).

- [ ] **Step 1: Write the smoke script**

Copy `scripts/smoke_stxm_live_map.py` as the skeleton (server bootstrap `_free_port`/`_wait_http`/`start_server`, `_pump`, teardown incl. bounded bridge disconnects and the `os._exit(0)` clean-pass exit) and replace the scan/assert middle with the energy stack. The essential deltas:

```python
# scripts/smoke_energy_stack.py  (skeleton from smoke_stxm_live_map.py; deltas below)
"""Phase-A capstone smoke: energy-stack runs through BlueskyEngine, lands in
Tiled in the contract layout (validated), and the stack viz fills LIVE.

    QT_QPA_PLATFORM=offscreen \
    C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/smoke_energy_stack.py
"""
NE, NY, NX = 2, 3, 4
ENERGIES = [500.0, 510.0]
MAP_KEY = "STXMLineFlyer"

# --- in run_energy_stack(base_url, app): same TiledService/engine bootstrap as
#     run_fly_scan, then: ---
    from lightfall_pystxmcontrol.plans import stxm_energy_stack
    flyer = PystxmLineFlyer(stxm_config.DEFAULT_COUNTER,
                            stxm_config.DEFAULT_AXES["SampleX"])   # default name is the map key now
    yax = PystxmAxis(stxm_config.DEFAULT_AXES["SampleY"], name="SampleY")
    en = PystxmAxis(stxm_config.DEFAULT_AXES["energy"], name="energy")
    # connect all three; subscribe docs; then:
    engine(stxm_energy_stack(flyer, en, yax, energies=ENERGIES,
                             y_start=-5, y_stop=5, ny=NY,
                             x_start=-5, x_stop=5, nx=NX, dwell_ms=1.0))

# --- after the run completes: validate BOTH the document stream and the node ---
    from lightfall_pystxmcontrol import contract
    errors = contract.validate_run_documents(docs)
    assert errors == [], f"contract violations: {errors}"

# --- confirm_node: expect the growing 2-D rows array ---
    assert shape == (NE * NY, NX), f"rows node shape {shape} != ({NE * NY}, {NX})"

# --- live stack: replace StxmMapVisualization block with ---
    from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization
    stack_viz = StxmStackVisualization()
    stack_viz.set_run(run)
    stack_viz.set_stream("primary")           # allocates (NE, NY, NX) cube from start doc

    def _cube_full() -> bool:
        cube = stack_viz.current_cube()
        return cube is not None and not np.isnan(cube).any() and (np.nanmax(cube) > 0)

    bridge = StreamBridge()
    bridge.update_received.connect(stack_viz.on_stream_update)
    bridges.append(bridge)
    bridge.connect_node(run["primary"][MAP_KEY])   # array node — never a column facet
    assert _pump(app, _cube_full, timeout=40.0), "stack cube did not fill via push"
    cube = stack_viz.current_cube()
    print(f"SUCCESS: energy stack {cube.shape} filled live; "
          f"min={np.nanmin(cube):g} max={np.nanmax(cube):g}; contract valid")
```

- [ ] **Step 2: Run the smoke**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/smoke_energy_stack.py
```

Expected: `SUCCESS: energy stack (2, 3, 4) filled live; ... contract valid`, exit 0. (Requires the local Tiled streaming server bootstrap from the skeleton — same `tiled` version/config as `smoke_stxm_live_map.py`. Adjust the scratch CONFIG path to this session's scratchpad.)

- [ ] **Step 3: Update README.md**

Add a "Phase A: energy stacks" section after the existing feature description:

```markdown
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
```

- [ ] **Step 4: Full suite, then commit**

```bash
QT_QPA_PLATFORM=offscreen C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ -q
```

Expected: ALL PASS.

```bash
git add scripts/smoke_energy_stack.py README.md
git commit -m "feat: Phase A capstone smoke + README (energy stack e2e via Tiled push)"
```

---

## Out of scope (spec §3.5 — do NOT build)

New pystxmcontrol drivers; `derivedEnergy` physics; spiral/ptycho/focus/point-spectrum plans; multi-region scans; per-range dwell; multi-channel acquisition; real hardware; `FlyMotorInfo`/`StandardDetector`/`StreamResource`; lightfall-core changes; changes to David's repo; `alsapi` metadata.
