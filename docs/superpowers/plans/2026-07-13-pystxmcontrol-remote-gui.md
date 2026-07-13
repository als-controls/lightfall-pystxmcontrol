# pystxmcontrol Remote GUI (spec #4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make David Shapiro's pystxmcontrol GUI a thin remote client of Lightfall — control over the spec-#1 NATS contract, motor readbacks over direct CA, live data over Tiled — with the ZMQ scan server dropped from the app path.

**Architecture:** New leaf package `pystxmcontrol/remote/` in the als-controls fork: `LightfallClient` (asyncio, raw nats-py + tiled.client, no lightfall imports), `RemoteBackend` (QThread hosting the loop, Qt signals matching what `MainController` consumes), `MotorMonitorSet` (caproto CA monitors → `motorPositions` dicts), `RunStreamer` (Tiled run → live image payloads), `scan_mapping` (scan-model dict → plan params). `MainController` is re-pointed at `RemoteBackend`; widgets unchanged. One small additive change lands in lightfall core first (`device.info` gains `pv`).

**Tech Stack:** PySide6 (David's GUI already uses it), nats-py, tiled.client, caproto threading client (+netifaces), pytest with `QT_QPA_PLATFORM=offscreen`; sim IOC fleet from spec #2 for live tests.

## Global Constraints

- **Repos:** (a) fork `_pystxmcontrol_src` at `C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\_pystxmcontrol_src` — work in worktree `..\_pystxmcontrol_remote_wt`, branch `feature/remote-gui` off `headless-install-fixes`; NEVER push `origin` (David); branch stays LOCAL. (b) lightfall at `C:\Users\rp\PycharmProjects\ncs\lightfall` — Task 1 only, on a branch `feature/device-info-pv` off master, LOCAL, no push. Do NOT modify David's `controller/server.py`, `controller/client.py`, or the spec-#2 `pystxmcontrol/iocs/` code.
- **Interpreter:** ALWAYS `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python` (`$PY`). Fork tests run from the fork worktree root with `PYTHONPATH` = fork worktree (editable install points at `_pystxmcontrol_src` main checkout).
- **`pystxmcontrol/remote/` must not import `lightfall`** (client independence is the point). Test-only lightfall imports are allowed in `tests/remote/` (to host the headless service).
- **Transports:** NATS for actions (capability channel per spec #1), caproto threading client for readback monitors (netifaces required), tiled.client for data. `device.put` (not CA) for manual moves — Lightfall arbitration must apply.
- **v1 scan modes:** fly raster + energy stack only, mapped to plan names `stxm_fly_raster` / `stxm_energy_stack` with the `lightfall-pystxmcontrol` plan param names (`y_start,y_stop,ny,x_start,x_stop,nx,dwell` / `energies,...,dwell_ms`; dwell in ms end-to-end). Unsupported modes raise `UnsupportedScanMode`.
- **Contract constants:** `CONTRACT_VERSION = 1`; structured errors `{status:"error", code, message}` with codes `busy|limits|timeout|unknown|denied|bad_request|version_mismatch`; capability subject `{prefix}.session.{token}.{suffix}`; broadcast events on `{prefix}.{suffix}`.
- **Qt tests:** `QT_QPA_PLATFORM=offscreen` in the test env. Live-fleet tests reuse the spec-#3 fixture pattern: spawn IOCs from `PYSTXMCONTROL_IOCS_SRC` (default `C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\_pystxmcontrol_iocs_wt`), per-IOC ports (`EPICS_CAS_SERVER_PORT` + `EPICS_CA_SERVER_PORT` per child), accumulated `EPICS_CA_ADDR_LIST`, fail loudly if missing.
- **Commits:** explicit `git add <paths>`; every commit in BOTH repos ends with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01PFykQo3UJmNXTg3kxLHKxv`
- **Deferred (spec §6):** analysis/browser/stack-viewer Tiled conversion; spiral/ptycho/point modes; CCD/frame streams; device streaming; leases; motor-config editing; panel slim-down.

## Reference facts (verified 2026-07-13)

- Reference client `C:\Users\rp\PycharmProjects\ncs\lightfall\tests\integration\remote_client.py`: `LightfallRemoteClient(nats_url, prefix, app_name, app_version="0.0")` with `connect() / authenticate(timeout=90) / call(suffix, payload, timeout=5) / call_bare / subscribe_event(suffix, cb) / close()`, `RemoteError(code, message)`, `CONTRACT_VERSION=1`. Copy it as the seed — semantics must stay identical.
- Spec-#1 verbs registered in `lightfall/remote/service.py`: `commands.engine.status/queue.get/plan.list/plan.run/plan.abort/device.search/device.components/device.info/device.get/device.put`; events `runs.new` (`{item_id, run_uid, plan_name}`), `runs.complete` (`{run_uid, exit_status}`), `state.engine` (`{state}`). `_device_info` reply today: `ok_reply(name=info.name, category=str(info.category), device_class=info.device_class)` at `service.py:496`.
- `MainController` seams (fork `pystxmcontrol/gui/controllers/main_controller.py`): `initialize_client()` (~:183) builds `ControlThread(self.client, self.message_queue)`, calls `client.get_config()`, reads `client.motorInfo / currentMotorPositions / daqConfig / main_config`, connects `client.monitor.scan_data → _handle_monitor_message`; `start_scan()` (~:871) puts `{"command":"scan","scan":scan_model.to_dict()}` on the queue; `cancel_scan()` puts `{"command":"cancel"}`; `move_motor()` puts `{"command":"moveMotor","axis","pos"}`; `set_gate`, `move_to_focus`, `change_motor_config` (~:1133), `query_motor_history` are server features DROPPED in v1 (UI paths disabled).
- `_handle_monitor_message` consumes: literal `"scan_complete"`; dicts with `motorPositions` (`{name: float, ..., "status": {name: bool}}`); `{"type":"monitor", "rawData": {daq: {"data": [...]}}}` idle traces; scan-image dicts with `mode` + `image` per-DAQ dict (exact scan-image shape to be pinned in Task 7 from the handler source ~:340-480).
- GUI is PySide6 throughout; venv has PySide6, nats-py?, tiled, caproto, netifaces — **verify `nats` importability in Task 2 Step 1** (lightfall depends on it, expected present).
- Spec-#3 fleet fixture pattern to copy: `lightfall-pystxmcontrol/tests/conftest.py` (iocs_src / _free_udp_port with issued-port set / stxm_fleet with env save-restore). Plugin sim JSONs: `lightfall-pystxmcontrol/src/lightfall_pystxmcontrol/sim_motor.json` + `sim_daq.json` (PVs `STXMSIM:E712:SampleX/SampleY`, `STXMSIM:XPS:energy`, `STXMSIM:DEFAULT`, `STXMSIM:E712:FLY`).
- Lightfall e2e harness for a headless RemoteControlService: `lightfall/tests/integration/test_remote_control_e2e.py` (local nats-server + service wiring — READ it in Task 8 before building the fork's contract test).

## File structure (final, fork unless noted)

```
lightfall repo: src/lightfall/remote/service.py (+pv), docs/developer-guide/ipc-client-guide.md, tests/integration/test_remote_control_e2e.py (assert pv)
pystxmcontrol/remote/__init__.py       # guarded imports (nats/tiled/caproto optional extra)
pystxmcontrol/remote/client.py         # LightfallClient (asyncio; seeded from reference client + tiled bootstrap)
pystxmcontrol/remote/scan_mapping.py   # scan-model dict -> (plan_name, params); UnsupportedScanMode
pystxmcontrol/remote/ca_monitors.py    # MotorMonitorSet
pystxmcontrol/remote/tiled_stream.py   # RunStreamer
pystxmcontrol/remote/qt_bridge.py      # RemoteBackend(QThread)
pystxmcontrol/remote/app.py            # stxmcontrol-remote entry point + remote.json loading
pystxmcontrol/gui/controllers/main_controller.py  # re-pointed at RemoteBackend (bounded edits)
tests/remote/{__init__,conftest,test_client,test_scan_mapping,test_ca_monitors,test_qt_bridge,test_tiled_stream,test_contract,test_e2e_gui}.py
pyproject.toml                         # console script stxmcontrol-remote + extra remote=[...]
```

---

### Task 1: lightfall — `device.info` gains `pv` (separate repo)

**Files:**
- Modify: `C:\Users\rp\PycharmProjects\ncs\lightfall\src\lightfall\remote\service.py:496` (the `_device_info` reply)
- Modify: `C:\Users\rp\PycharmProjects\ncs\lightfall\tests\integration\test_remote_control_e2e.py` (extend the existing device.info assertion)
- Modify: `C:\Users\rp\PycharmProjects\ncs\lightfall\docs\developer-guide\ipc-client-guide.md` (device.info reply table row)

**Interfaces:**
- Produces: `commands.device.info` reply gains `"pv": <str>` — the device's EPICS/record prefix from `DeviceInfo.prefix` (empty string when the catalog entry has none). Additive; `contract_version` stays 1.

- [ ] **Step 1: Branch**

```bash
cd /c/Users/rp/PycharmProjects/ncs/lightfall
git status --porcelain   # must be clean before branching; if dirty, STOP and report
git checkout -b feature/device-info-pv master
```
(If lightfall's default branch is `main` not `master`, use it — check `git branch --show-current` conventions first.)

- [ ] **Step 2: Find and extend the e2e assertion (failing first)**

Locate the `device.info` block in `tests/integration/test_remote_control_e2e.py` (grep `device.info`). Extend it:

```python
        info = await self.client.call("commands.device.info", {"device": device_name})
        assert info["pv"] == expected_prefix   # NEW: adapt expected_prefix to what the
        # harness's sim DeviceInfo actually registers (read the harness fixture; use
        # the same source it uses for name/category — do not invent a value)
```

- [ ] **Step 3: Run that e2e test to verify the new assertion fails** (use lightfall's own documented test invocation — check the repo's CLAUDE.md/pyproject for the exact runner; it is the same venv).

- [ ] **Step 4: Implement** — in `_device_info`, extend the reply:

```python
            ok_reply(name=info.name, category=str(info.category),
                     device_class=info.device_class,
                     pv=getattr(info, "prefix", "") or ""),
```
(Match the surrounding code style; `info` here is the catalog `DeviceInfo`.)

- [ ] **Step 5: Update `ipc-client-guide.md`** — add `pv` to the `device.info` reply description with one sentence: "record/PV prefix of the device (empty when not EPICS-backed); use for client-side CA monitors."

- [ ] **Step 6: Run the e2e device tests to green; run lightfall's remote-service unit tests too** (grep `tests` for files touching `remote/service`).

- [ ] **Step 7: Commit (lightfall repo, trailers), stay on the branch** — merging/pushing is Ron's; record the branch name in the task report. NOTE for later tasks: the fork's contract/e2e tests must run against THIS branch's lightfall — since the venv imports lightfall editable from this checkout, having the branch checked out locally is sufficient; flag loudly in the report that lightfall is left on `feature/device-info-pv`.

```bash
git add src/lightfall/remote/service.py tests/integration/test_remote_control_e2e.py docs/developer-guide/ipc-client-guide.md
git commit -m "feat(remote): device.info reply gains pv (record prefix) for client-side CA monitors"
```

---

### Task 2: Fork worktree, `remote` package scaffold, `LightfallClient`

**Files:**
- Create: worktree `C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\_pystxmcontrol_remote_wt` (branch `feature/remote-gui` off `headless-install-fixes`)
- Create: `pystxmcontrol/remote/__init__.py`, `pystxmcontrol/remote/client.py`
- Modify: `pyproject.toml` (console script + `remote` extra)
- Create: `tests/remote/__init__.py`, `tests/remote/conftest.py` (stub-NATS helper only, fleet fixture comes in Task 4), `tests/remote/test_client.py`

**Interfaces:**
- Produces:
  - `remote/__init__.py::require_remote_deps() -> None` — imports nats, tiled, caproto, netifaces; actionable ImportError naming `pip install pystxmcontrol[remote]`.
  - `client.LightfallClient(nats_url, prefix, app_name, app_version="0.0")` — the reference client's exact API (`connect/authenticate/call/call_bare/subscribe_event/close`, `RemoteError`, `CONTRACT_VERSION`) PLUS `tiled_client()` (lazy `tiled.client.from_uri(self.tiled_url, api_key=self.tiled_token)` after auth; raises RuntimeError before auth) and `async ping() -> bool` (`meta.actions` round-trip on the bare subject — pre-trust liveness).
  - Test helper `conftest.StubNats` — in-process fake with `request(subject, data, timeout)` routed to registered handlers and `subscribe(subject, cb)`; injected via `LightfallClient._connect_impl` seam (constructor kwarg `_nats_connect=nats.connect` overrideable).

- [ ] **Step 1: Worktree + gitignore + dep check**

```bash
cd /c/Users/rp/PycharmProjects/ncs/lightfall-pystxmcontrol/_pystxmcontrol_src
git worktree add ../_pystxmcontrol_remote_wt -b feature/remote-gui headless-install-fixes
grep -q '_pystxmcontrol_remote_wt/' ../.gitignore || echo "_pystxmcontrol_remote_wt/" >> ../.gitignore
C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -c "import nats, tiled.client, caproto, netifaces; print('deps OK')"
```
If `nats` is missing, `pip install nats-py` into the venv and record it. Commit the plugin-repo `.gitignore` line separately in `lightfall-pystxmcontrol` (one-line chore commit).

- [ ] **Step 2: Write failing tests**

`tests/remote/conftest.py`:

```python
"""Stub NATS for unit-testing LightfallClient without a broker."""
import json


class _StubMsg:
    def __init__(self, data: bytes):
        self.data = data


class StubNats:
    """Duck-types the nats-py client surface LightfallClient uses."""

    def __init__(self):
        self.handlers = {}       # exact subject -> callable(payload dict) -> dict
        self.subscriptions = {}  # subject -> cb
        self.requests = []       # (subject, payload) log

    async def request(self, subject, data, timeout=None):
        payload = json.loads(data.decode())
        self.requests.append((subject, payload))
        for pat, handler in self.handlers.items():
            if subject == pat or (pat.endswith(".*") and subject.startswith(pat[:-1])):
                return _StubMsg(json.dumps(handler(subject, payload)).encode())
        raise TimeoutError(f"no stub handler for {subject}")

    async def subscribe(self, subject, cb=None):
        self.subscriptions[subject] = cb

    async def drain(self):
        pass


async def stub_connect_factory(stub):
    async def _connect(url):
        return stub
    return _connect
```

`tests/remote/test_client.py`:

```python
import json

import pytest

from pystxmcontrol.remote.client import CONTRACT_VERSION, LightfallClient, RemoteError
from .conftest import StubNats


@pytest.fixture
def stub():
    return StubNats()


@pytest.fixture
async def client(stub):
    async def _connect(url):
        return stub
    c = LightfallClient("nats://x", "als.test", "stxm-gui", _nats_connect=_connect)
    await c.connect()
    return c


async def test_authenticate_stores_token_and_tiled(client, stub):
    stub.handlers["als.test.auth.request"] = lambda s, p: {
        "status": "approved", "session_token": "tok123",
        "tiled_url": "http://t", "tiled_token": "tt"}
    reply = await client.authenticate()
    assert reply["status"] == "approved"
    assert client.session_token == "tok123"
    assert client.tiled_url == "http://t"


async def test_call_travels_on_capability_channel(client, stub):
    stub.handlers["als.test.auth.request"] = lambda s, p: {
        "status": "approved", "session_token": "tok123"}
    await client.authenticate()
    stub.handlers["als.test.session.tok123.commands.engine.status"] = (
        lambda s, p: {"status": "ok", "state": "idle", "contract_version": 1})
    reply = await client.call("commands.engine.status")
    assert reply["state"] == "idle"
    subject, payload = stub.requests[-1]
    assert subject == "als.test.session.tok123.commands.engine.status"
    assert payload["contract_version"] == CONTRACT_VERSION


async def test_structured_error_raises(client, stub):
    stub.handlers["als.test.auth.request"] = lambda s, p: {
        "status": "approved", "session_token": "tok123"}
    await client.authenticate()
    stub.handlers["als.test.session.tok123.commands.plan.run"] = (
        lambda s, p: {"status": "error", "code": "busy", "message": "engine busy"})
    with pytest.raises(RemoteError) as ei:
        await client.call("commands.plan.run", {"plan_name": "x"})
    assert ei.value.code == "busy"


async def test_call_before_auth_raises(client):
    with pytest.raises(RuntimeError):
        await client.call("commands.engine.status")


async def test_tiled_client_requires_auth(client):
    with pytest.raises(RuntimeError):
        client.tiled_client()
```

(`asyncio_mode` — check the fork's pyproject `[tool.pytest.ini_options]`; if absent, add `asyncio_mode = "auto"` and add `pytest-asyncio` presence check; if pytest-asyncio is not installed, install it into the venv and record it.)

- [ ] **Step 3: Verify failure** — `PYTHONPATH="$PWD" $PY -m pytest tests/remote/test_client.py -v` from the fork worktree root → import error.

- [ ] **Step 4: Implement**

`pystxmcontrol/remote/__init__.py`:

```python
"""Thin Lightfall remote client for the pystxmcontrol GUI (spec #4).

Leaf package: NOTHING here imports lightfall, and nothing in the base
pystxmcontrol package imports this. Install extras: pip install pystxmcontrol[remote]
"""


def require_remote_deps() -> None:
    missing = []
    for mod in ("nats", "tiled", "caproto", "netifaces"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise ImportError(
            f"pystxmcontrol.remote requires {missing}; "
            "install with: pip install pystxmcontrol[remote]")
```

`pystxmcontrol/remote/client.py`: copy `lightfall/tests/integration/remote_client.py` VERBATIM (docstring adjusted: this is now the production client; keep `CONTRACT_VERSION`, `RemoteError`, all method semantics), rename class `LightfallRemoteClient` → `LightfallClient`, then add:

```python
    def __init__(self, nats_url, prefix, app_name, app_version="0.0", *,
                 _nats_connect=None):
        ...existing fields...
        self._nats_connect = _nats_connect  # test seam; None -> nats.connect

    async def connect(self) -> None:
        connect = self._nats_connect or nats.connect
        self._nc = await connect(self._nats_url)

    async def ping(self, timeout: float = 3.0) -> bool:
        """Pre-trust liveness: meta.actions on the bare subject."""
        try:
            await self.call_bare("meta.actions", {}, timeout=timeout)
            return True
        except Exception:
            return False

    def tiled_client(self):
        """Lazy tiled.client rooted at the handshake's URL/token."""
        if not self.tiled_url:
            raise RuntimeError("Not authenticated - no tiled_url yet")
        if self._tiled is None:
            from tiled.client import from_uri
            self._tiled = from_uri(self.tiled_url, api_key=self.tiled_token)
        return self._tiled
```
(`self._tiled = None` in `__init__`. Verify `from_uri(..., api_key=...)` is the right kwarg against the installed tiled — the plugin/lightfall code already does this; copy their call form.)

`pyproject.toml`: add to `[project.scripts]` → `stxmcontrol-remote = "pystxmcontrol.remote.app:main"` (app.py arrives in Task 7 — the script entry is declared now with the package); add to `[project.optional-dependencies]` → `remote = ["nats-py", "tiled", "caproto>=1.1", "netifaces"]`.

- [ ] **Step 5: Green + commit**

```bash
PYTHONPATH="$PWD" $PY -m pytest tests/remote/test_client.py -v   # all PASS
git add pystxmcontrol/remote/__init__.py pystxmcontrol/remote/client.py pyproject.toml tests/remote/__init__.py tests/remote/conftest.py tests/remote/test_client.py
git commit -m "feat(remote): LightfallClient - productionized spec-#1 reference client + tiled bootstrap"
```

---

### Task 3: `scan_mapping` — scan-model dict → plan params

**Files:**
- Create: `pystxmcontrol/remote/scan_mapping.py`
- Test: `tests/remote/test_scan_mapping.py`

**Interfaces:**
- Produces: `map_scan(scan: dict) -> tuple[str, dict]` returning `("stxm_fly_raster", {y_start,y_stop,ny,x_start,x_stop,nx,dwell})` or `("stxm_energy_stack", {energies, y_start,y_stop,ny,x_start,x_stop,nx,dwell_ms})`; `class UnsupportedScanMode(ValueError)` carrying the offending `scan_type`.

- [ ] **Step 1: PIN THE INPUT SHAPE (investigative, load-bearing).** Read `pystxmcontrol/gui/models/scan_model.py` in the fork — `to_dict()`, the scan/energy region structures (`energy_regions`, scan region keys: centers/ranges vs start/stop, point counts, dwell fields and their UNITS), and how `scanDef.py`/`energyDef.py` populate them. Record in your report: the exact keys for (a) a single-region Image scan, (b) a multi-energy Image scan. Write the Step-2 tests with REAL dicts copied from that shape (construct via `scan_model` in the test if simpler). The plan cannot pre-specify these keys — David's shape wins; the OUTPUT contract above is fixed.

- [ ] **Step 2: Write table-driven failing tests** — at minimum: single-region raster maps to `stxm_fly_raster` with correct start/stop/n conversion (centers/ranges → start/stop if that's the shape) and dwell in ms; multi-energy maps to `stxm_energy_stack` with the expanded energy list (reuse David's/our region-expansion logic — check `lightfall_pystxmcontrol/energy_ranges.py` in the plugin repo for precedent, but implement standalone here, no plugin import); Ptychography/Focus/Line-Spectrum/point scan_types raise `UnsupportedScanMode`; missing keys raise `KeyError`-derived errors with the key named.

- [ ] **Step 3-5: Implement pure functions, iterate to green, commit** (`feat(remote): scan-model -> Lightfall plan mapping (fly raster + energy stack)`). No Qt, no I/O in this module.

---

### Task 4: `MotorMonitorSet` — CA readback monitors (+ fleet fixture)

**Files:**
- Create: `pystxmcontrol/remote/ca_monitors.py`
- Modify: `tests/remote/conftest.py` (add fleet fixture — port the spec-#3 pattern)
- Test: `tests/remote/test_ca_monitors.py`

**Interfaces:**
- Produces: `MotorMonitorSet(motors: dict[str, str], on_update: Callable[[dict], None], min_period_s: float = 0.2)` — `motors` maps display name → PV prefix; subscribes `<pv>.RBV` and `<pv>.MOVN` via ONE caproto threading `Context`; coalesces updates and invokes `on_update({name: float, ..., "status": {name: bool}})` at most every `min_period_s` (trailing-edge flush so the final value always lands); `start()` / `stop()` (stop unsubscribes + closes context); `connected: dict[str, bool]` property (per-motor CA connection state, drives the panel grey-out).
- Fleet fixture: `stxm_fleet` in `tests/remote/conftest.py`, PORTED from `lightfall-pystxmcontrol/tests/conftest.py` (iocs_src → `PYSTXMCONTROL_IOCS_SRC` default `..\_pystxmcontrol_iocs_wt`; issued-port-tracking `_free_udp_port`; env save/restore in finally; sim JSONs — copy `sim_motor.json`/`sim_daq.json` content into `tests/remote/data/` in THIS repo, do not path-reach into the plugin repo). Session-scoped; yields `.motor_pv` / `.fly_prefix` / `.daq_prefix` / `.addr_list`.

- [ ] **Step 1: Port the fleet fixture + write failing tests.** Tests: (a) monitor set delivers an initial position snapshot for SampleX/SampleY within 5 s of `start()`; (b) after a caproto-client `.VAL` put moving SampleX to 7.0, `on_update` eventually reports `SampleX ≈ 7.0` and `status["SampleX"]` transitioned True→False (collect all callbacks, assert on the sequence); (c) update rate: with a long slow move, callbacks arrive no faster than `min_period_s` apart (allow jitter: assert median inter-arrival ≥ 0.8*min_period); (d) `stop()` → no callbacks after; (e) unknown PV → `connected[name] is False` within timeout, others unaffected.
- [ ] **Step 2: Verify failure; implement.** One `caproto.threading.client.Context`; subscriptions via `pv.subscribe(data_type='time')`; callbacks push into a lock-guarded pending dict; a timer thread (or timestamp check on each callback) flushes at `min_period_s` with a trailing flush. No Qt here — `on_update` is a plain callable (RemoteBackend adapts it to a signal in Task 5).
- [ ] **Step 3: Green (live fleet), full tests/remote suite, commit** (`feat(remote): CA readback monitor set with coalesced updates`).

---

### Task 5: `RemoteBackend` (QThread + asyncio bridge)

**Files:**
- Create: `pystxmcontrol/remote/qt_bridge.py`
- Test: `tests/remote/test_qt_bridge.py` (offscreen Qt; stubbed client — no broker needed)

**Interfaces:**
- Consumes: `LightfallClient` (injected, constructed but not connected), `MotorMonitorSet`, `map_scan`.
- Produces: `RemoteBackend(QtCore.QThread)` — hosts an asyncio loop in `run()`; public THREAD-SAFE methods (each schedules onto the loop via `asyncio.run_coroutine_threadsafe`):
  - `connect_and_authenticate()`, `fetch_config()`, `move_motor(name, position)`, `submit_scan(scan_dict)`, `abort_scan()`, `shutdown()`
  - Qt signals: `authenticated(dict)`, `auth_failed(str)`, `config_ready(dict)`  (`{"motors": {name: {"pv": str, "category": str}}, "plans": [...]}`), `motor_positions(dict)` (the `motorPositions` dict shape), `engine_state(str)`, `scan_submitted(dict)`, `scan_error(str)`, `run_new(dict)`, `run_complete(dict)`, `remote_error(str)`
  - Internals: `fetch_config` = `device.search {}` → per-device `device.info` (collect `pv`, `category`) → `plan.list`; motors = entries with `category` containing `"motor"`. `move_motor` → `device.put {device, value, wait: true}`; RemoteError(busy/limits) → `scan_error`/`remote_error` with the message. `submit_scan` → `map_scan` → `plan.run {plan_name, params, behavior:"reject"}`; UnsupportedScanMode → `scan_error`. Subscribes `runs.new/runs.complete/state.engine` broadcast events → signals. Starts `MotorMonitorSet` after `config_ready` using the fetched PVs, adapting `on_update` → `motor_positions` signal via `QtCore.QMetaObject`-safe emission (signals are thread-safe to emit — emit directly from the monitor thread).
- Test double: `FakeLightfallClient` in the test module implementing the async surface with canned replies + call log; no NATS.

- [ ] **Step 1: Failing tests** (offscreen): backend thread starts/authenticates (authenticated signal, `QSignalSpy` or a plain list + `QTest.qWait`); fetch_config emits config_ready with motors filtered by category and PVs present; submit_scan happy path calls plan.run with mapped params (inspect fake's call log); busy RemoteError from plan.run → scan_error signal, no crash; move_motor limits error → remote_error; runs.new event from the fake → run_new signal; shutdown joins the thread cleanly (thread not alive within 5 s).
- [ ] **Step 2: Implement.** Loop lifecycle: `run()` creates loop, runs forever; `shutdown()` schedules loop.stop + joins with timeout. All client calls wrapped: `RemoteError` → structured signal, unexpected exception → `remote_error(str)` + traceback to stderr (never kill the loop).
- [ ] **Step 3: Green, suite, commit** (`feat(remote): RemoteBackend QThread bridging asyncio client to Qt signals`).

---

### Task 6: `RunStreamer` — Tiled run → live image payloads

**Files:**
- Create: `pystxmcontrol/remote/tiled_stream.py`
- Test: `tests/remote/test_tiled_stream.py` (stub run tree; live coverage lands in Task 8)

**Interfaces:**
- Consumes: a tiled run node (duck-typed: `run.metadata["start"]` with the spec-#3 contract's `stxm` block / `shape`/`x_extent`/`y_extent` md; `run["primary"]` stream readable as a table via `.read()` — mirror `lightfall_pystxmcontrol/contract.py`'s documented layout, read that file first).
- Produces: `RunStreamer(tiled_client_factory, run_uid, on_image, on_progress, poll_s=1.0, data_field="Counter1")` — background thread polling the run's primary stream table facet (`stream.read()` — NEVER scalar column facets, per the Tiled gotchas), assembling a 2-D (ny,nx) float array (NaN-filled) from line events (`SampleX` arrays + `SampleY` + counts rows, per the contract), invoking `on_image({daq_name: 2d_array}, extents)` when new rows arrive and `on_progress(rows_done, rows_total)`; `stop()`. On `runs.complete` the backend calls `stop()` after a final poll.
- [ ] **Step 1: Failing tests** with a `FakeRun` (dict metadata + a `FakeStream` whose `read()` returns a pandas/dict table growing between polls): image assembles rows in order, NaN rows until filled, extents from md, progress counts, stop() halts, malformed/missing stream → one `on_error` (add `on_error` callback) not a crash.
- [ ] **Step 2: Implement + green + commit** (`feat(remote): RunStreamer - Tiled line-event polling into live images`). Read `lightfall_pystxmcontrol/contract.py` + `stxm_map_viz.py` read-side first; transcribe the layout rules, import nothing from the plugin.

---

### Task 7: MainController integration + app entry point

**Files:**
- Modify: `pystxmcontrol/gui/controllers/main_controller.py` (bounded: client construction + seams listed below)
- Create: `pystxmcontrol/remote/app.py`, packaged default `pystxmcontrol/remote/remote.json`
- Test: `tests/remote/test_qt_integration.py` (offscreen; FakeLightfallClient-backed RemoteBackend driving the REAL MainController + models)

**Interfaces:**
- Consumes: everything above.
- Produces: `MainController(backend=...)` accepts a `RemoteBackend`; when provided it does NOT construct `stxm_client`/`ControlThread` and instead: `initialize_client()` → `backend.connect_and_authenticate()` + `fetch_config()`; `config_ready` → populate `motor_model.set_motor_info` (adapt: build a motorInfo-shaped dict from the config payload — read what `set_motor_info` expects and synthesize minimally); `backend.motor_positions → _handle_monitor_message`-compatible dict (reuse the handler); `start_scan()` → `backend.submit_scan(scan_config)` (keep validation + `_live_stxm` creation); `cancel_scan()` → `backend.abort_scan()`; `move_motor` → `backend.move_motor`; `run_new` → start a `RunStreamer` (via backend) whose `on_image` feeds the same image-model path scan images use today (pin the exact scan-image dict shape from `_handle_monitor_message` ~:340-480 and synthesize it); `run_complete` → the `"scan_complete"` path. DISABLED when backend mode: `set_gate`, `move_to_focus`, `change_motor_config`, `query_motor_history` (methods emit `status_updated("not available in remote mode")`), CCD/ptycho monitor hookups skipped. Unsupported scan types: `start_scan` surfaces the `UnsupportedScanMode` message. The legacy ZMQ path stays intact when `backend=None` (default) — David's local mode keeps working.
  - `app.py::main()` — argparse `--config` (default packaged `remote.json`: `{"nats_url": "nats://127.0.0.1:4222", "prefix": "als.stxm", "app_name": "pystxmcontrol-remote"}`), builds QApplication, LightfallClient, RemoteBackend, MainWindowMVC with the backend-carrying controller; auth-failure dialog with retry/quit.
- [ ] **Step 1: Read the integration surface first** — `_handle_monitor_message` image branch (~:340-480), `set_motor_info` expectations (`gui/models/motor_model.py`), `MainWindowMVC` construction of `MainController` (how to thread the backend kwarg through). Record shapes in the report.
- [ ] **Step 2: Failing integration tests** — with FakeLightfallClient: controller initializes (config → motor model populated); move_motor routes to device.put; start_scan with a raster scan-model dict routes to plan.run; busy → error_occurred signal; synthesized run_new + fake streamer image → image_model updated; run_complete → scanning False + scan_state_changed(False); disabled features emit the not-available message; `backend=None` still constructs the ZMQ client class (import-only check, no server).
- [ ] **Step 3: Implement (keep edits surgical — every hunk inside MainController should be a seam swap, not a rewrite), iterate, green, commit** (`feat(remote): MainController speaks RemoteBackend; stxmcontrol-remote entry point`).

---

### Task 8: Contract + e2e tests (live Lightfall service + fleet)

**Files:**
- Test: `tests/remote/test_contract.py`, `tests/remote/test_e2e_gui.py`
- Possibly Modify: `tests/remote/conftest.py` (lightfall-service fixture)

**Interfaces:** consumes everything; lightfall imports ALLOWED here (tests only). Requires lightfall checked out on `feature/device-info-pv` (Task 1) — assert `pv` present and fail with a clear message telling the operator to check out that branch if missing.

- [ ] **Step 1: READ `lightfall/tests/integration/test_remote_control_e2e.py`** — how it stands up LocalNatsServer + RemoteControlService + engine + auto-approving trust; port that wiring into a `lightfall_service` fixture here (session-scoped), configured with the lightfall-pystxmcontrol plugin devices (happi DB from the plugin repo — it's installed in the venv; use its packaged `pystxm_happi.json`) and the sim IOC fleet (reuse `stxm_fleet`, started FIRST so EpicsMotors connect).
- [ ] **Step 2: `test_contract.py`** — LightfallClient (real NATS) against the live service: authenticate → token+tiled fields; bare-subject call rejected (`denied`); `device.search`/`device.info` returns SampleX/SampleY/energy WITH `pv` fields matching the fleet PVs; `device.put` moves SampleY (verify over CA RBV); `plan.list` contains stxm_fly_raster; busy rejection while a plan runs.
- [ ] **Step 3: `test_e2e_gui.py`** (the golden-run bar, offscreen Qt): RemoteBackend + real MainController against the live service+fleet: initialize (config_ready), submit a small fly raster via `start_scan()`, observe run_new → RunStreamer assembles the image from Tiled, final image shape (ny,nx) with all-finite values matching the run's Tiled data (fetch independently and compare), motor panel positions track a commanded `move_motor`, `run_complete` → scanning False. Generous timeouts; this test may take ~1-2 min.
- [ ] **Step 4: Full tests/remote suite green twice; commit** (`test(remote): contract + golden-run e2e against live Lightfall service and sim fleet`).

---

### Task 9: Docs + whole-branch verification

- [ ] **Step 1:** README section in the fork (`README.md` or `docs/`): what `stxmcontrol-remote` is, remote.json config, the three transports, prerequisites (Lightfall instance with remote service + sim fleet for demo, `pip install pystxmcontrol[remote]`), v1 scan-mode scope, what's disabled in remote mode. Transcribe, don't invent.
- [ ] **Step 2:** Full `tests/remote` + the fork's pre-existing test suite (if any collected at this branch) twice; grep `import lightfall` under `pystxmcontrol/` (must be ZERO hits — lightfall only under `tests/`); manual smoke: start fleet + a real Lightfall (or the test harness service) and run `stxmcontrol-remote` once, submit a raster, see the live image (document in the report with the doc-stream evidence).
- [ ] **Step 3:** superpowers:requesting-code-review (whole branch, both repos' diffs) → superpowers:finishing-a-development-branch. Fork branch LOCAL; lightfall branch LOCAL — Ron drives merges/pushes/upstream PR to David. Named follow-ups: analysis/browser Tiled conversion (next spec); spiral/ptycho modes; panel slim-down (old spec #3); device streaming.

---

## Self-review notes

- Spec §2.1 hybrid → Tasks 4 (CA readbacks) + 5/7 (`device.put` moves). §2.2 scope → Task 7's disabled-features list; analysis/browser untouched. §2.3 modes → Task 3. §2.4 contract addition → Task 1. §3.1 modules → Tasks 2-6 one-to-one. §3.3 entry+config → Task 7. §3.4 → Task 1. §4 failure modes → Tasks 5 (reconnect/backoff is follow-up if not reached — the spec's re-handshake precedent lands in Task 5's error paths; auth dialog in Task 7), 6 (`on_error`), 4 (`connected` grey-out). §5 testing tiers → Tasks 2/3 (unit), 8 (contract+e2e), offscreen Qt throughout.
- Investigative steps are explicitly load-bearing where David's shapes rule (Task 3 Step 1, Task 7 Step 1, Task 8 Step 1) — output contracts stay fixed; input shapes get pinned from source. No placeholders otherwise.
- Type consistency: `LightfallClient` API fixed in Task 2 and consumed verbatim in 5/8; `map_scan` tuple in 3→5; `MotorMonitorSet` callback dict shape in 4→5→7 (`motorPositions` handler reuse); signal names listed once in Task 5 and consumed in 7/8.
- NOTE: spec §4's NATS reconnect-with-backoff is deliberately thinned to: error signals + re-handshake on channel death in Task 5, full auto-reconnect loop named as a follow-up if it doesn't fall out naturally — record in the final report either way.
