# STXM-Live External NATS Analysis Service — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the option-5 layer-3 external analysis service: a new headless `stxm-live` repo that receives `stxm.run.bind` over NATS, polls the energy-stack run in Tiled, publishes an incremental I(E) spectrum inline over NATS, runs pystxmcontrol's `stack` reduction at run-stop into a durable `stxm_analysis/` Tiled stream — plus the in-Lightfall half in `lightfall-pystxmcontrol` (binder, Qt client, spectrum panel).

**Architecture:** Two repos joined only by the versioned NATS contract (spec §3). `stxm-live` is raw `nats-py` + `tiled.client` + its own read-side `contract.py`; it never imports lightfall. The in-Lightfall half mirrors the XPCS `binding.py`/`client.py`/`panel.py` shapes exactly (injectable deps, FakeIPC tests, PanelPlugin manifest entry).

**Tech Stack:** Python 3.12 (stxm-live venv, numpy<2), nats-py, tiled[client], bluesky-tiled-plugins (`_RunWriter`), pydantic v2, click, pystxmcontrol (`--no-deps`), pytest + pytest-asyncio; in-Lightfall half: PySide6/pyqtgraph via lightfall's 3.14 venv.

**Spec:** `docs/superpowers/specs/2026-07-09-stxm-live-nats-analysis-design.md` (this repo). Companion: `2026-07-07-stxm-lightfall-option5-design.md`.

## Global Constraints

- **JSON-only over NATS** — never arrays bigger than the nE-length spectrum; full arrays go via Tiled.
- **stxm-live never imports `lightfall` or `lightfall_pystxmcontrol`** — only `nats`, `tiled.client`, `bluesky_tiled_plugins`, `numpy`, `pystxmcontrol` (for stack.py).
- **The binder never blocks or breaks the RunEngine** — document callback body fully wrapped in try/except.
- **Never subscribe to a scalar Tiled column facet** — stxm-live POLLS the array node `run["primary"][data_field]`.
- **`contract_version = 1`** travels in the start doc (already, Phase A) and in the bind; mismatch → logged refusal, no crash.
- **Subject convention (spec §3 correction, matches XPCS reality):** all `stxm.*` subjects are UNPREFIXED on the bus (Lightfall's `IPCService.publish/subscribe` take subjects verbatim; XPCS does the same). `lightfall_prefix` is used ONLY to build `{prefix}.auth.request`, and is still included in the bind payload.
- **stxm-live repo:** scaffold locally at `C:\Users\rp\PycharmProjects\ncs\stxm-live`; `git init` + local commits only. **Ron creates the GitHub remote and drives all pushes.**
- **In-Lightfall half:** worktree off `lightfall-pystxmcontrol` `main`, branch `feature/stxm-live-analysis`. Kept local; Ron drives PRs.
- **Test commands:**
  - stxm-live: `C:/Users/rp/PycharmProjects/ncs/stxm-live/.venv/Scripts/python -m pytest tests -v` (own venv, created in Task 1).
  - plugin worktree: `QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/... -v` — never bare `pytest`; `PYTHONPATH=src` is required in a worktree (editable install resolves to the main checkout otherwise).
- **git:** explicit paths only (never `git add -A`). Commit trailers: `Co-Authored-By: Claude <model> <noreply@anthropic.com>` + `Claude-Session: <url>`.
- **hatch + hatch-vcs** for the new package; version needs at least one git tag → tag `v0.1.0` after the first commit.
- Python for stxm-live venv: `py -3.12` (fall back `py -3.11`); numpy<2 has no 3.13+ wheels here and pystxmcontrol pins `numpy<2.0`.

## File Structure

**Repo A — `C:\Users\rp\PycharmProjects\ncs\stxm-live` (new):**

| File | Responsibility |
|---|---|
| `pyproject.toml`, `README.md`, `.gitignore` | packaging (hatch+hatch-vcs), contract doc verbatim |
| `src/stxm_live/contract.py` | read-side contract: `parse_start_stxm`, `cube_from_rows`, `decode_line_index`, version guard |
| `src/stxm_live/config.py` | pydantic `AppConfig` (`NatsConfig`, `TiledConfig`, poll interval) |
| `src/stxm_live/cli.py` | `stxm-live run` click entry point |
| `src/stxm_live/nats_client.py` | raw nats-py connect + `auth.request` + pub/sub helpers |
| `src/stxm_live/service.py` | event loop: bind→poll task→publish spectrum; stop→reduce+write; status/error; discovery |
| `src/stxm_live/tiled_io.py` | `connect_tiled`, `RunReader` (poll rows node), `AnalysisWriter` (`_RunWriter` → `stxm_analysis/` stream) |
| `src/stxm_live/analysis/base.py` | `Reducer` protocol |
| `src/stxm_live/analysis/spectrum.py` | `IntensitySpectrumReducer` (whole-frame mean I(E)) |
| `src/stxm_live/analysis/stack_adapter.py` | `StackReducer` wrapping pystxmcontrol `stack` (OD at run-stop) |
| `tests/…` | unit per module + `test_e2e_smoke.py`; `tests/fixtures/golden_energy_stack_run.json` (copied from Phase A) |

**Repo B — `lightfall-pystxmcontrol` worktree (branch `feature/stxm-live-analysis`):**

| File | Responsibility |
|---|---|
| `src/lightfall_pystxmcontrol/stxm_analysis_client.py` | `StxmAnalysisClient(QObject)` over IPCService |
| `src/lightfall_pystxmcontrol/stxm_binder.py` | `StxmRunBinder` — RE start/stop → bind/stop publishes |
| `src/lightfall_pystxmcontrol/stxm_spectrum_panel.py` | `StxmSpectrumPanel(BasePanel)` + `StxmSpectrumPanelPlugin(PanelPlugin)` |
| `src/lightfall_pystxmcontrol/manifest.py` (modify) | add panel `PluginEntry` |
| `tests/test_stxm_analysis_client.py`, `tests/test_stxm_binder.py`, `tests/test_stxm_spectrum_panel.py`, `tests/conftest.py` (new: FakeIPC) | unit tests, XPCS pattern |

---

### Task 1: stxm-live repo scaffold + read-side contract

**Files:**
- Create: `C:\Users\rp\PycharmProjects\ncs\stxm-live\pyproject.toml`, `README.md`, `.gitignore`, `src/stxm_live/__init__.py`, `src/stxm_live/contract.py`
- Test: `tests/test_contract.py`
- Also: create the venv, `git init`, tag `v0.1.0`.

**Interfaces:**
- Produces: `contract.CONTRACT_VERSION = 1`; `StxmRunInfo` dataclass (`run_uid, nE, ny, nx, energies: list[float], data_field: str`); `parse_start_stxm(run_uid: str, start_doc: dict) -> StxmRunInfo | None` (None + log on missing `stxm` key or version mismatch); `decode_line_index(row: int, ny: int) -> tuple[int, int]`; `cube_from_rows(rows: np.ndarray, shape: tuple[int,int,int]) -> np.ndarray`.

- [ ] **Step 1: Scaffold repo, venv, packaging**

```powershell
mkdir C:\Users\rp\PycharmProjects\ncs\stxm-live
cd C:\Users\rp\PycharmProjects\ncs\stxm-live
git init
py -3.12 -m venv .venv   # fall back: py -3.11
```

`pyproject.toml`:

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[project]
name = "stxm-live"
description = "Headless STXM analysis service: NATS-bound, Tiled-fed, seed of the ALS STXM analysis stack"
readme = "README.md"
requires-python = ">=3.11"
dynamic = ["version"]
dependencies = [
    "numpy<2.0",
    "nats-py",
    "tiled[client]",
    "bluesky-tiled-plugins",
    "pydantic>=2",
    "click",
    "pyyaml",
    "loguru",
]

[project.optional-dependencies]
# pystxmcontrol is installed separately with --no-deps (GUI/instrument deps skipped);
# these are the runtime deps stack.py actually imports at module top.
stack = [
    "scipy",
    "scikit-image",
    "scikit-learn",
    "matplotlib",
    "opencv-python-headless",
    "h5py",
]
test = ["pytest", "pytest-asyncio", "tiled[server]", "adbc-driver-sqlite", "nats-server-bin"]

[project.scripts]
stxm-live = "stxm_live.cli:main"

[tool.hatch.version]
source = "vcs"

[tool.hatch.build.targets.wheel]
packages = ["src/stxm_live"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

`.gitignore`: `.venv/`, `__pycache__/`, `*.egg-info/`, `dist/`, `.pytest_cache/`.

`README.md`: project one-liner, the venv/install commands below, and **the NATS contract table from spec §3.1 verbatim** (both repos document the contract — copy the table + the subject-prefix rule from Global Constraints).

Install:

```powershell
.venv\Scripts\python -m pip install -e ".[stack,test]"
.venv\Scripts\python -m pip install --no-deps "pystxmcontrol @ git+https://github.com/als-controls/pystxmcontrol.git@fa801472"
```

(Use the exact same git ref as `lightfall-pystxmcontrol`'s `hardware` extra — check its `pyproject.toml` and copy the full pinned URL.)

- [ ] **Step 2: Write the failing contract tests**

`tests/test_contract.py`:

```python
import numpy as np
from stxm_live import contract


def _start_doc(version=1):
    return {
        "plan_name": "stxm_energy_stack",
        "stxm": {
            "contract_version": version,
            "shape": [2, 3, 4],
            "energies": [500.0, 510.0],
            "dwell_ms": 1.0,
            "x_extent": [-4.0, 4.0],
            "y_extent": [-2.0, 2.0],
            "x_motor": "SampleX",
            "y_motor": "SampleY",
            "energy_motor": "energy",
            "data_field": "STXMLineFlyer",
        },
    }


def test_parse_start_stxm():
    info = contract.parse_start_stxm("uid1", _start_doc())
    assert (info.run_uid, info.nE, info.ny, info.nx) == ("uid1", 2, 3, 4)
    assert info.energies == [500.0, 510.0]
    assert info.data_field == "STXMLineFlyer"


def test_parse_rejects_version_mismatch():
    assert contract.parse_start_stxm("u", _start_doc(version=99)) is None


def test_parse_rejects_non_stxm_run():
    assert contract.parse_start_stxm("u", {"plan_name": "count"}) is None


def test_decode_line_index():
    assert contract.decode_line_index(0, 3) == (0, 0)
    assert contract.decode_line_index(4, 3) == (1, 1)


def test_cube_from_rows_nan_fills():
    rows = np.arange(8, dtype=float).reshape(2, 4)
    cube = contract.cube_from_rows(rows, (2, 3, 4))
    assert cube.shape == (2, 3, 4)
    assert cube[0, 0, 0] == 0.0 and cube[0, 1, 3] == 7.0
    assert np.isnan(cube[0, 2]).all() and np.isnan(cube[1]).all()


def test_cube_from_rows_empty():
    cube = contract.cube_from_rows(np.empty((0, 4)), (2, 3, 4))
    assert np.isnan(cube).all()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests\test_contract.py -v` — Expected: FAIL (ModuleNotFoundError / AttributeError).

- [ ] **Step 4: Implement `src/stxm_live/contract.py`**

```python
"""Read-side contract for stxm_energy_stack runs (option-5 spec section 4).

Re-implemented here per the stxm-live design doc; stxm-live never imports
lightfall_pystxmcontrol. seq_num = iE*ny + iy + 1; row index = seq_num - 1.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from loguru import logger

CONTRACT_VERSION = 1


@dataclass(frozen=True)
class StxmRunInfo:
    run_uid: str
    nE: int
    ny: int
    nx: int
    energies: list[float]
    data_field: str


def parse_start_stxm(run_uid: str, start_doc: dict) -> StxmRunInfo | None:
    stxm = start_doc.get("stxm")
    if not isinstance(stxm, dict):
        logger.info(f"run {run_uid}: no stxm metadata; ignoring")
        return None
    version = stxm.get("contract_version")
    if version != CONTRACT_VERSION:
        logger.warning(
            f"run {run_uid}: contract_version {version} != {CONTRACT_VERSION}; refusing"
        )
        return None
    nE, ny, nx = (int(v) for v in stxm["shape"])
    return StxmRunInfo(
        run_uid=run_uid,
        nE=nE, ny=ny, nx=nx,
        energies=[float(e) for e in stxm["energies"]],
        data_field=str(stxm["data_field"]),
    )


def decode_line_index(row: int, ny: int) -> tuple[int, int]:
    return divmod(int(row), int(ny))


def cube_from_rows(rows: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    nE, ny, nx = (int(v) for v in shape)
    flat = np.full((nE * ny, nx), np.nan, dtype=float)
    rows = np.asarray(rows, dtype=float)
    if rows.ndim == 2 and rows.shape[1] == nx and rows.shape[0] > 0:
        k = min(rows.shape[0], nE * ny)
        flat[:k] = rows[:k]
    return flat.reshape(nE, ny, nx)
```

`src/stxm_live/__init__.py`: empty.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests\test_contract.py -v` — Expected: 6 PASS.

- [ ] **Step 6: Commit and tag**

```powershell
git add pyproject.toml README.md .gitignore src/stxm_live/__init__.py src/stxm_live/contract.py tests/test_contract.py
git commit -m "feat: scaffold stxm-live with read-side contract"
git tag v0.1.0
```

---

### Task 2: IntensitySpectrumReducer

**Files:**
- Create: `src/stxm_live/analysis/__init__.py`, `src/stxm_live/analysis/base.py`, `src/stxm_live/analysis/spectrum.py`
- Test: `tests/test_spectrum.py`

**Interfaces:**
- Consumes: `contract.StxmRunInfo`.
- Produces: `Reducer` protocol (`update(cube, n_complete) -> bool`, `finalize(cube) -> dict[str, np.ndarray]`); `IntensitySpectrumReducer(info: StxmRunInfo)` with attrs `intensity: list[float | None]` (length nE), `energies_done: int`, `seq: int`; `update()` returns True when new energies completed (increments `seq`); `payload() -> dict` — the exact `stxm.spectrum.updated` payload (spec §3.1).

- [ ] **Step 1: Write the failing tests**

`tests/test_spectrum.py`:

```python
import numpy as np
from stxm_live.analysis.spectrum import IntensitySpectrumReducer
from stxm_live.contract import StxmRunInfo


def _info():
    return StxmRunInfo("uid1", nE=2, ny=3, nx=4,
                       energies=[500.0, 510.0], data_field="STXMLineFlyer")


def _cube(fill0=2.0, fill1=6.0):
    cube = np.full((2, 3, 4), np.nan)
    cube[0] = fill0
    cube[1] = fill1
    return cube


def test_incremental_update():
    r = IntensitySpectrumReducer(_info())
    cube = _cube()
    cube[1] = np.nan  # only energy 0 acquired
    assert r.update(cube, n_complete=1) is True
    assert r.intensity == [2.0, None]
    assert r.energies_done == 1 and r.seq == 1
    # no new frames -> no publish
    assert r.update(cube, n_complete=1) is False
    assert r.seq == 1


def test_full_update_and_payload():
    r = IntensitySpectrumReducer(_info())
    assert r.update(_cube(), n_complete=2) is True
    p = r.payload()
    assert p == {
        "run_uid": "uid1",
        "energies": [500.0, 510.0],
        "intensity": [2.0, 6.0],
        "energies_done": 2,
        "seq": 1,
    }


def test_finalize_returns_spectrum_arrays():
    r = IntensitySpectrumReducer(_info())
    out = r.finalize(_cube())
    assert np.allclose(out["energies"], [500.0, 510.0])
    assert np.allclose(out["intensity"], [2.0, 6.0])
```

- [ ] **Step 2: Run to verify FAIL** — `.venv\Scripts\python -m pytest tests\test_spectrum.py -v`

- [ ] **Step 3: Implement**

`src/stxm_live/analysis/base.py`:

```python
from __future__ import annotations

from typing import Protocol

import numpy as np


class Reducer(Protocol):
    def update(self, cube: np.ndarray, n_complete: int) -> bool:
        """Incremental step. Returns True if there is something new to publish."""
        ...

    def finalize(self, cube: np.ndarray) -> dict[str, np.ndarray]:
        """Run-complete reduction. Returns named products for the durable stream."""
        ...
```

`src/stxm_live/analysis/spectrum.py`:

```python
"""Incremental whole-frame-mean I(E) reducer (v1; ROI-restricted spectra deferred)."""
from __future__ import annotations

import numpy as np

from stxm_live.contract import StxmRunInfo


class IntensitySpectrumReducer:
    def __init__(self, info: StxmRunInfo) -> None:
        self._info = info
        self.intensity: list[float | None] = [None] * info.nE
        self.energies_done = 0
        self.seq = 0

    def update(self, cube: np.ndarray, n_complete: int) -> bool:
        n_complete = min(int(n_complete), self._info.nE)
        if n_complete <= self.energies_done:
            return False
        for iE in range(self.energies_done, n_complete):
            self.intensity[iE] = float(np.nanmean(cube[iE]))
        self.energies_done = n_complete
        self.seq += 1
        return True

    def payload(self) -> dict:
        return {
            "run_uid": self._info.run_uid,
            "energies": list(self._info.energies),
            "intensity": list(self.intensity),
            "energies_done": self.energies_done,
            "seq": self.seq,
        }

    def finalize(self, cube: np.ndarray) -> dict[str, np.ndarray]:
        intensity = np.nanmean(cube, axis=(1, 2))
        return {
            "energies": np.asarray(self._info.energies, dtype=float),
            "intensity": np.asarray(intensity, dtype=float),
        }
```

`analysis/__init__.py`: empty.

- [ ] **Step 4: Run to verify PASS** — `.venv\Scripts\python -m pytest tests\test_spectrum.py -v` (3 PASS)

- [ ] **Step 5: Commit**

```powershell
git add src/stxm_live/analysis tests/test_spectrum.py
git commit -m "feat: incremental whole-frame I(E) spectrum reducer"
```

---

### Task 3: pydantic config + click CLI

**Files:**
- Create: `src/stxm_live/config.py`, `src/stxm_live/cli.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `NatsConfig(url="nats://127.0.0.1:4222", tls_ca=None, tls_insecure=False, lightfall_prefix="als.7011", app_name="stxm-live", app_version="", auth_timeout=70.0, connect_timeout=5.0)`; `TiledConfig(url="", api_key=None)`; `AppConfig(nats: NatsConfig, tiled: TiledConfig, poll_interval_s=1.0)`; `load_config(path: str | None, **overrides) -> AppConfig`; CLI `stxm-live run --nats-url --lightfall-prefix --poll-interval --config config.yml`.

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:

```python
from click.testing import CliRunner

from stxm_live.cli import main
from stxm_live.config import AppConfig, load_config


def test_defaults():
    cfg = AppConfig()
    assert cfg.nats.url == "nats://127.0.0.1:4222"
    assert cfg.nats.lightfall_prefix == "als.7011"
    assert cfg.nats.app_name == "stxm-live"
    assert cfg.poll_interval_s == 1.0
    assert cfg.tiled.url == ""


def test_yaml_and_overrides(tmp_path):
    p = tmp_path / "c.yml"
    p.write_text("nats:\n  url: nats://broker:4222\npoll_interval_s: 0.2\n")
    cfg = load_config(str(p), nats_url="nats://cli-wins:4222")
    assert cfg.nats.url == "nats://cli-wins:4222"
    assert cfg.poll_interval_s == 0.2


def test_cli_run_wires_config(monkeypatch):
    captured = {}
    monkeypatch.setattr("stxm_live.cli._run_service",
                        lambda cfg: captured.setdefault("cfg", cfg))
    result = CliRunner().invoke(
        main, ["run", "--nats-url", "nats://x:4222", "--lightfall-prefix", "als.dev"])
    assert result.exit_code == 0
    assert captured["cfg"].nats.url == "nats://x:4222"
    assert captured["cfg"].nats.lightfall_prefix == "als.dev"
```

- [ ] **Step 2: Run to verify FAIL** — `.venv\Scripts\python -m pytest tests\test_config.py -v`

- [ ] **Step 3: Implement**

`src/stxm_live/config.py`:

```python
from __future__ import annotations

import yaml
from pydantic import BaseModel


class NatsConfig(BaseModel):
    url: str = "nats://127.0.0.1:4222"
    tls_ca: str | None = None
    tls_insecure: bool = False
    lightfall_prefix: str = "als.7011"
    app_name: str = "stxm-live"
    app_version: str = ""
    auth_timeout: float = 70.0  # > 60s Lightfall trust-dialog timeout
    connect_timeout: float = 5.0


class TiledConfig(BaseModel):
    url: str = ""
    api_key: str | None = None


class AppConfig(BaseModel):
    nats: NatsConfig = NatsConfig()
    tiled: TiledConfig = TiledConfig()
    poll_interval_s: float = 1.0


def load_config(path: str | None = None, *, nats_url: str | None = None,
                lightfall_prefix: str | None = None,
                poll_interval_s: float | None = None) -> AppConfig:
    data = {}
    if path:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    cfg = AppConfig(**data)
    if nats_url:
        cfg.nats.url = nats_url
    if lightfall_prefix:
        cfg.nats.lightfall_prefix = lightfall_prefix
    if poll_interval_s is not None:
        cfg.poll_interval_s = poll_interval_s
    return cfg
```

`src/stxm_live/cli.py`:

```python
from __future__ import annotations

import click

from stxm_live.config import AppConfig, load_config


def _run_service(cfg: AppConfig) -> None:  # patched in tests; real impl in Task 8
    from stxm_live.service import StxmLiveService
    StxmLiveService(cfg).main()


@click.group()
def main() -> None:
    """stxm-live: headless STXM analysis service."""


@main.command()
@click.option("--nats-url", default=None, help="NATS broker URL")
@click.option("--lightfall-prefix", default=None, help="Lightfall topic prefix (auth subject)")
@click.option("--poll-interval", "poll_interval_s", type=float, default=None)
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
def run(nats_url, lightfall_prefix, poll_interval_s, config_path) -> None:
    """Run the analysis service."""
    cfg = load_config(config_path, nats_url=nats_url,
                      lightfall_prefix=lightfall_prefix,
                      poll_interval_s=poll_interval_s)
    _run_service(cfg)
```

- [ ] **Step 4: Run to verify PASS** — `.venv\Scripts\python -m pytest tests\test_config.py -v` (3 PASS)

- [ ] **Step 5: Commit**

```powershell
git add src/stxm_live/config.py src/stxm_live/cli.py tests/test_config.py
git commit -m "feat: pydantic config + click CLI"
```

---

### Task 4: NATS client (connect, auth handshake, pub/sub)

**Files:**
- Create: `src/stxm_live/nats_client.py`
- Test: `tests/test_nats_client.py`

**Interfaces:**
- Consumes: `NatsConfig`.
- Produces: `NatsClient(config: NatsConfig)` with `async connect()`, `async close()`, `async authenticate() -> dict | None` (requests `{prefix}.auth.request` with `{app_name, app_version}`; caches + returns `{tiled_token, tiled_url, session_id}` on approved; returns None + logs on denied/timeout — auth failure must NOT be fatal: per-run creds arrive in each bind), `tiled_credentials: dict | None` attr, `async publish(subject: str, payload: dict)` (JSON-encodes), `async subscribe(subject: str, cb)` (cb receives decoded dict + reply subject), `async reply(msg, payload: dict)`. Subjects passed verbatim (no prefixing).

- [ ] **Step 1: Write the failing tests**

`tests/test_nats_client.py`:

```python
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from stxm_live.config import NatsConfig
from stxm_live.nats_client import NatsClient


def _client_with_fake_nc(reply_payload=None):
    c = NatsClient(NatsConfig())
    nc = MagicMock()
    if reply_payload is not None:
        msg = MagicMock()
        msg.data = json.dumps(reply_payload).encode()
        nc.request = AsyncMock(return_value=msg)
    else:
        nc.request = AsyncMock(side_effect=TimeoutError)
    nc.publish = AsyncMock()
    nc.subscribe = AsyncMock()
    c._nc = nc
    return c, nc


async def test_authenticate_approved_caches_credentials():
    c, nc = _client_with_fake_nc(
        {"status": "approved", "tiled_token": "k", "tiled_url": "http://t", "session_id": "s"})
    creds = await c.authenticate()
    assert creds["tiled_token"] == "k"
    assert c.tiled_credentials == creds
    subject = nc.request.call_args[0][0]
    assert subject == "als.7011.auth.request"
    sent = json.loads(nc.request.call_args[0][1])
    assert sent["app_name"] == "stxm-live"


async def test_authenticate_denied_returns_none():
    c, _ = _client_with_fake_nc({"status": "denied", "reason": "denied"})
    assert await c.authenticate() is None
    assert c.tiled_credentials is None


async def test_authenticate_timeout_returns_none():
    c, _ = _client_with_fake_nc(None)
    assert await c.authenticate() is None


async def test_publish_json_encodes():
    c, nc = _client_with_fake_nc({})
    await c.publish("stxm.status", {"state": "idle"})
    subject, data = nc.publish.call_args[0]
    assert subject == "stxm.status"
    assert json.loads(data) == {"state": "idle"}


async def test_connect_plaintext_no_tls(monkeypatch):
    captured = {}

    async def fake_connect(url, **kw):
        captured.update(kw, url=url)
        return MagicMock()

    monkeypatch.setattr("stxm_live.nats_client.nats.connect", fake_connect)
    c = NatsClient(NatsConfig(url="nats://127.0.0.1:4222"))
    await c.connect()
    assert captured["url"] == "nats://127.0.0.1:4222"
    assert "tls" not in captured
```

- [ ] **Step 2: Run to verify FAIL** — `.venv\Scripts\python -m pytest tests\test_nats_client.py -v`

- [ ] **Step 3: Implement `src/stxm_live/nats_client.py`**

```python
"""Raw nats-py client: connect, Lightfall auth handshake, JSON pub/sub.

Subjects are passed verbatim — the stxm.* namespace is unprefixed on the bus
(XPCS convention). lightfall_prefix is used only for {prefix}.auth.request.
"""
from __future__ import annotations

import json
import ssl

import nats
from loguru import logger

from stxm_live.config import NatsConfig


class NatsClient:
    def __init__(self, config: NatsConfig) -> None:
        self._config = config
        self._nc = None
        self.tiled_credentials: dict | None = None

    def _build_tls_context(self) -> ssl.SSLContext | None:
        cfg = self._config
        if not cfg.tls_ca and not cfg.tls_insecure:
            return None
        ctx = ssl.create_default_context()
        if cfg.tls_ca:
            ctx.load_verify_locations(cfg.tls_ca)
        if cfg.tls_insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def connect(self) -> None:
        kwargs = dict(connect_timeout=self._config.connect_timeout)
        tls = self._build_tls_context()
        if tls is not None:
            kwargs["tls"] = tls
        self._nc = await nats.connect(self._config.url, **kwargs)
        logger.info(f"connected to NATS at {self._config.url}")

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None

    async def authenticate(self) -> dict | None:
        cfg = self._config
        subject = f"{cfg.lightfall_prefix}.auth.request"
        payload = json.dumps(
            {"app_name": cfg.app_name, "app_version": cfg.app_version}).encode()
        try:
            msg = await self._nc.request(subject, payload, timeout=cfg.auth_timeout)
        except Exception as ex:
            logger.warning(f"auth.request failed: {ex}")
            return None
        reply = json.loads(msg.data)
        if reply.get("status") != "approved":
            logger.warning(f"auth denied: {reply.get('reason', '')}")
            return None
        self.tiled_credentials = {
            "tiled_token": reply.get("tiled_token"),
            "tiled_url": reply.get("tiled_url", ""),
            "session_id": reply.get("session_id"),
        }
        logger.info("auth approved; Tiled credentials cached")
        return self.tiled_credentials

    async def publish(self, subject: str, payload: dict) -> None:
        await self._nc.publish(subject, json.dumps(payload).encode())

    async def subscribe(self, subject: str, cb) -> None:
        async def handler(msg):
            try:
                data = json.loads(msg.data) if msg.data else {}
            except json.JSONDecodeError:
                logger.warning(f"non-JSON message on {msg.subject}; dropped")
                return
            await cb(data, msg)

        await self._nc.subscribe(subject, cb=handler)

    async def reply(self, msg, payload: dict) -> None:
        if getattr(msg, "reply", None):
            await self._nc.publish(msg.reply, json.dumps(payload).encode())
```

- [ ] **Step 4: Run to verify PASS** — `.venv\Scripts\python -m pytest tests\test_nats_client.py -v` (5 PASS)

- [ ] **Step 5: Commit**

```powershell
git add src/stxm_live/nats_client.py tests/test_nats_client.py
git commit -m "feat: raw nats-py client with Lightfall auth handshake"
```

---

### Task 5: Tiled I/O — connect, RunReader (poll), AnalysisWriter (durable stream)

**Files:**
- Create: `src/stxm_live/tiled_io.py`
- Test: `tests/test_tiled_io.py`

**Interfaces:**
- Consumes: `contract.StxmRunInfo`, `contract.cube_from_rows`.
- Produces:
  - `connect_tiled(url: str, api_key: str | None)` → `tiled.client.from_uri(url, api_key=api_key)`.
  - `RunReader(run_node, info: StxmRunInfo)`: `.read_state() -> tuple[np.ndarray, int]` — reads `run_node["primary"][info.data_field]` (the `(k,nx)` array node), returns `(cube, n_complete)` where `n_complete = k // ny` (count of fully-acquired energies); raises `KeyError` while the stream doesn't exist yet (caller retries).
  - `AnalysisWriter(tiled_client, run_uid: str)`: `.write(products: dict[str, np.ndarray]) -> list[str]` — attaches `_RunWriter(client, batch_size=1, max_array_size=0)` to the EXISTING run (`writer.root_node = client[run_uid]`), lazily emits one `stxm_analysis` descriptor whose data_keys are 1-D `dtype:"array"` keys (each product FLATTENED — `_RunWriter` internal arrays are 1-D per event; original shapes recorded in the descriptor's `configuration["product_shapes"]`), one event with the flattened data, then flushes the internal cache (xpcs `_flush` pattern). Returns the product names written. Tiled path of the stream: `<run_uid>/stxm_analysis`.

- [ ] **Step 1: Write the failing tests**

`tests/test_tiled_io.py` (in-memory Tiled server, xpcs `test_tiled_writer.py` pattern):

```python
from pathlib import Path

import numpy as np
import pytest
from tiled.catalog import in_memory
from tiled.client import Context, from_context
from tiled.server.app import build_app

from stxm_live.contract import StxmRunInfo
from stxm_live.tiled_io import AnalysisWriter, RunReader


@pytest.fixture
def client(tmp_path):
    sql_uri = f"sqlite:///{(Path(tmp_path) / 'internal.db').as_posix()}"
    catalog = in_memory(writable_storage=[str(tmp_path), sql_uri])
    app = build_app(catalog)
    with Context.from_app(app) as context:
        yield from_context(context)


def _info():
    return StxmRunInfo("run1", nE=2, ny=3, nx=4,
                       energies=[500.0, 510.0], data_field="STXMLineFlyer")


def _run_with_rows(client, rows):
    run = client.create_container("run1")
    primary = run.create_container("primary")
    primary.write_array(np.asarray(rows, dtype=float), key="STXMLineFlyer")
    return run


def test_reader_counts_complete_energies(client):
    run = _run_with_rows(client, np.ones((4, 4)))  # 4 of 6 rows: energy 0 done
    cube, n_complete = RunReader(run, _info()).read_state()
    assert n_complete == 1
    assert cube.shape == (2, 3, 4)
    assert np.isnan(cube[1, 1]).all()


def test_reader_full(client):
    run = _run_with_rows(client, np.ones((6, 4)))
    _, n_complete = RunReader(run, _info()).read_state()
    assert n_complete == 2


def test_reader_missing_stream_raises_keyerror(client):
    run = client.create_container("run1")
    with pytest.raises(KeyError):
        RunReader(run, _info()).read_state()


def test_analysis_writer_creates_stream(client):
    _run_with_rows(client, np.ones((6, 4)))
    products = {"energies": np.array([500.0, 510.0]),
                "intensity": np.array([1.0, 1.0]),
                "od": np.zeros((2, 3, 4))}
    written = AnalysisWriter(client, "run1").write(products)
    assert set(written) == {"energies", "intensity", "od"}
    stream = client["run1"]["stxm_analysis"]
    assert np.allclose(stream["intensity"].read()[0], [1.0, 1.0])
    assert stream["od"].read().shape == (1, 24)  # flattened, 1 event
    shapes = stream.metadata["configuration"]["product_shapes"]
    assert shapes["od"] == [2, 3, 4]


def test_analysis_writer_missing_run_raises(client):
    with pytest.raises(KeyError):
        AnalysisWriter(client, "nope").write({"x": np.zeros(2)})
```

- [ ] **Step 2: Run to verify FAIL** — `.venv\Scripts\python -m pytest tests\test_tiled_io.py -v`

- [ ] **Step 3: Implement `src/stxm_live/tiled_io.py`**

```python
"""Tiled I/O: connect, poll the rows node, write the durable stxm_analysis stream."""
from __future__ import annotations

import time
from uuid import uuid4

import numpy as np
from bluesky_tiled_plugins.writing.tiled_writer import _RunWriter
from loguru import logger

from stxm_live.contract import StxmRunInfo, cube_from_rows


def connect_tiled(url: str, api_key: str | None):
    from tiled.client import from_uri
    return from_uri(url, api_key=api_key)


class RunReader:
    """Polls the (k, nx) rows array node. NEVER touches scalar column facets."""

    def __init__(self, run_node, info: StxmRunInfo) -> None:
        self._run = run_node
        self._info = info

    def read_state(self) -> tuple[np.ndarray, int]:
        node = self._run["primary"][self._info.data_field]  # KeyError until stream exists
        rows = node.read()
        cube = cube_from_rows(rows, (self._info.nE, self._info.ny, self._info.nx))
        n_complete = min(int(rows.shape[0]) // self._info.ny, self._info.nE)
        return cube, n_complete


class AnalysisWriter:
    """Appends a stxm_analysis BlueskyEventStream to an EXISTING run.

    Arrays are flattened per event (_RunWriter internal arrays are 1-D per
    event, dims hardcoded ("time", "dim_1")); original shapes live in the
    descriptor configuration under "product_shapes".
    """

    STREAM_NAME = "stxm_analysis"

    def __init__(self, tiled_client, run_uid: str) -> None:
        self._client = tiled_client
        self._run_uid = run_uid

    def write(self, products: dict[str, np.ndarray]) -> list[str]:
        run = self._client[self._run_uid]  # KeyError if run absent
        writer = _RunWriter(self._client, batch_size=1, max_array_size=0)
        writer.root_node = run

        flat = {k: np.asarray(v, dtype=float).ravel() for k, v in products.items()}
        shapes = {k: list(np.asarray(v).shape) for k, v in products.items()}
        data_keys = {
            k: {"dtype": "array", "shape": [int(v.size)], "dtype_numpy": "<f8",
                "source": "stxm-live", "object_name": "stxm_live"}
            for k, v in flat.items()
        }
        now = time.time()
        desc_uid = str(uuid4())
        writer.descriptor({
            "uid": desc_uid,
            "run_start": self._run_uid,
            "name": self.STREAM_NAME,
            "time": now,
            "data_keys": data_keys,
            "configuration": {"product_shapes": shapes},
            "object_keys": {"stxm_live": list(flat)},
            "hints": {"fields": []},
        })
        writer.event({
            "uid": str(uuid4()),
            "descriptor": desc_uid,
            "seq_num": 1,
            "time": now,
            "data": {k: v.tolist() for k, v in flat.items()},
            "timestamps": {k: now for k in flat},
        })
        self._flush(writer)
        logger.info(f"wrote {sorted(flat)} to {self._run_uid}/{self.STREAM_NAME}")
        return list(flat)

    @staticmethod
    def _flush(writer) -> None:
        for desc_name, cache in list(writer._internal_data_cache.items()):
            if cache:
                writer._write_internal_data(cache, writer._desc_nodes[desc_name])
                cache.clear()
```

Note for the implementer: if the `configuration` metadata assertion fails because `_RunWriter.descriptor()` stores metadata differently (it stores all descriptor keys except `name`/`object_keys`/`run_start` as container metadata), read the actual metadata layout with `stream.metadata` in the test and adjust the assertion path (e.g. `stream.metadata["configuration"]["product_shapes"]`) — the requirement is only that shapes are recoverable from the stream node.

- [ ] **Step 4: Run to verify PASS** — `.venv\Scripts\python -m pytest tests\test_tiled_io.py -v` (5 PASS)

- [ ] **Step 5: Commit**

```powershell
git add src/stxm_live/tiled_io.py tests/test_tiled_io.py
git commit -m "feat: Tiled reader (poll rows node) + durable stxm_analysis writer"
```

---

### Task 6: StackReducer (pystxmcontrol stack.py adapter)

**Files:**
- Create: `src/stxm_live/analysis/stack_adapter.py`
- Test: `tests/test_stack_adapter.py`

**Interfaces:**
- Consumes: `StxmRunInfo`, a finished `(nE, ny, nx)` cube.
- Produces: `StackReducer(info: StxmRunInfo)` with `finalize(cube) -> dict[str, np.ndarray]` returning `{"od": (nE,ny,nx) array}` (optical density via `stack.calcOD()`); rows still NaN (partial run) are zero-filled before OD with a logged warning; if pystxmcontrol is not importable, `finalize` returns `{}` with a logged warning (service degrades: spectrum-only durable write). v1 products = OD only; NMF/PCA are David's extensions.

- [ ] **Step 1: Write the failing tests**

`tests/test_stack_adapter.py`:

```python
import numpy as np
import pytest

from stxm_live.contract import StxmRunInfo
from stxm_live.analysis.stack_adapter import StackReducer, _HAVE_PYSTXM


def _info():
    return StxmRunInfo("u", nE=2, ny=3, nx=4,
                       energies=[500.0, 510.0], data_field="f")


@pytest.mark.skipif(not _HAVE_PYSTXM, reason="pystxmcontrol not installed")
def test_finalize_produces_od():
    cube = np.full((2, 3, 4), 100.0)
    cube[1] *= 0.5  # more absorption at energy 1
    out = StackReducer(_info()).finalize(cube)
    assert out["od"].shape == (2, 3, 4)
    assert np.all(np.isfinite(out["od"]))
    assert out["od"][1].mean() > out["od"][0].mean()


@pytest.mark.skipif(not _HAVE_PYSTXM, reason="pystxmcontrol not installed")
def test_finalize_tolerates_partial_cube():
    cube = np.full((2, 3, 4), 100.0)
    cube[1] = np.nan  # aborted run
    out = StackReducer(_info()).finalize(cube)
    assert out["od"].shape == (2, 3, 4)
    assert np.all(np.isfinite(out["od"]))


def test_missing_pystxm_degrades(monkeypatch):
    import stxm_live.analysis.stack_adapter as sa
    monkeypatch.setattr(sa, "_HAVE_PYSTXM", False)
    assert StackReducer(_info()).finalize(np.ones((2, 3, 4))) == {}
```

- [ ] **Step 2: Run to verify FAIL** — `.venv\Scripts\python -m pytest tests\test_stack_adapter.py -v`

- [ ] **Step 3: Implement `src/stxm_live/analysis/stack_adapter.py`**

```python
"""Run-complete reduction via pystxmcontrol utils/stack.py (OD in v1)."""
from __future__ import annotations

import numpy as np
from loguru import logger

try:  # headless: force Agg BEFORE stack.py's eager matplotlib import
    import matplotlib
    matplotlib.use("Agg")
    from pystxmcontrol.utils.stack import stack as _Stack
    _HAVE_PYSTXM = True
except Exception as _ex:  # pragma: no cover - environment-dependent
    _Stack = None
    _HAVE_PYSTXM = False
    logger.warning(f"pystxmcontrol unavailable; StackReducer degrades to no-op: {_ex}")

from stxm_live.contract import StxmRunInfo


class StackReducer:
    def __init__(self, info: StxmRunInfo) -> None:
        self._info = info

    def finalize(self, cube: np.ndarray) -> dict[str, np.ndarray]:
        if not _HAVE_PYSTXM:
            logger.warning("StackReducer skipped: pystxmcontrol not installed")
            return {}
        cube = np.asarray(cube, dtype=float)
        if np.isnan(cube).any():
            logger.warning("partial cube: NaN lines zero-filled before OD")
            cube = np.nan_to_num(cube, nan=0.0)
        # calcOD divides by an I0 estimate; keep counts strictly positive
        cube = np.clip(cube, 1e-6, None)
        s = _Stack()
        s.processedFrames = cube
        s.energies = np.asarray(self._info.energies, dtype=float)
        s.calcOD()
        return {"od": np.asarray(s.odFrames, dtype=float)}
```

Note for the implementer: `stack()` with no filename must construct without touching files — if `stack.__init__` requires more attributes before `calcOD()` (e.g. `getIOMask` reading `self.shape`), set them from the cube (`s.shape = cube.shape` etc.) based on the actual AttributeError; keep the adapter the only place with that knowledge. If bare construction proves impossible, compute OD directly (`i0 = frame-mean of the brightest-pixel mask; od = -log(cube/i0)`) and keep the class name/product identical — the contract is the returned `{"od": ...}`.

- [ ] **Step 4: Run to verify PASS** — `.venv\Scripts\python -m pytest tests\test_stack_adapter.py -v` (3 PASS or 2 skipped + 1 pass if env lacks pystxmcontrol — but the Task-1 venv installs it, so expect 3 PASS)

- [ ] **Step 5: Commit**

```powershell
git add src/stxm_live/analysis/stack_adapter.py tests/test_stack_adapter.py
git commit -m "feat: StackReducer OD adapter over pystxmcontrol stack.py"
```

---

### Task 7: Service event loop

**Files:**
- Create: `src/stxm_live/service.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: `NatsClient` (Task 4), `connect_tiled`/`RunReader`/`AnalysisWriter` (Task 5), `IntensitySpectrumReducer` (Task 2), `StackReducer` (Task 6), `parse_start_stxm` (Task 1), `AppConfig` (Task 3).
- Produces: `StxmLiveService(config, *, nats_client=None, tiled_connect=None)` (injectables for tests) with:
  - `main()` — `asyncio.run(self._main())`; connects NATS, subscribes `stxm.run.bind` / `stxm.run.stop`, registers discovery subjects (`_stxm.discover`, `stxm.meta.actions`, `stxm.meta.events` — req/reply returning `{"app_name","app_version","actions":[],"events":[...]}`), fires `authenticate()` as a background task, then idles until SIGINT.
  - `async _handle_bind(data, msg)` — version-guard via payload `contract_version` (mismatch → `stxm.error` + log, no crash); opens Tiled (`tiled_url`/`tiled_api_key` from payload, else cached auth creds, else config) in an executor; reads the run's start doc (`run.metadata["start"]`) → `parse_start_stxm`; non-stxm run → ignore with log; spawns `asyncio.create_task(self._poll_run(...))`; publishes `stxm.status {run_uid, state:"binding", energies_done:0, total:nE}`.
  - `async _poll_run(run_uid)` — loop: `read_state()` in executor (KeyError → stream not yet created → sleep and retry); reducer `update()` → True → publish `stxm.spectrum.updated` (reducer `payload()`) + `stxm.status {state:"reducing", ...}`; sleep `poll_interval_s`; exit when stop-requested AND final state read.
  - `async _handle_stop(data, msg)` — flags the bound run stopped; after the poll task drains: final `read_state()`, `spectrum.finalize()` + `StackReducer.finalize()` → `AnalysisWriter.write()` in an executor → publish `stxm.reduction.complete {run_uid, tiled_path: f"{run_uid}/stxm_analysis", products}`; then `stxm.status {state:"idle"}`. Any exception → `stxm.error {run_uid, error}` + log, service keeps running.
  - One bound run at a time (a second bind while busy replaces the old poll task with a logged warning — v1).

- [ ] **Step 1: Write the failing tests**

`tests/test_service.py` — no real broker; fake `NatsClient` records publishes, handlers invoked directly:

```python
import asyncio
from pathlib import Path

import numpy as np
import pytest
from tiled.catalog import in_memory
from tiled.client import Context, from_context
from tiled.server.app import build_app

from stxm_live.config import AppConfig
from stxm_live.service import StxmLiveService


class FakeNats:
    def __init__(self):
        self.published = []      # (subject, payload)
        self.subscriptions = {}  # subject -> cb
        self.tiled_credentials = None

    async def connect(self): ...
    async def close(self): ...
    async def authenticate(self): return None

    async def publish(self, subject, payload):
        self.published.append((subject, payload))

    async def subscribe(self, subject, cb):
        self.subscriptions[subject] = cb

    async def reply(self, msg, payload):
        self.published.append((getattr(msg, "reply", "?"), payload))


@pytest.fixture
def tiled_client(tmp_path):
    sql_uri = f"sqlite:///{(Path(tmp_path) / 'internal.db').as_posix()}"
    catalog = in_memory(writable_storage=[str(tmp_path), sql_uri])
    with Context.from_app(build_app(catalog)) as context:
        yield from_context(context)


def _make_run(client, uid="runA", rows=6):
    start = {
        "plan_name": "stxm_energy_stack",
        "stxm": {"contract_version": 1, "shape": [2, 3, 4],
                 "energies": [500.0, 510.0], "dwell_ms": 1.0,
                 "x_extent": [-4, 4], "y_extent": [-2, 2],
                 "x_motor": "SampleX", "y_motor": "SampleY",
                 "energy_motor": "energy", "data_field": "STXMLineFlyer"},
    }
    run = client.create_container(uid, metadata={"start": start})
    primary = run.create_container("primary")
    primary.write_array(np.full((rows, 4), 5.0), key="STXMLineFlyer")
    return run


def _service(fake, tiled_client):
    cfg = AppConfig()
    cfg.poll_interval_s = 0.01
    return StxmLiveService(cfg, nats_client=fake,
                           tiled_connect=lambda url, key: tiled_client)


def _bind_payload(uid="runA"):
    return {"run_uid": uid, "tiled_url": "http://local", "tiled_api_key": "k",
            "lightfall_prefix": "als.7011", "contract_version": 1}


async def test_bind_poll_stop_full_cycle(tiled_client):
    fake = FakeNats()
    _make_run(tiled_client)
    svc = _service(fake, tiled_client)
    await svc._handle_bind(_bind_payload(), None)
    for _ in range(200):
        await asyncio.sleep(0.01)
        if any(s == "stxm.spectrum.updated" for s, _ in fake.published):
            break
    spectra = [p for s, p in fake.published if s == "stxm.spectrum.updated"]
    assert spectra and spectra[-1]["energies_done"] == 2
    assert spectra[-1]["intensity"] == [5.0, 5.0]

    await svc._handle_stop({"run_uid": "runA"}, None)
    await svc.wait_idle()
    done = [p for s, p in fake.published if s == "stxm.reduction.complete"]
    assert done and done[0]["tiled_path"] == "runA/stxm_analysis"
    assert "intensity" in done[0]["products"]
    assert np.allclose(
        tiled_client["runA"]["stxm_analysis"]["intensity"].read()[0], [5.0, 5.0])


async def test_bind_version_mismatch_publishes_error(tiled_client):
    fake = FakeNats()
    svc = _service(fake, tiled_client)
    bad = _bind_payload(); bad["contract_version"] = 99
    await svc._handle_bind(bad, None)
    assert any(s == "stxm.error" for s, _ in fake.published)
    assert not svc.busy


async def test_bind_non_stxm_run_ignored(tiled_client):
    fake = FakeNats()
    tiled_client.create_container("plainrun", metadata={"start": {"plan_name": "count"}})
    svc = _service(fake, tiled_client)
    await svc._handle_bind(_bind_payload("plainrun"), None)
    assert not svc.busy
    assert not any(s == "stxm.spectrum.updated" for s, _ in fake.published)


async def test_stop_unknown_run_is_noop(tiled_client):
    fake = FakeNats()
    svc = _service(fake, tiled_client)
    await svc._handle_stop({"run_uid": "ghost"}, None)
    assert not any(s == "stxm.error" for s, _ in fake.published)


async def test_discovery_reply(tiled_client):
    fake = FakeNats()
    svc = _service(fake, tiled_client)
    await svc._register_subscriptions()
    class Msg: reply = "inbox1"
    await fake.subscriptions["_stxm.discover"]({}, Msg())
    replies = [p for s, p in fake.published if s == "inbox1"]
    assert replies and replies[0]["app_name"] == "stxm-live"
    assert "stxm.spectrum.updated" in replies[0]["events"]
```

- [ ] **Step 2: Run to verify FAIL** — `.venv\Scripts\python -m pytest tests\test_service.py -v`

- [ ] **Step 3: Implement `src/stxm_live/service.py`**

```python
"""stxm-live event loop: bind -> poll Tiled -> publish spectrum; stop -> reduce + durable write."""
from __future__ import annotations

import asyncio

from loguru import logger

from stxm_live.analysis.spectrum import IntensitySpectrumReducer
from stxm_live.analysis.stack_adapter import StackReducer
from stxm_live.config import AppConfig
from stxm_live.contract import CONTRACT_VERSION, parse_start_stxm
from stxm_live.nats_client import NatsClient
from stxm_live.tiled_io import AnalysisWriter, RunReader, connect_tiled

EVENTS = ["stxm.spectrum.updated", "stxm.status", "stxm.error", "stxm.reduction.complete"]
ACTIONS: list[str] = []  # v1 has no actions (stxm.roi.set etc. deferred)


class StxmLiveService:
    def __init__(self, config: AppConfig, *, nats_client=None, tiled_connect=None) -> None:
        self._config = config
        self._nats = nats_client or NatsClient(config.nats)
        self._tiled_connect = tiled_connect or connect_tiled
        self._poll_task: asyncio.Task | None = None
        self._stop_requested = asyncio.Event()
        self._current = None  # dict: run_uid, tiled_client, reader, reducer

    @property
    def busy(self) -> bool:
        return self._current is not None

    def main(self) -> None:
        asyncio.run(self._main())

    async def _main(self) -> None:
        await self._nats.connect()
        await self._register_subscriptions()
        asyncio.get_running_loop().create_task(self._authenticate_bg())
        logger.info("stxm-live ready")
        try:
            while True:
                await asyncio.sleep(0.5)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self._nats.close()

    async def _authenticate_bg(self) -> None:
        try:
            await self._nats.authenticate()
        except Exception as ex:
            logger.warning(f"background auth failed: {ex}")

    async def _register_subscriptions(self) -> None:
        await self._nats.subscribe("stxm.run.bind", self._handle_bind)
        await self._nats.subscribe("stxm.run.stop", self._handle_stop)
        await self._nats.subscribe("_stxm.discover", self._handle_discover)
        await self._nats.subscribe("stxm.meta.actions", self._handle_discover)
        await self._nats.subscribe("stxm.meta.events", self._handle_discover)

    async def _handle_discover(self, data, msg) -> None:
        await self._nats.reply(msg, {
            "app_name": self._config.nats.app_name,
            "app_version": self._config.nats.app_version,
            "actions": ACTIONS,
            "events": EVENTS,
        })

    def _resolve_credentials(self, data: dict) -> tuple[str, str | None]:
        url = data.get("tiled_url") or ""
        key = data.get("tiled_api_key")
        cached = self._nats.tiled_credentials or {}
        if not url:
            url = cached.get("tiled_url") or self._config.tiled.url
        if not key:
            key = cached.get("tiled_token") or self._config.tiled.api_key
        return url, key

    async def _handle_bind(self, data: dict, msg) -> None:
        run_uid = data.get("run_uid", "")
        try:
            version = data.get("contract_version", CONTRACT_VERSION)
            if version != CONTRACT_VERSION:
                raise ValueError(
                    f"contract_version {version} != {CONTRACT_VERSION}; refusing bind")
            url, key = self._resolve_credentials(data)
            loop = asyncio.get_running_loop()
            tiled_client = await loop.run_in_executor(
                None, self._tiled_connect, url, key)
            run = await loop.run_in_executor(None, tiled_client.__getitem__, run_uid)
            start = run.metadata.get("start", {})
            info = parse_start_stxm(run_uid, start)
            if info is None:
                logger.info(f"bind ignored for non-stxm run {run_uid}")
                return
            if self._current is not None:
                logger.warning(f"replacing bound run {self._current['run_uid']}")
                await self._teardown_poll()
            self._stop_requested = asyncio.Event()
            self._current = {
                "run_uid": run_uid,
                "tiled_client": tiled_client,
                "reader": RunReader(run, info),
                "reducer": IntensitySpectrumReducer(info),
                "info": info,
            }
            self._poll_task = asyncio.get_running_loop().create_task(self._poll_run())
            await self._nats.publish("stxm.status", {
                "run_uid": run_uid, "state": "binding",
                "energies_done": 0, "total": info.nE})
            logger.info(f"bound run {run_uid} ({info.nE}x{info.ny}x{info.nx})")
        except Exception as ex:
            logger.exception(f"bind failed for {run_uid}")
            await self._nats.publish("stxm.error", {"run_uid": run_uid, "error": str(ex)})

    async def _poll_run(self) -> None:
        cur = self._current
        loop = asyncio.get_running_loop()
        while True:
            try:
                cube, n_complete = await loop.run_in_executor(
                    None, cur["reader"].read_state)
            except KeyError:
                cube, n_complete = None, 0  # stream not created yet
            if cube is not None and cur["reducer"].update(cube, n_complete):
                await self._nats.publish("stxm.spectrum.updated",
                                         cur["reducer"].payload())
                await self._nats.publish("stxm.status", {
                    "run_uid": cur["run_uid"], "state": "reducing",
                    "energies_done": cur["reducer"].energies_done,
                    "total": cur["info"].nE})
            if self._stop_requested.is_set():
                return
            await asyncio.sleep(self._config.poll_interval_s)

    async def _teardown_poll(self) -> None:
        self._stop_requested.set()
        if self._poll_task is not None:
            try:
                await self._poll_task
            except Exception:
                logger.exception("poll task died")
            self._poll_task = None
        self._current = None

    async def _handle_stop(self, data: dict, msg) -> None:
        run_uid = data.get("run_uid", "")
        cur = self._current
        if cur is None or cur["run_uid"] != run_uid:
            logger.info(f"stop for unknown/unbound run {run_uid}; ignoring")
            return
        try:
            self._stop_requested.set()
            if self._poll_task is not None:
                await self._poll_task
                self._poll_task = None
            loop = asyncio.get_running_loop()
            cube, _ = await loop.run_in_executor(None, cur["reader"].read_state)
            products = cur["reducer"].finalize(cube)
            products.update(StackReducer(cur["info"]).finalize(cube))
            writer = AnalysisWriter(cur["tiled_client"], run_uid)
            written = await loop.run_in_executor(None, writer.write, products)
            await self._nats.publish("stxm.reduction.complete", {
                "run_uid": run_uid,
                "tiled_path": f"{run_uid}/{AnalysisWriter.STREAM_NAME}",
                "products": written})
        except Exception as ex:
            logger.exception(f"reduction failed for {run_uid}")
            await self._nats.publish("stxm.error", {"run_uid": run_uid, "error": str(ex)})
        finally:
            self._current = None
            await self._nats.publish("stxm.status", {
                "run_uid": run_uid, "state": "idle", "energies_done": 0, "total": 0})

    async def wait_idle(self) -> None:
        """Test helper: await completion of any in-flight poll task."""
        if self._poll_task is not None:
            self._stop_requested.set()
            await self._poll_task
            self._poll_task = None
```

- [ ] **Step 4: Run to verify PASS** — `.venv\Scripts\python -m pytest tests\test_service.py -v` (5 PASS). Then run the full suite: `.venv\Scripts\python -m pytest tests -v`.

- [ ] **Step 5: Commit**

```powershell
git add src/stxm_live/service.py tests/test_service.py
git commit -m "feat: service event loop (bind/poll/spectrum/stop-reduce/discovery)"
```

---

### Task 8: e2e smoke — local nats-server + local Tiled + golden run

**Files:**
- Create: `tests/test_e2e_smoke.py`, `tests/fixtures/golden_energy_stack_run.json` (copy from `C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\tests\fixtures\golden_energy_stack_run.json`)

**Interfaces:**
- Consumes: everything. Real `nats-server` binary (from the `nats-server-bin` test dep — resolve next to `sys.executable`, else `shutil.which("nats-server")`; **skip the module if absent**), in-memory Tiled app served in-process, golden docs replayed through `bluesky_tiled_plugins.TiledWriter` to create a real BlueskyRun.
- Verifies spec §8: (a) service binds, (b) publishes `stxm.spectrum.updated` with correct I(E), (c) writes `stxm_analysis/`, (d) publishes `stxm.reduction.complete`.

- [ ] **Step 1: Copy the golden fixture**

```powershell
mkdir tests\fixtures
copy C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\tests\fixtures\golden_energy_stack_run.json tests\fixtures\
```

- [ ] **Step 2: Write the smoke test**

`tests/test_e2e_smoke.py`:

```python
"""Cross-repo e2e smoke: golden run -> Tiled; service over a real local nats-server."""
import asyncio
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import nats as natslib
import numpy as np
import pytest
from bluesky_tiled_plugins import TiledWriter
from tiled.catalog import in_memory
from tiled.client import Context, from_context
from tiled.server.app import build_app

from stxm_live.config import AppConfig
from stxm_live.service import StxmLiveService

GOLDEN = Path(__file__).parent / "fixtures" / "golden_energy_stack_run.json"


def _nats_binary():
    exe = Path(sys.executable).parent / (
        "nats-server.exe" if sys.platform == "win32" else "nats-server")
    if exe.exists():
        return str(exe)
    return shutil.which("nats-server")

pytestmark = pytest.mark.skipif(_nats_binary() is None, reason="nats-server not found")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def nats_server():
    port = _free_port()
    proc = subprocess.Popen([_nats_binary(), "-a", "127.0.0.1", "-p", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        proc.kill()
        pytest.fail("nats-server did not become ready")
    yield f"nats://127.0.0.1:{port}"
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture
def tiled_client(tmp_path):
    sql_uri = f"sqlite:///{(Path(tmp_path) / 'internal.db').as_posix()}"
    catalog = in_memory(writable_storage=[str(tmp_path), sql_uri])
    with Context.from_app(build_app(catalog)) as context:
        yield from_context(context)


def _replay_golden(tiled_client) -> tuple[str, np.ndarray]:
    docs = json.loads(GOLDEN.read_text())
    tw = TiledWriter(tiled_client, batch_size=1, max_array_size=0)
    for name, doc in docs:
        tw(name, doc)
    uid = docs[0][1]["uid"]
    rows = tiled_client[uid]["primary"]["STXMLineFlyer"].read()
    return uid, np.asarray(rows, dtype=float)


async def _smoke(nats_url, tiled_client):
    uid, rows = _replay_golden(tiled_client)
    expected = rows.reshape(2, 3, 4).mean(axis=(1, 2))

    cfg = AppConfig()
    cfg.nats.url = nats_url
    cfg.poll_interval_s = 0.05
    svc = StxmLiveService(cfg, tiled_connect=lambda url, key: tiled_client)
    await svc._nats.connect()
    await svc._register_subscriptions()

    nc = await natslib.connect(nats_url)
    events = {"spectrum": [], "complete": []}

    async def on_spectrum(msg):
        events["spectrum"].append(json.loads(msg.data))

    async def on_complete(msg):
        events["complete"].append(json.loads(msg.data))

    await nc.subscribe("stxm.spectrum.updated", cb=on_spectrum)
    await nc.subscribe("stxm.reduction.complete", cb=on_complete)
    await nc.flush()

    # (a) bind
    await nc.publish("stxm.run.bind", json.dumps({
        "run_uid": uid, "tiled_url": "http://in-memory", "tiled_api_key": None,
        "lightfall_prefix": "als.7011", "contract_version": 1}).encode())

    # (b) spectrum arrives with correct I(E)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        await asyncio.sleep(0.05)
        if events["spectrum"] and events["spectrum"][-1]["energies_done"] == 2:
            break
    assert events["spectrum"], "no stxm.spectrum.updated received"
    got = events["spectrum"][-1]
    assert got["energies"] == [500.0, 510.0]
    assert np.allclose(got["intensity"], expected)

    # (c)+(d) stop -> durable stream + reduction.complete
    await nc.publish("stxm.run.stop", json.dumps({"run_uid": uid}).encode())
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not events["complete"]:
        await asyncio.sleep(0.1)
    assert events["complete"], "no stxm.reduction.complete received"
    done = events["complete"][0]
    assert done["tiled_path"] == f"{uid}/stxm_analysis"
    stream = tiled_client[uid]["stxm_analysis"]
    assert np.allclose(stream["intensity"].read()[0], expected)
    if "od" in done["products"]:
        assert stream["od"].read().size == 24

    await nc.drain()
    await svc._nats.close()


def test_e2e_smoke(nats_server, tiled_client):
    asyncio.run(_smoke(nats_server, tiled_client))
```

Note for the implementer: the golden fixture emits `event_page` docs (bluesky 1.14.6 `collect` paginates). `TiledWriter` handles `event_page` natively; if the run replays but `primary/STXMLineFlyer` is a table column instead of an array node, the `max_array_size=0` kwarg is the fix (forces array storage) — assert `rows.shape == (6, 4)` right after `_replay_golden` to fail loudly. If `TiledWriter`'s constructor doesn't accept those kwargs in this version, use `TiledWriter(tiled_client)` and check what `_replay_golden` yields before touching the service.

- [ ] **Step 3: Run** — `.venv\Scripts\python -m pytest tests\test_e2e_smoke.py -v -s` — Expected: 1 PASS (or a loud, specific assertion failure to iterate on; budget iteration here — this test is the capstone).

- [ ] **Step 4: Full suite green** — `.venv\Scripts\python -m pytest tests -v`

- [ ] **Step 5: Commit**

```powershell
git add tests/test_e2e_smoke.py tests/fixtures/golden_energy_stack_run.json
git commit -m "test: e2e smoke over real nats-server + in-memory Tiled + golden run"
```

---

### Task 9: StxmAnalysisClient (in-Lightfall, worktree)

**From here on, work in the `lightfall-pystxmcontrol` worktree** (branch `feature/stxm-live-analysis` off `main`; the SDD workflow creates it). Test command: `QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_stxm_analysis_client.py -v`

**Files:**
- Create: `src/lightfall_pystxmcontrol/stxm_analysis_client.py`, `tests/conftest.py` (FakeIPC — repo has none yet), `tests/test_stxm_analysis_client.py`

**Interfaces:**
- Produces: `StxmAnalysisClient(QObject)` — signals `spectrumUpdated = Signal(dict)`, `statusChanged = Signal(dict)`, `errorReceived = Signal(dict)`, `reductionComplete = Signal(dict)`; ctor `(ipc=None, parent=None)` falling back to `get_ipc_service()`; subscribes `stxm.spectrum.updated`/`stxm.status`/`stxm.error`/`stxm.reduction.complete`; `bind_run(run_uid, tiled_url="", tiled_api_key=None, lightfall_prefix="", contract_version=1)` and `run_stop(run_uid)` publish (fire-and-forget, no-op if ipc None); `discover(timeout_ms=2000) -> dict | None` requests `_stxm.discover`.

- [ ] **Step 1: Write `tests/conftest.py`** (copy of the XPCS FakeIPC):

```python
import pytest


class FakeIPC:
    """Duck-type of lightfall.ipc.service.IPCService for unit tests."""

    def __init__(self):
        self.published = []
        self.requests = []
        self.replies = {}
        self.subscriptions = {}

    def publish(self, subject, data):
        self.published.append((subject, data))

    def request(self, subject, data, timeout_ms=1000):
        self.requests.append((subject, data))
        return self.replies.get(subject)

    def subscribe(self, subject, callback, *, main_thread=True):
        self.subscriptions[subject] = callback

    def emit(self, subject, data):
        self.subscriptions[subject](subject, data, None)


@pytest.fixture
def fake_ipc():
    return FakeIPC()
```

- [ ] **Step 2: Write the failing tests**

`tests/test_stxm_analysis_client.py`:

```python
from lightfall_pystxmcontrol.stxm_analysis_client import StxmAnalysisClient


def test_event_signals(fake_ipc, qtbot):
    c = StxmAnalysisClient(ipc=fake_ipc)
    got = {}
    c.spectrumUpdated.connect(lambda d: got.setdefault("spec", d))
    c.statusChanged.connect(lambda d: got.setdefault("status", d))
    c.errorReceived.connect(lambda d: got.setdefault("err", d))
    c.reductionComplete.connect(lambda d: got.setdefault("done", d))
    fake_ipc.emit("stxm.spectrum.updated", {"seq": 1})
    fake_ipc.emit("stxm.status", {"state": "reducing"})
    fake_ipc.emit("stxm.error", {"error": "x"})
    fake_ipc.emit("stxm.reduction.complete", {"products": ["od"]})
    assert got["spec"]["seq"] == 1
    assert got["status"]["state"] == "reducing"
    assert got["err"]["error"] == "x"
    assert got["done"]["products"] == ["od"]


def test_bind_run_publishes_full_payload(fake_ipc):
    c = StxmAnalysisClient(ipc=fake_ipc)
    c.bind_run("u1", tiled_url="http://t", tiled_api_key="k",
               lightfall_prefix="als.7011")
    assert fake_ipc.published == [("stxm.run.bind", {
        "run_uid": "u1", "tiled_url": "http://t", "tiled_api_key": "k",
        "lightfall_prefix": "als.7011", "contract_version": 1})]


def test_run_stop_publishes(fake_ipc):
    c = StxmAnalysisClient(ipc=fake_ipc)
    c.run_stop("u1")
    assert ("stxm.run.stop", {"run_uid": "u1"}) in fake_ipc.published


def test_no_ipc_is_safe():
    c = StxmAnalysisClient(ipc=None)
    c.bind_run("u")
    c.run_stop("u")
    assert c.discover() is None


def test_discover_requests(fake_ipc):
    fake_ipc.replies["_stxm.discover"] = {"app_name": "stxm-live"}
    c = StxmAnalysisClient(ipc=fake_ipc)
    assert c.discover()["app_name"] == "stxm-live"
```

- [ ] **Step 3: Run to verify FAIL** — command above.

- [ ] **Step 4: Implement `src/lightfall_pystxmcontrol/stxm_analysis_client.py`**

```python
"""Qt-side client for the external stxm-live analysis service (XPCS client shape)."""
from __future__ import annotations

from qtpy.QtCore import QObject, Signal

from lightfall_pystxmcontrol.contract import CONTRACT_VERSION


class StxmAnalysisClient(QObject):
    spectrumUpdated = Signal(dict)
    statusChanged = Signal(dict)
    errorReceived = Signal(dict)
    reductionComplete = Signal(dict)

    def __init__(self, ipc=None, parent=None) -> None:
        super().__init__(parent)
        if ipc is None:
            try:
                from lightfall.ipc.service import get_ipc_service
                ipc = get_ipc_service()
            except Exception:
                ipc = None
        self._ipc = ipc
        if self._ipc is not None:
            self._ipc.subscribe("stxm.spectrum.updated", self._on_spectrum)
            self._ipc.subscribe("stxm.status", self._on_status)
            self._ipc.subscribe("stxm.error", self._on_error)
            self._ipc.subscribe("stxm.reduction.complete", self._on_complete)

    # IPCService marshals callbacks to the Qt main thread (main_thread=True default)
    def _on_spectrum(self, subject, data, reply):
        self.spectrumUpdated.emit(data)

    def _on_status(self, subject, data, reply):
        self.statusChanged.emit(data)

    def _on_error(self, subject, data, reply):
        self.errorReceived.emit(data)

    def _on_complete(self, subject, data, reply):
        self.reductionComplete.emit(data)

    def discover(self, timeout_ms: int = 2000):
        if self._ipc is None:
            return None
        return self._ipc.request("_stxm.discover", {}, timeout_ms=timeout_ms)

    def bind_run(self, run_uid: str, tiled_url: str = "", tiled_api_key=None,
                 lightfall_prefix: str = "") -> None:
        if self._ipc is None:
            return
        self._ipc.publish("stxm.run.bind", {
            "run_uid": run_uid,
            "tiled_url": tiled_url,
            "tiled_api_key": tiled_api_key,
            "lightfall_prefix": lightfall_prefix,
            "contract_version": CONTRACT_VERSION,
        })

    def run_stop(self, run_uid: str) -> None:
        if self._ipc is None:
            return
        self._ipc.publish("stxm.run.stop", {"run_uid": run_uid})
```

- [ ] **Step 5: Run to verify PASS** (5 PASS), then run the repo's full suite to catch conftest fallout: `QT_QPA_PLATFORM=offscreen PYTHONPATH=src <lightfall venv> -m pytest tests -v`

- [ ] **Step 6: Commit**

```powershell
git add src/lightfall_pystxmcontrol/stxm_analysis_client.py tests/conftest.py tests/test_stxm_analysis_client.py
git commit -m "feat: StxmAnalysisClient over IPCService"
```

---

### Task 10: StxmRunBinder

**Files:**
- Create: `src/lightfall_pystxmcontrol/stxm_binder.py`, `tests/test_stxm_binder.py`

**Interfaces:**
- Consumes: `StxmAnalysisClient.bind_run/run_stop` (Task 9).
- Produces: `StxmRunBinder(client, run_engine_getter=..., credentials_getter=..., prefix_getter=...)` — `enable()` subscribes `get_engine().RE` (no backend ack gate — v1 has no `processing.enable` action; the next run's bind IS the start-analyzing signal); `disable()` unsubscribes; `enabled` property; `_on_document(name, doc)` publishes bind **only for stxm runs** (`"stxm" in doc`) on `start`, and `run_stop` on `stop` **only if a bind was published for that run**; entire callback wrapped in try/except.

- [ ] **Step 1: Write the failing tests**

`tests/test_stxm_binder.py`:

```python
from unittest.mock import MagicMock

from lightfall_pystxmcontrol.stxm_analysis_client import StxmAnalysisClient
from lightfall_pystxmcontrol.stxm_binder import StxmRunBinder


def _binder(fake_ipc):
    client = StxmAnalysisClient(ipc=fake_ipc)
    re = MagicMock()
    re.subscribe.return_value = 7
    b = StxmRunBinder(
        client,
        run_engine_getter=lambda: re,
        credentials_getter=lambda: ("http://t", "key", None),
        prefix_getter=lambda: "als.7011",
    )
    return b, re, fake_ipc


def _start_doc(uid="runX"):
    return {"uid": uid, "plan_name": "stxm_energy_stack", "stxm": {"contract_version": 1}}


def test_enable_subscribes_disable_unsubscribes(fake_ipc):
    b, re, _ = _binder(fake_ipc)
    b.enable()
    assert b.enabled
    b.enable()  # idempotent
    re.subscribe.assert_called_once()
    b.disable()
    re.unsubscribe.assert_called_once_with(7)
    assert not b.enabled


def test_stxm_start_publishes_bind(fake_ipc):
    b, re, ipc = _binder(fake_ipc)
    b.enable()
    cb = re.subscribe.call_args[0][0]
    cb("start", _start_doc())
    assert ipc.published == [("stxm.run.bind", {
        "run_uid": "runX", "tiled_url": "http://t", "tiled_api_key": "key",
        "lightfall_prefix": "als.7011", "contract_version": 1})]
    cb("stop", {"run_start": "runX"})
    assert ("stxm.run.stop", {"run_uid": "runX"}) in ipc.published


def test_non_stxm_run_ignored(fake_ipc):
    b, re, ipc = _binder(fake_ipc)
    b.enable()
    cb = re.subscribe.call_args[0][0]
    cb("start", {"uid": "plain", "plan_name": "count"})
    cb("stop", {"run_start": "plain"})
    assert ipc.published == []


def test_callback_exceptions_swallowed(fake_ipc):
    b, re, _ = _binder(fake_ipc)
    b._get_creds = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    b.enable()
    cb = re.subscribe.call_args[0][0]
    cb("start", _start_doc())  # must not raise
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement `src/lightfall_pystxmcontrol/stxm_binder.py`**

```python
"""Publishes stxm.run.bind/stop on RunEngine start/stop (XPCS binding.py shape)."""
from __future__ import annotations

from typing import Callable

from loguru import logger


def _default_run_engine():
    from lightfall.acquire.engine import get_engine
    return get_engine().RE


def _default_credentials():
    tiled_url, api_key = "", None
    try:
        from lightfall.core.services import ServiceRegistry
        from lightfall.services.tiled_service import TiledService
        ts = ServiceRegistry.get_instance().get(TiledService, None)
        if ts and ts.config:
            tiled_url = ts.config.url or ""
    except Exception:
        pass
    try:
        from lightfall.auth.session import SessionManager
        api_key = SessionManager.get_instance().get_api_key("tiled")
    except Exception:
        pass
    return tiled_url, api_key, None


def _default_prefix():
    try:
        from lightfall.core.preferences import PreferencesManager
        return PreferencesManager.get_instance().get("ipc_topic_prefix", "als.7011")
    except Exception:
        return "als.7011"


class StxmRunBinder:
    def __init__(
        self,
        client,
        run_engine_getter: Callable = _default_run_engine,
        credentials_getter: Callable = _default_credentials,
        prefix_getter: Callable = _default_prefix,
    ) -> None:
        self._client = client
        self._get_re = run_engine_getter
        self._get_creds = credentials_getter
        self._get_prefix = prefix_getter
        self._token = None
        self._re = None
        self._bound_uid: str | None = None

    @property
    def enabled(self) -> bool:
        return self._token is not None

    def enable(self) -> None:
        if self.enabled:
            return
        self._re = self._get_re()
        self._token = self._re.subscribe(self._on_document)

    def disable(self) -> None:
        if not self.enabled:
            return
        try:
            self._re.unsubscribe(self._token)
        finally:
            self._token = None
            self._re = None

    def _on_document(self, name: str, doc: dict) -> None:
        try:
            if name == "start":
                if "stxm" not in doc:
                    return  # not an stxm run; stay quiet on the bus
                uid = doc["uid"]
                tiled_url, api_key, _ = self._get_creds()
                self._client.bind_run(
                    uid, tiled_url=tiled_url, tiled_api_key=api_key,
                    lightfall_prefix=self._get_prefix())
                self._bound_uid = uid
            elif name == "stop":
                uid = doc.get("run_start") or self._bound_uid
                if uid and uid == self._bound_uid:
                    self._client.run_stop(uid)
                self._bound_uid = None
        except Exception as ex:  # never break the RunEngine document stream
            logger.exception(ex)
```

Note: check the import of `PreferencesManager` — Grep lightfall for `class PreferencesManager` and use its actual module path; the try/except default keeps a wrong path non-fatal but get it right.

- [ ] **Step 4: Run to verify PASS** (4 PASS).

- [ ] **Step 5: Commit**

```powershell
git add src/lightfall_pystxmcontrol/stxm_binder.py tests/test_stxm_binder.py
git commit -m "feat: StxmRunBinder publishes bind/stop on RE start/stop"
```

---

### Task 11: StxmSpectrumPanel + plugin + manifest entry

**Files:**
- Create: `src/lightfall_pystxmcontrol/stxm_spectrum_panel.py`, `tests/test_stxm_spectrum_panel.py`
- Modify: `src/lightfall_pystxmcontrol/manifest.py` (add one entry)

**Interfaces:**
- Consumes: `StxmAnalysisClient` (Task 9), `StxmRunBinder` (Task 10).
- Produces: `StxmSpectrumPanel(BasePanel)` (metadata id `lightfall_pystxmcontrol.panels.stxm_spectrum`, name "STXM Spectrum", category "Analysis", `default_area="bottom"`); ctor `(parent=None, client=None, binder=None)`; checkable title-bar Enable-analysis toggle → `binder.enable()/disable()` with rollback on exception; pyqtgraph I(E) plot fed by `spectrumUpdated` (None intensities → NaN, plotted with `connect="finite"`); status label from `statusChanged`/`errorReceived`; `_on_closing` disables the binder. `StxmSpectrumPanelPlugin(PanelPlugin)` name `stxm_spectrum`.

- [ ] **Step 1: Write the failing tests**

`tests/test_stxm_spectrum_panel.py`:

```python
from unittest.mock import MagicMock

import numpy as np
import pytest

from lightfall_pystxmcontrol.manifest import manifest
from lightfall_pystxmcontrol.stxm_analysis_client import StxmAnalysisClient
from lightfall_pystxmcontrol.stxm_spectrum_panel import (
    StxmSpectrumPanel, StxmSpectrumPanelPlugin)


@pytest.fixture
def panel(qtbot, fake_ipc):
    client = StxmAnalysisClient(ipc=fake_ipc)
    binder = MagicMock()
    binder.enabled = False
    p = StxmSpectrumPanel(client=client, binder=binder)
    qtbot.addWidget(p)
    p.test_ipc = fake_ipc
    p.test_binder = binder
    return p


def test_metadata(panel):
    md = panel.panel_metadata
    assert md.id == "lightfall_pystxmcontrol.panels.stxm_spectrum"
    assert md.default_area != "center"


def test_spectrum_event_updates_curve(panel):
    panel.test_ipc.emit("stxm.spectrum.updated", {
        "run_uid": "u", "energies": [500.0, 510.0],
        "intensity": [2.0, None], "energies_done": 1, "seq": 1})
    x, y = panel._curve.getData()
    assert list(x) == [500.0, 510.0]
    assert y[0] == 2.0 and np.isnan(y[1])


def test_toggle_drives_binder(panel):
    panel._enable_toggle.setChecked(True)
    panel.test_binder.enable.assert_called_once()
    panel._enable_toggle.setChecked(False)
    panel.test_binder.disable.assert_called_once()


def test_toggle_rollback_on_error(panel):
    panel.test_binder.enable.side_effect = RuntimeError("no ipc")
    panel._enable_toggle.setChecked(True)
    assert panel._enable_toggle.isChecked() is False


def test_status_and_error_labels(panel):
    panel.test_ipc.emit("stxm.status", {
        "run_uid": "u", "state": "reducing", "energies_done": 1, "total": 2})
    assert "reducing" in panel._status_label.text()
    panel.test_ipc.emit("stxm.error", {"run_uid": "u", "error": "boom"})
    assert "boom" in panel._status_label.text()


def test_close_disables_binder(panel):
    panel._on_closing()
    panel.test_binder.disable.assert_called()


def test_plugin_and_manifest():
    plugin = StxmSpectrumPanelPlugin()
    assert plugin.name == "stxm_spectrum"
    cls = plugin.get_panel_class()
    assert cls.panel_metadata.id == "lightfall_pystxmcontrol.panels.stxm_spectrum"
    entries = [p for p in manifest.plugins
               if p.type_name == "panel" and p.name == "stxm_spectrum"]
    assert len(entries) == 1
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement `src/lightfall_pystxmcontrol/stxm_spectrum_panel.py`**

```python
"""Live I(E) spectrum panel fed by the external stxm-live service (XPCS panel shape)."""
from __future__ import annotations

from typing import ClassVar

import numpy as np
import pyqtgraph as pg
from loguru import logger
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget

from lightfall.plugins.panel_plugin import PanelPlugin
from lightfall.ui.panels.base import BasePanel, PanelMetadata

from lightfall_pystxmcontrol.stxm_analysis_client import StxmAnalysisClient
from lightfall_pystxmcontrol.stxm_binder import StxmRunBinder


class StxmSpectrumPanel(BasePanel):
    panel_metadata: ClassVar[PanelMetadata] = PanelMetadata(
        id="lightfall_pystxmcontrol.panels.stxm_spectrum",
        name="STXM Spectrum",
        description="Live I(E) spectrum from the external stxm-live analysis service",
        icon="mdi6.chart-bell-curve",
        category="Analysis",
        singleton=True,
        closable=True,
        keywords=["stxm", "spectrum", "analysis", "live"],
        default_area="bottom",
        sidebar_group="top",
    )

    def __init__(self, parent: QWidget | None = None,
                 client: StxmAnalysisClient | None = None,
                 binder: StxmRunBinder | None = None) -> None:
        # attrs before super().__init__: BasePanel.__init__ calls _setup_ui()
        self._client = client or StxmAnalysisClient()
        self._binder = binder or StxmRunBinder(client=self._client)
        super().__init__(parent)
        self._client.spectrumUpdated.connect(self._on_spectrum)
        self._client.statusChanged.connect(self._on_status)
        self._client.errorReceived.connect(self._on_error)
        self._client.reductionComplete.connect(self._on_complete)

    def _setup_ui(self) -> None:
        super()._setup_ui()
        self._enable_toggle = self.add_title_bar_button(
            "mdi6.play-pause", "Enable analysis", checkable=True)
        self._enable_toggle.toggled.connect(self._on_enable_toggled)
        content = QWidget(self)
        layout = QVBoxLayout(content)
        self._plot = pg.PlotWidget()
        self._plot.setLabel("bottom", "Energy", units="eV")
        self._plot.setLabel("left", "I(E)")
        self._curve = self._plot.plot([], [], pen=pg.mkPen(width=2),
                                      symbol="o", symbolSize=5)
        self._status_label = QLabel("idle")
        layout.addWidget(self._plot)
        layout.addWidget(self._status_label)
        self._layout.addWidget(content)

    def _on_enable_toggled(self, checked: bool) -> None:
        try:
            if checked:
                self._binder.enable()
            else:
                self._binder.disable()
        except Exception as ex:
            logger.exception(ex)
            self._status_label.setText(str(ex))
            self._enable_toggle.setChecked(self._binder.enabled)

    def _on_spectrum(self, data: dict) -> None:
        energies = np.asarray(data.get("energies", []), dtype=float)
        intensity = np.asarray(
            [np.nan if v is None else v for v in data.get("intensity", [])],
            dtype=float)
        if energies.size and energies.size == intensity.size:
            self._curve.setData(energies, intensity, connect="finite")

    def _on_status(self, data: dict) -> None:
        self._status_label.setText(
            f"{data.get('state', '?')} — {data.get('energies_done', 0)}/{data.get('total', 0)}")

    def _on_error(self, data: dict) -> None:
        self._status_label.setText(f"error: {data.get('error', '')}")

    def _on_complete(self, data: dict) -> None:
        self._status_label.setText(
            f"reduction complete: {', '.join(data.get('products', []))}")

    def _on_closing(self) -> None:
        try:
            self._binder.disable()
        except Exception as ex:
            logger.exception(ex)
        super()._on_closing()


class StxmSpectrumPanelPlugin(PanelPlugin):
    @property
    def name(self) -> str:
        return "stxm_spectrum"

    @property
    def description(self) -> str:
        return "Live I(E) spectrum panel for the stxm-live analysis service"

    def get_panel_class(self):
        from lightfall_pystxmcontrol.stxm_spectrum_panel import StxmSpectrumPanel
        return StxmSpectrumPanel
```

Note: check `BasePanel`'s actual content-layout attribute (`self._layout` per the XPCS panel) and `add_title_bar_button` signature against `lightfall/ui/panels/base.py` before finalizing; mirror `scan_panel.py` in this repo if it differs.

- [ ] **Step 4: Add the manifest entry** — in `src/lightfall_pystxmcontrol/manifest.py`, append after the `stxm_scan` panel entry:

```python
        PluginEntry("panel", "stxm_spectrum",
                    "lightfall_pystxmcontrol.stxm_spectrum_panel:StxmSpectrumPanelPlugin",
                    preload=True),
```

- [ ] **Step 5: Run to verify PASS** (7 PASS), then the full repo suite: `QT_QPA_PLATFORM=offscreen PYTHONPATH=src <lightfall venv> -m pytest tests -v`

- [ ] **Step 6: Commit**

```powershell
git add src/lightfall_pystxmcontrol/stxm_spectrum_panel.py src/lightfall_pystxmcontrol/manifest.py tests/test_stxm_spectrum_panel.py
git commit -m "feat: StxmSpectrumPanel + PanelPlugin manifest entry"
```

---

### Task 12: Documentation + final verification

**Files:**
- Modify: `README.md` in BOTH repos.
- Verify: both suites green; spec §8 assertions covered.

- [ ] **Step 1: lightfall-pystxmcontrol README** — add a "Live analysis (stxm-live)" section: one paragraph on the split (binder/client/panel here, service in `als-controls/stxm-live`), the NATS contract table from spec §3.1 verbatim, the unprefixed-subject rule, and a pointer to the spec file.

- [ ] **Step 2: stxm-live README** — confirm it has: install (venv + `-e ".[stack,test]"` + pystxmcontrol `--no-deps`), `stxm-live run` usage with the local-broker dev flow (`--nats-url nats://127.0.0.1:4222`), the contract table, and the "seed of the real STXM analysis service" framing with the deferred list (spec §9).

- [ ] **Step 3: Full verification, both repos**

```powershell
# stxm-live
C:\Users\rp\PycharmProjects\ncs\stxm-live\.venv\Scripts\python -m pytest tests -v
# plugin worktree
$env:QT_QPA_PLATFORM="offscreen"; $env:PYTHONPATH="src"
C:\Users\rp\PycharmProjects\ncs\lightfall\.venv\Scripts\python -m pytest tests -v
```

Expected: all green (e2e smoke may skip only if nats-server binary is genuinely absent — it should NOT skip, since `nats-server-bin` is a test dep).

- [ ] **Step 4: Commit READMEs (each in its own repo, explicit paths).**

---

## Self-Review Notes

- Spec coverage: §2 layers → Tasks 1–8 (service) + 9–11 (in-Lightfall); §3 contract subjects all implemented (bind/stop Task 7+10, spectrum/status/error/complete Task 7, discovery Task 7, auth Task 4); §3.3 durable record Task 5; §3.4 read-side Task 1; §4 internals Tasks 2–7; §5 Tasks 9–11; §6 flow exercised by Task 8 e2e; §7 degrade paths in Tasks 4/6/7/11; §8 test matrix Tasks 1–11 unit + Task 8 e2e; §10 bootstrap in Task 1 (local scaffold, Ron creates remote).
- Known deviation from spec §3 (documented in Global Constraints): subjects are unprefixed on the bus, matching IPCService verbatim-subject semantics and the working XPCS convention; `lightfall_prefix` used only for auth.request and still carried in the bind payload.
- v1 StackReducer product is OD only (spec says "whatever stack.py yields" — NMF/PCA are David's extensions; `finalize` returns a dict so adding them is additive).
