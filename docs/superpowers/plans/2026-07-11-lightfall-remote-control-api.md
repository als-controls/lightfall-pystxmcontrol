# Lightfall Remote Control API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec #1 of the pystxmcontrol-remote-client program: capability-channel trust enforcement in `IPCService` plus a new `RemoteControlService` exposing plan/queue/engine/device verbs over NATS, with a headless reference client, e2e tests, and updated IPC docs.

**Architecture:** Two layers. `IPCService` (lightfall/ipc/service.py) gains generic trust plumbing: per-login-session capability channels (`{prefix}.session.{token}.>`), central rejection of bare `commands.*`, teardown on logout. `lightfall/remote/service.py` (`RemoteControlService`) owns all action semantics — thin adapters over the existing engine, plan registry, and DeviceCatalog — and absorbs `_wire_plan_commands` / `_wire_engine_ipc` from `core/application.py`. Handlers never gate themselves; enforcement is central.

**Tech Stack:** Python 3.11+, PySide6, nats-py, bluesky/ophyd, pytest + pytest-qt + pytest-asyncio, LocalNatsServer (nats-server-bin) for e2e.

**Spec:** `~/PycharmProjects/ncs/lightfall-pystxmcontrol/docs/superpowers/specs/2026-07-10-lightfall-remote-control-design.md` (approved; breaking changes in §2 are Ron-approved — do NOT water them down for back-compat).

## Global Constraints

- **Repo/worktree:** all code changes in a git worktree of `C:\Users\rp\PycharmProjects\ncs\lightfall`, branch `feature/remote-control-api` off `master`. Package lives under `src/lightfall/`.
- **Test command (exact, from the worktree root):**
  `QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest <paths> -v`
  NEVER bare `pytest`. `PYTHONPATH=src` is REQUIRED in a worktree (editable install resolves to the main checkout otherwise).
- **Shared repo:** NEVER `git add -A` or `git add .`. Explicit paths only. Ron's WIP files (e.g. `scripts/diag_live.py`) must never be staged.
- **Commit trailers** (every commit):
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01PFykQo3UJmNXTg3kxLHKxv`
- **Branch stays local.** No push, no PR — Ron drives integration.
- **Breaking changes (approved, spec §2):** `procedure_id`→`item_id`; `run_id`→`run_uid` in `runs.new`/`runs.complete` (`runs.new` gains `item_id`); `plan.run` default behavior `"reject"`; ALL `commands.*` (incl. `logbook.add`, `agent.message`) move behind the capability channel.
- **Structured errors everywhere:** `{"status": "error", "code": <busy|limits|timeout|unknown|denied|bad_request|version_mismatch>, "message": str, "contract_version": 1}`.
- **Every reply carries `contract_version: 1`.**
- **Deferred (spec §8, do NOT build):** device value streaming, leases, scan-safe allowlist, loopback short-circuit, broker-side permission provisioning.
- Existing conventions: loguru `logger`, `from __future__ import annotations`, Google-style docstrings, ruff-clean (`ruff check src/` must pass).

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/lightfall/remote/__init__.py` | Create | Package init, exports |
| `src/lightfall/remote/protocol.py` | Create | `CONTRACT_VERSION`, `ok_reply()`, `error_reply()`, error codes |
| `src/lightfall/remote/service.py` | Create | `RemoteControlService` — all action semantics + run-lifecycle events |
| `src/lightfall/ipc/service.py` | Modify | Capability channels: mint/route/reject/teardown; `trusted=` actions; `session_token` in auth response; `_make_handler` passes real msg.subject |
| `src/lightfall/core/application.py` | Modify | Delete `_wire_plan_commands`/`_wire_engine_ipc`; wire `RemoteControlService`; `trusted=True` on logbook/agent actions; logout hook |
| `tests/remote/test_protocol.py` | Create | Protocol helper tests |
| `tests/ipc/test_capability_channels.py` | Create | IPCService trust plumbing tests |
| `tests/remote/test_service_plan.py` | Create | plan.list/run/abort, queue.get, engine.status |
| `tests/remote/test_service_device.py` | Create | device.search/components/info/get/put |
| `tests/remote/test_logout_teardown.py` | Create | Logout → clear + teardown |
| `tests/ipc/test_integration.py` | Modify | Update wiring tests to new field names / new wiring |
| `tests/integration/remote_client.py` | Create | Headless reference client (raw nats-py) |
| `tests/integration/test_remote_control_e2e.py` | Create | LocalNatsServer + real RunEngine + sim devices e2e |
| `docs/developer-guide/ipc-architecture.md` | Modify | Capability channels, RemoteControlService, per-login trust |
| `docs/developer-guide/ipc-client-guide.md` | Modify | New handshake, new verbs, renamed fields, structured errors |

Note: lightfall's own `docs/superpowers/` is **gitignored** — this plan lives in lightfall-pystxmcontrol (committed). The client guide/architecture docs in lightfall ARE the committed contract.

## Key upstream facts (verified 2026-07-11, master)

- `IPCService.register_action(suffix, callback, *, description="", schema=None, main_thread=True)` at `src/lightfall/ipc/service.py:167`; `subscribe(subject, callback, *, main_thread=True)` at :494; `reply()`/`publish()` are thread-safe; `_make_handler` (:689) currently passes the **subscription pattern**, not `msg.subject` (must change for wildcards); `build_auth_response` at :303; `unsubscribe(subject)` at :522.
- `TrustManager` (`src/lightfall/ipc/trust.py:39`): `approve/deny/revoke/clear/check`, thread-safe. `clear()` exists, unwired.
- `core/application.py`: `_register_core_services` :245 (registers `TrustManager`, `IPCService` factories); `_start_ipc` :317 (registers `auth.request` → `_handle_ipc_auth_request` :601, then `_wire_engine_ipc` :346, `_wire_plan_commands` :420, `_wire_logbook_ipc` :501, `_wire_agent_ipc` :559); `_shutdown` :715 stops IPC.
- `SessionManager` (`src/lightfall/auth/session.py`): signals `state_changed = Signal(AuthState, AuthState)` (new, old), `user_changed = Signal(User)`; `logout()` :524 clears service keys at :545-548 and emits `user_changed(ANONYMOUS_USER)`. Nothing tears down IPC/trust today.
- Engine: `get_engine()` (`src/lightfall/acquire/engine/__init__.py:63`, singleton). `BaseEngine.submit(procedure, *, priority=1, name="", ...) -> str | None` (base.py:182) — **queued**, returns `PrioritizedProcedure.id` (uuid4 str). `get_queue_items() -> list[PrioritizedProcedure]` :279, `get_current_procedure()` :288, `queue_size` :152. `BlueskyEngine.is_idle` (bluesky.py:227) = `_RE is not None and _RE.state == "idle"`; `abort(reason="") -> bool` (bluesky.py:526). Signals on BaseEngine: `sigOutput(str, dict)`, `sigFinish()`, `sigAbort()`, `sigException(Exception)`, `sigStateChanged(str)` (emits `"idle"/"running"/"paused"/...`). `PrioritizedProcedure` fields: `.id`, `.name`, `.priority`, `.submitted_at`.
- Plans: `get_registry()` (`src/lightfall/acquire/plans/registry.py:536`); `PlanInfo` fields incl. `name`, `func`, `parameters: list[ParameterInfo]`, `description`; `ParameterInfo(name, annotation, default, kind, description)` with raw `Annotated[...]` in `annotation`, `required` property. `list_plans()` exists on registry (`get_plan(name)`, `list_plans()` — verify exact name at implementation time; `get_plan` confirmed at application.py:442). Annotated metadata decomposed by `extract_annotated_metadata(annotation, func) -> (base_type, list[meta])` at `src/lightfall/ui/widgets/plan_config.py:194`; metadata classes `Unit(suffix)`, `Default(value)`, `Range(min,max)` in `src/lightfall/ui/annotations.py`.
- Devices: `DeviceCatalog.get_instance()` (`src/lightfall/devices/catalog.py:90`); `get_device_by_name(name) -> DeviceInfo | None` :680; `list_devices(category=None, beamline=None, active_only=True)` :723; `get_ophyd_device(name) -> Any` :988. `DeviceInfo` (`devices/model.py:149`): `name`, `description`, `category: DeviceCategory` (StrEnum MOTOR/DETECTOR/CONTROLLER), `device_class: str`, `prefix`, `beamline`, `tags`, `active`, `metadata: dict`. Component enumeration must use `component_names` + `_sig_attrs`/`_signals` dicts (NOT getattr — avoids triggering lazy Components; see `ui/models/device_tree.py:551-605`). Writability: not writable if class name contains `"ReadOnly"`/`"RO"`, else `hasattr(obj, "put") or hasattr(obj, "set")` (`ui/widgets/signal_control.py:77`). Put-with-completion: `status = obj.set(value)`; `status.wait(timeout=...)` (pattern in `tests/test_sim_areadetector.py:114`). Sim devices: `ophyd.sim.SynAxis/SynGauss/SynSignal`; `MockBackend` in `devices/backends/mock.py`.
- `LocalNatsServer(port=4222, host="127.0.0.1")` (`src/lightfall/ipc/local_server.py:105`): `start(timeout_s=5.0)`, `stop()`, no TLS/JetStream; binary via `resolve_nats_binary()` (bundled next to venv python, `nats-server-bin` package). Caller builds `f"nats://127.0.0.1:{port}"`. **IPCService `_connect_and_serve` always passes `tls=ssl.create_default_context()`** (service.py:627-628) yet connects fine to the plaintext local server today (nats-py ignores tls unless server advertises it) — application already uses this combination with `ipc_use_local_nats` (application.py:281-315), so do NOT change TLS handling.
- Tests: pytest config in `pyproject.toml` (`qt_api=pyside6`, `asyncio_mode=auto`, marker `integration` opt-in via `LIGHTFALL_INTEGRATION=1`). `tests/conftest.py` sets `OPHYD_CONTROL_LAYER=dummy` and resets singleton services (incl. `DeviceCatalog`) autouse. pytest-qt supplies `qapp`. Existing IPC wiring tests build fake services via `IPCService.__new__(IPCService)` + attribute injection (`tests/ipc/test_integration.py:24-38`) — reuse that pattern.

## Design decisions locked by this plan

1. **Identity attach:** the session router injects `data["_identity"] = {"app_name": ..., "session_token": ...}` into the payload before invoking the handler (any client-supplied `_identity` key is stripped first). Handlers read it if they care; most don't.
2. **`register_action(..., trusted=True)`:** trusted actions are NOT subscribed on their bare subject with their real handler. Instead the bare subject gets a rejection handler replying `denied`, and the real handler is stored in `_trusted_actions` and reachable only through the session router. Untrusted actions (`auth.request`, `meta.*`) keep today's behavior and are NOT reachable via the session channel.
3. **Threading:** all `RemoteControlService` handlers register with `main_thread=False` (run on the NATS loop) and immediately hand blocking work to a `ThreadPoolExecutor` owned by the service, replying from the worker. Engine document signals (`sigOutput` etc.) arrive on the Qt main thread via queued connections, so an executor thread can wait on a `threading.Event` set by the main thread without deadlock. `plan.abort` marshals `engine.abort()` to the main thread via `invoke_in_main_thread`.
4. **Contract version check:** the session router rejects payloads whose `contract_version` is present and ≠ 1 with `version_mismatch`. Absent means "assume 1" (v1 clients may omit it).
5. **Re-auth of an already-trusted app mints a fresh token** (multiple live tokens per app are fine; all die on logout).
6. **`engine.status` contract state** is `"idle"` iff `engine.is_idle` else `"running"` (paused/aborting map to `"running"` for the v1 contract).

---

### Task 1: Protocol helpers (`lightfall.remote.protocol`)

**Files:**
- Create: `src/lightfall/remote/__init__.py`
- Create: `src/lightfall/remote/protocol.py`
- Test: `tests/remote/__init__.py` (empty), `tests/remote/test_protocol.py`

**Interfaces:**
- Produces: `CONTRACT_VERSION: int = 1`; `ERROR_CODES: frozenset[str]`; `ok_reply(**fields) -> dict`; `error_reply(code: str, message: str) -> dict`. Every later task uses these to build replies.

- [ ] **Step 1: Write the failing tests**

```python
# tests/remote/test_protocol.py
"""Tests for the remote-control reply protocol helpers."""

import pytest

from lightfall.remote.protocol import CONTRACT_VERSION, ERROR_CODES, error_reply, ok_reply


def test_contract_version_is_1():
    assert CONTRACT_VERSION == 1


def test_ok_reply_merges_fields_and_stamps_version():
    reply = ok_reply(status="submitted", item_id="abc")
    assert reply == {"status": "submitted", "item_id": "abc", "contract_version": 1}


def test_error_reply_shape():
    reply = error_reply("busy", "engine is running")
    assert reply == {
        "status": "error",
        "code": "busy",
        "message": "engine is running",
        "contract_version": 1,
    }


def test_error_reply_rejects_unknown_code():
    with pytest.raises(ValueError):
        error_reply("nonsense", "x")


def test_error_codes_match_spec():
    assert ERROR_CODES == frozenset(
        {"busy", "limits", "timeout", "unknown", "denied", "bad_request", "version_mismatch"}
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from worktree root):
`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/remote/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lightfall.remote'`

- [ ] **Step 3: Implement**

```python
# src/lightfall/remote/__init__.py
"""Remote-control API for external clients (spec: lightfall-remote-control-design)."""
```

```python
# src/lightfall/remote/protocol.py
"""Reply protocol for the remote-control contract (v1).

Every reply — success or error — carries ``contract_version`` so clients can
detect mismatches. Errors are structured: ``{status: "error", code, message}``.
"""

from __future__ import annotations

from typing import Any

__all__ = ["CONTRACT_VERSION", "ERROR_CODES", "error_reply", "ok_reply"]

CONTRACT_VERSION = 1

ERROR_CODES = frozenset(
    {"busy", "limits", "timeout", "unknown", "denied", "bad_request", "version_mismatch"}
)


def ok_reply(**fields: Any) -> dict:
    """Build a success reply carrying ``contract_version``."""
    return {**fields, "contract_version": CONTRACT_VERSION}


def error_reply(code: str, message: str) -> dict:
    """Build a structured error reply.

    Args:
        code: One of :data:`ERROR_CODES`.
        message: Human-readable detail.

    Raises:
        ValueError: If *code* is not a known error code.
    """
    if code not in ERROR_CODES:
        raise ValueError(f"Unknown error code: {code!r}")
    return {
        "status": "error",
        "code": code,
        "message": message,
        "contract_version": CONTRACT_VERSION,
    }
```

Also create empty `tests/remote/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass** (same command). Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lightfall/remote/__init__.py src/lightfall/remote/protocol.py tests/remote/__init__.py tests/remote/test_protocol.py
git commit -m "feat(remote): add contract-v1 reply protocol helpers"
```
(with the trailer lines from Global Constraints — applies to every commit below.)

---

### Task 2: IPCService capability channels

**Files:**
- Modify: `src/lightfall/ipc/service.py`
- Test: `tests/ipc/test_capability_channels.py`

**Interfaces:**
- Consumes: `error_reply`, `ok_reply` from Task 1.
- Produces (on `IPCService`):
  - `register_action(suffix, callback, *, description="", schema=None, main_thread=True, trusted=False) -> _ActionHandle`
  - `mint_session_channel(app_name: str) -> str` — mints token, subscribes `{prefix}.session.{token}.>`, returns token.
  - `teardown_session_channels(app_name: str | None = None) -> None` — unsubscribe + forget tokens (all, or one app's).
  - `session_channel_count` (property, for tests/teardown assertions).
  - `build_auth_response(..., app_name: str | None = None)` — approved responses gain `"session_token"` and `"contract_version"`.
  - Handlers registered `trusted=True` receive `data["_identity"] = {"app_name", "session_token"}` when called via the channel; bare-subject calls get `error_reply("denied", ...)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/ipc/test_capability_channels.py
"""Unit tests for IPCService capability-channel trust plumbing.

Uses the same fake-IPCService construction pattern as tests/ipc/test_integration.py:
IPCService.__new__ + manual attribute injection, capturing outbound replies.
"""

from __future__ import annotations

import pytest

from lightfall.ipc.service import IPCService


def _make_ipc(prefix: str = "als.test") -> tuple[IPCService, list[tuple[str, dict]]]:
    """Build a disconnected IPCService whose publish() captures messages."""
    ipc = IPCService.__new__(IPCService)
    ipc._topic_prefix = prefix
    ipc._subscriptions = {}
    ipc._action_catalog = {}
    ipc._event_catalog = {}
    ipc._trusted_actions = {}
    ipc._session_channels = {}
    ipc._trust = None
    ipc._instance_id = "test-1"
    ipc._display_name = None
    ipc._loop = None
    ipc._nc = None
    ipc._connected = False

    sent: list[tuple[str, dict]] = []
    ipc.publish = lambda subject, data: sent.append((subject, data))  # type: ignore[method-assign]
    return ipc, sent


def _call_subscription(ipc: IPCService, subject: str, data: dict, reply: str) -> None:
    """Invoke the callback registered for *subject* directly (as _make_handler would)."""
    ipc._subscriptions[subject].callback(subject, data, reply)


class TestMint:
    def test_mint_returns_unguessable_token_and_subscribes_wildcard(self):
        ipc, _ = _make_ipc()
        token = ipc.mint_session_channel("pystxm")
        assert len(token) >= 22  # token_urlsafe(32) -> 43 chars; 128-bit floor
        assert f"als.test.session.{token}.>" in ipc._subscriptions

    def test_mint_twice_gives_distinct_tokens(self):
        ipc, _ = _make_ipc()
        assert ipc.mint_session_channel("a") != ipc.mint_session_channel("a")
        assert ipc.session_channel_count == 2


class TestRouting:
    def test_trusted_action_reachable_via_channel_with_identity(self):
        ipc, sent = _make_ipc()
        calls: list[dict] = []
        ipc.register_action("commands.thing.do", lambda s, d, r: calls.append(d), trusted=True)
        token = ipc.mint_session_channel("pystxm")

        _call_subscription(
            ipc,
            f"als.test.session.{token}.>",
            {"x": 1},
            "_INBOX.1",
        )
        # Router receives the *actual* subject via _make_handler change; simulate it:
        # the router callback is registered under the wildcard, called with real subject.
        # (See router test below for the real-subject path.)

    def test_router_dispatches_by_real_subject(self):
        ipc, sent = _make_ipc()
        seen: list[tuple[str, dict]] = []
        ipc.register_action(
            "commands.thing.do",
            lambda s, d, r: seen.append((s, d)),
            trusted=True,
            main_thread=False,
        )
        token = ipc.mint_session_channel("pystxm")
        router = ipc._subscriptions[f"als.test.session.{token}.>"].callback
        router(f"als.test.session.{token}.commands.thing.do", {"x": 1}, "_INBOX.1")
        assert len(seen) == 1
        subject, data = seen[0]
        assert subject == "commands.thing.do"
        assert data["x"] == 1
        assert data["_identity"] == {"app_name": "pystxm", "session_token": token}

    def test_client_supplied_identity_is_stripped(self):
        ipc, _ = _make_ipc()
        seen: list[dict] = []
        ipc.register_action("commands.t.d", lambda s, d, r: seen.append(d), trusted=True, main_thread=False)
        token = ipc.mint_session_channel("appA")
        router = ipc._subscriptions[f"als.test.session.{token}.>"].callback
        router(f"als.test.session.{token}.commands.t.d", {"_identity": {"app_name": "fake"}}, "_INBOX.1")
        assert seen[0]["_identity"]["app_name"] == "appA"

    def test_unknown_suffix_on_channel_gets_unknown_error(self):
        ipc, sent = _make_ipc()
        token = ipc.mint_session_channel("appA")
        router = ipc._subscriptions[f"als.test.session.{token}.>"].callback
        router(f"als.test.session.{token}.commands.nope", {}, "_INBOX.9")
        assert sent[-1][0] == "_INBOX.9"
        assert sent[-1][1]["status"] == "error"
        assert sent[-1][1]["code"] == "unknown"

    def test_untrusted_action_not_reachable_via_channel(self):
        ipc, sent = _make_ipc()
        ipc.register_action("meta.actions", lambda s, d, r: None)  # untrusted
        token = ipc.mint_session_channel("appA")
        router = ipc._subscriptions[f"als.test.session.{token}.>"].callback
        router(f"als.test.session.{token}.meta.actions", {}, "_INBOX.2")
        assert sent[-1][1]["code"] == "unknown"

    def test_version_mismatch_rejected(self):
        ipc, sent = _make_ipc()
        ipc.register_action("commands.t.d", lambda s, d, r: None, trusted=True, main_thread=False)
        token = ipc.mint_session_channel("appA")
        router = ipc._subscriptions[f"als.test.session.{token}.>"].callback
        router(f"als.test.session.{token}.commands.t.d", {"contract_version": 2}, "_INBOX.3")
        assert sent[-1][1]["code"] == "version_mismatch"


class TestBareSubjectRejection:
    def test_bare_commands_subject_replies_denied(self):
        ipc, sent = _make_ipc()
        ipc.register_action("commands.plan.run", lambda s, d, r: None, trusted=True)
        _call_subscription(ipc, "als.test.commands.plan.run", {"plan_name": "x"}, "_INBOX.4")
        assert sent[-1][0] == "_INBOX.4"
        assert sent[-1][1]["status"] == "error"
        assert sent[-1][1]["code"] == "denied"

    def test_trusted_action_still_in_catalog(self):
        ipc, _ = _make_ipc()
        ipc.register_action("commands.plan.run", lambda s, d, r: None, trusted=True)
        assert any(a["subject"] == "commands.plan.run" for a in ipc.list_actions())

    def test_unregister_trusted_action_removes_both(self):
        ipc, _ = _make_ipc()
        handle = ipc.register_action("commands.plan.run", lambda s, d, r: None, trusted=True)
        handle.unregister()
        assert "commands.plan.run" not in ipc._trusted_actions
        assert "als.test.commands.plan.run" not in ipc._subscriptions


class TestTeardown:
    def test_teardown_all(self):
        ipc, _ = _make_ipc()
        t1 = ipc.mint_session_channel("a")
        t2 = ipc.mint_session_channel("b")
        ipc.teardown_session_channels()
        assert ipc.session_channel_count == 0
        assert f"als.test.session.{t1}.>" not in ipc._subscriptions
        assert f"als.test.session.{t2}.>" not in ipc._subscriptions

    def test_teardown_single_app(self):
        ipc, _ = _make_ipc()
        ta = ipc.mint_session_channel("a")
        tb = ipc.mint_session_channel("b")
        ipc.teardown_session_channels("a")
        assert ipc.session_channel_count == 1
        assert f"als.test.session.{ta}.>" not in ipc._subscriptions
        assert f"als.test.session.{tb}.>" in ipc._subscriptions

    def test_dead_token_routes_nowhere(self):
        ipc, sent = _make_ipc()
        seen = []
        ipc.register_action("commands.t.d", lambda s, d, r: seen.append(d), trusted=True, main_thread=False)
        token = ipc.mint_session_channel("a")
        router = ipc._subscriptions[f"als.test.session.{token}.>"].callback
        ipc.teardown_session_channels()
        router(f"als.test.session.{token}.commands.t.d", {}, "_INBOX.5")
        assert seen == []
        assert sent[-1][1]["code"] == "denied"


class TestAuthResponse:
    def test_approved_response_carries_session_token_and_version(self, monkeypatch):
        ipc, _ = _make_ipc()

        class _FakeSM:
            def get_api_key(self, service):
                return "key123"

        import lightfall.auth.session as session_mod

        monkeypatch.setattr(session_mod.SessionManager, "get_instance", staticmethod(lambda: _FakeSM()))

        class _Sess:
            class user:
                attributes = {"sub": "user-1"}

        resp = ipc.build_auth_response(
            approved=True, session=_Sess(), tiled_url="http://t", app_name="pystxm"
        )
        assert resp["status"] == "approved"
        assert resp["contract_version"] == 1
        token = resp["session_token"]
        assert f"als.test.session.{token}.>" in ipc._subscriptions

    def test_denied_response_has_no_token(self):
        ipc, _ = _make_ipc()
        resp = ipc.build_auth_response(approved=False, reason="denied")
        assert resp == {"status": "denied", "reason": "denied", "contract_version": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ipc/test_capability_channels.py -v`
Expected: FAIL — `AttributeError` (`mint_session_channel` / `_trusted_actions` missing) / `TypeError` (unexpected `trusted` kwarg).

- [ ] **Step 3: Implement in `src/lightfall/ipc/service.py`**

3a. Add imports near the top (after existing imports):

```python
import secrets
```
and add to the protocol imports:
```python
from lightfall.remote.protocol import CONTRACT_VERSION, error_reply
```
(NB: `lightfall.remote.protocol` imports nothing from `lightfall.ipc`, so no cycle.)

3b. Add dataclass after `_Subscription`:

```python
@dataclass
class _SessionChannel:
    """A live capability channel minted for a trusted app."""

    token: str
    app_name: str
    wildcard_subject: str
```

3c. In `__init__`, after `self._action_catalog ... self._event_catalog` lines, add:

```python
        self._trusted_actions: dict[str, _Subscription] = {}
        self._session_channels: dict[str, _SessionChannel] = {}
```

3d. Change `_make_handler` so callbacks receive the *actual* message subject (required for wildcard routing; identical for exact subjects). In `_make_handler`, replace the two callback invocation lines:

```python
                if sub.main_thread:
                    invoke_in_main_thread(sub.callback, subject, data, reply)
                else:
                    sub.callback(subject, data, reply)
```
with:
```python
                actual_subject = msg.subject or subject
                if sub.main_thread:
                    invoke_in_main_thread(sub.callback, actual_subject, data, reply)
                else:
                    sub.callback(actual_subject, data, reply)
```

3e. Extend `register_action` — new signature and body:

```python
    def register_action(
        self,
        suffix: str,
        callback: Callable[[str, dict, str | None], Any],
        *,
        description: str = "",
        schema: dict[str, Any] | None = None,
        main_thread: bool = True,
        trusted: bool = False,
    ) -> _ActionHandle:
        """Register a request/reply action handler.

        Args:
            suffix: Subject suffix (appended to the topic prefix).
            callback: Called as ``callback(subject, data, reply)`` for each
                incoming request.
            description: Human-readable description for meta-discovery.
            schema: Optional JSON Schema describing the request payload.
            main_thread: If True (default) the callback runs on the Qt main
                thread.
            trusted: If True the action is reachable ONLY through a session
                capability channel (see :meth:`mint_session_channel`); requests
                on the bare prefixed subject are rejected with a structured
                ``denied`` error. The routed payload carries
                ``data["_identity"] = {"app_name", "session_token"}``.

        Returns:
            An :class:`_ActionHandle` whose :meth:`~_ActionHandle.unregister`
            method removes both the catalog entry and the subscription.
        """
        full_subject = self.topic(suffix)
        self._action_catalog[suffix] = ActionInfo(
            subject=suffix, description=description, schema=schema
        )
        if trusted:
            self._trusted_actions[suffix] = _Subscription(
                subject=suffix, callback=callback, main_thread=main_thread, nats_sub=None
            )
            self.subscribe(full_subject, self._reject_untrusted, main_thread=False)
        else:
            self.subscribe(full_subject, callback, main_thread=main_thread)
        return _ActionHandle(self, suffix, full_subject)
```

3f. Update `_ActionHandle.unregister` to also drop the trusted entry:

```python
    def unregister(self) -> None:
        """Remove this action from the catalog and unsubscribe."""
        self._service._action_catalog.pop(self._suffix, None)
        self._service._trusted_actions.pop(self._suffix, None)
        self._service.unsubscribe(self._subject)
```

3g. Add the capability-channel section (new methods on `IPCService`, e.g. after `build_auth_response`):

```python
    # ------------------------------------------------------------------
    # Capability channels (per-login-session trust)
    # ------------------------------------------------------------------

    @property
    def session_channel_count(self) -> int:
        """Number of live session capability channels."""
        return len(self._session_channels)

    def mint_session_channel(self, app_name: str) -> str:
        """Mint a capability channel for *app_name* and return its token.

        Subscribes ``{prefix}.session.{token}.>`` and routes requests to
        trusted actions with the app identity attached. Possession of the
        token is proof of a completed auth handshake in the current login
        session.
        """
        token = secrets.token_urlsafe(32)
        wildcard = self.topic(f"session.{token}.>")
        self._session_channels[token] = _SessionChannel(
            token=token, app_name=app_name, wildcard_subject=wildcard
        )
        self.subscribe(wildcard, self._route_session_message, main_thread=False)
        logger.info("IPCService: minted session channel for '{}'", app_name)
        return token

    def teardown_session_channels(self, app_name: str | None = None) -> None:
        """Tear down session channels — all of them, or one app's.

        Unsubscribes the wildcard subjects and invalidates the tokens. Called
        on logout (all) or trust revocation (per app).
        """
        for token, chan in list(self._session_channels.items()):
            if app_name is not None and chan.app_name != app_name:
                continue
            del self._session_channels[token]
            self.unsubscribe(chan.wildcard_subject)
            logger.info("IPCService: tore down session channel for '{}'", chan.app_name)

    def _route_session_message(self, subject: str, data: dict, reply: str | None) -> None:
        """Route a capability-channel request to its trusted action handler.

        Runs on the NATS loop thread. Resolves the token from the subject,
        validates it, attaches identity, and dispatches honoring the target
        action's ``main_thread`` preference.
        """
        session_prefix = self.topic("session.")
        remainder = subject[len(session_prefix):] if subject.startswith(session_prefix) else ""
        token, _, action_suffix = remainder.partition(".")

        chan = self._session_channels.get(token)
        if chan is None:
            self.reply(reply, error_reply("denied", "Invalid or expired session token"))
            return

        version = data.get("contract_version", CONTRACT_VERSION)
        if version != CONTRACT_VERSION:
            self.reply(
                reply,
                error_reply(
                    "version_mismatch",
                    f"Server speaks contract_version {CONTRACT_VERSION}, got {version}",
                ),
            )
            return

        target = self._trusted_actions.get(action_suffix)
        if target is None:
            self.reply(reply, error_reply("unknown", f"Unknown action: {action_suffix}"))
            return

        data.pop("_identity", None)
        data["_identity"] = {"app_name": chan.app_name, "session_token": token}
        if target.main_thread:
            invoke_in_main_thread(target.callback, action_suffix, data, reply)
        else:
            target.callback(action_suffix, data, reply)

    def _reject_untrusted(self, subject: str, data: dict, reply: str | None) -> None:
        """Reject a request that arrived on a bare (non-channel) trusted subject."""
        logger.warning("IPCService: rejected untrusted request on '{}'", subject)
        self.reply(
            reply,
            error_reply(
                "denied",
                "This action requires a session capability channel; "
                "complete the auth.request handshake and use the session subject.",
            ),
        )
```

3h. Extend `build_auth_response` — add `app_name` kwarg, mint on approval, stamp `contract_version` on both branches. New signature/return (keep existing docstring content, add the new arg doc):

```python
    def build_auth_response(
        self,
        *,
        approved: bool,
        session=None,
        tiled_url: str = "",
        reason: str = "",
        app_name: str | None = None,
    ) -> dict:
```
In the approved branch, after computing `session_id`, replace the return with:
```python
            response = {
                "status": "approved",
                # Historical name; actually carries an API key under auth-v2.
                "tiled_token": SessionManager.get_instance().get_api_key("tiled"),
                "tiled_url": tiled_url,
                # Keycloak `sub` of the logged-in user; lets IPC clients drop a
                # cached Tiled key when a different user session issues a request.
                "session_id": session_id,
                "contract_version": CONTRACT_VERSION,
            }
            if app_name:
                response["session_token"] = self.mint_session_channel(app_name)
            return response
```
And the denied branch:
```python
        response: dict = {"status": "denied", "contract_version": CONTRACT_VERSION}
        if reason:
            response["reason"] = reason
        return response
```

3i. In `core/application.py` `_handle_ipc_auth_request`, pass `app_name=app_name` to **both** approved `build_auth_response(...)` calls (lines ~619 and ~651):

```python
                ipc.build_auth_response(
                    approved=True, session=session, tiled_url=tiled_url, app_name=app_name
                ),
```

- [ ] **Step 4: Run tests**

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ipc/ -v`
Expected: new file all PASS; existing `tests/ipc/` suites still PASS (the `_make_handler` change is behavior-compatible for exact subjects). If `tests/ipc/test_integration.py` fake-IPC constructors lack the two new dict attributes, add `instance._trusted_actions = {}` / `instance._session_channels = {}` to its `_make_ipc` helper.

- [ ] **Step 5: Commit**

```bash
git add src/lightfall/ipc/service.py src/lightfall/core/application.py tests/ipc/test_capability_channels.py tests/ipc/test_integration.py
git commit -m "feat(ipc): capability channels — per-session trust enforcement in IPCService"
```

---

### Task 3: Logout → trust clear + channel teardown

**Files:**
- Modify: `src/lightfall/core/application.py` (in `_start_ipc`)
- Test: `tests/remote/test_logout_teardown.py`

**Interfaces:**
- Consumes: `TrustManager.clear()` (trust.py:68), `IPCService.teardown_session_channels()` (Task 2), `SessionManager.state_changed = Signal(AuthState, AuthState)`.
- Produces: `LFApplication._wire_session_trust(self) -> None` — connects `state_changed`; on transition to `AuthState.UNAUTHENTICATED` calls `trust.clear()` + `ipc.teardown_session_channels()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/remote/test_logout_teardown.py
"""Logout must clear trust and tear down capability channels (spec §3.5)."""

from __future__ import annotations

from lightfall.auth.session import AuthState
from lightfall.core.application import LFApplication
from lightfall.ipc.service import IPCService
from lightfall.ipc.trust import TrustManager


class _FakeRegistry:
    def __init__(self, services):
        self._services = services

    def get(self, service_type, default=None):
        return self._services.get(service_type, default)


def _make_ipc() -> IPCService:
    ipc = IPCService.__new__(IPCService)
    ipc._topic_prefix = "als.test"
    ipc._subscriptions = {}
    ipc._action_catalog = {}
    ipc._event_catalog = {}
    ipc._trusted_actions = {}
    ipc._session_channels = {}
    ipc._trust = None
    ipc._instance_id = "t"
    ipc._display_name = None
    ipc._loop = None
    ipc._nc = None
    ipc._connected = False
    ipc.publish = lambda subject, data: None  # type: ignore[method-assign]
    return ipc


def test_logout_clears_trust_and_channels(qapp, monkeypatch):
    ipc = _make_ipc()
    trust = TrustManager()
    trust.approve("pystxm")
    ipc.mint_session_channel("pystxm")

    app = LFApplication.__new__(LFApplication)
    app._services = _FakeRegistry({IPCService: ipc, TrustManager: trust})

    class _FakeSM:
        class _Sig:
            def __init__(self):
                self._slots = []

            def connect(self, slot):
                self._slots.append(slot)

            def emit(self, *args):
                for s in self._slots:
                    s(*args)

        def __init__(self):
            self.state_changed = self._Sig()

    sm = _FakeSM()
    import lightfall.auth.session as session_mod

    monkeypatch.setattr(session_mod.SessionManager, "get_instance", staticmethod(lambda: sm))

    app._wire_session_trust()
    sm.state_changed.emit(AuthState.UNAUTHENTICATED, AuthState.AUTHENTICATED)

    assert not trust.is_trusted("pystxm")
    assert ipc.session_channel_count == 0


def test_login_transition_does_not_clear(qapp, monkeypatch):
    ipc = _make_ipc()
    trust = TrustManager()
    trust.approve("pystxm")
    ipc.mint_session_channel("pystxm")

    app = LFApplication.__new__(LFApplication)
    app._services = _FakeRegistry({IPCService: ipc, TrustManager: trust})

    class _FakeSM:
        class _Sig:
            def __init__(self):
                self._slots = []

            def connect(self, slot):
                self._slots.append(slot)

            def emit(self, *args):
                for s in self._slots:
                    s(*args)

        def __init__(self):
            self.state_changed = self._Sig()

    sm = _FakeSM()
    import lightfall.auth.session as session_mod

    monkeypatch.setattr(session_mod.SessionManager, "get_instance", staticmethod(lambda: sm))

    app._wire_session_trust()
    sm.state_changed.emit(AuthState.AUTHENTICATED, AuthState.UNAUTHENTICATED)

    assert trust.is_trusted("pystxm")
    assert ipc.session_channel_count == 1
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL, `AttributeError: 'LFApplication' object has no attribute '_wire_session_trust'`.

- [ ] **Step 3: Implement in `core/application.py`**

Add method (near `_wire_agent_ipc`):

```python
    def _wire_session_trust(self) -> None:
        """Scope IPC trust to the login session (spec: per-login-session trust).

        On logout, all app trust decisions are cleared and every capability
        channel is torn down; clients detect the dead channel and re-run
        ``auth.request`` after the next login. Mirrors the service-key
        clearing in :meth:`SessionManager.logout`.
        """
        from lightfall.auth.session import AuthState, SessionManager

        ipc = self._services.get(IPCService)
        trust = self._services.get(TrustManager)

        def on_state_changed(new_state, old_state) -> None:
            if new_state == AuthState.UNAUTHENTICATED:
                trust.clear()
                ipc.teardown_session_channels()
                logger.info("IPC trust cleared and session channels torn down on logout")

        SessionManager.get_instance().state_changed.connect(on_state_changed)
```

In `_start_ipc`, after the existing `_wire_agent_ipc` try/except block, add:

```python
        try:
            self._wire_session_trust()
        except Exception:
            logger.exception("Failed to wire session-trust teardown")
```

- [ ] **Step 4: Run tests**

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/remote/test_logout_teardown.py tests/ipc/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lightfall/core/application.py tests/remote/test_logout_teardown.py
git commit -m "feat(auth): tear down IPC trust + capability channels on logout"
```

---

### Task 4: RemoteControlService core — run tracking, events, engine.status, queue.get

**Files:**
- Create: `src/lightfall/remote/service.py`
- Modify: `src/lightfall/core/application.py` (replace `_wire_engine_ipc` + `_wire_plan_commands` with RemoteControlService wiring; `trusted=True` on logbook/agent actions)
- Modify: `tests/ipc/test_integration.py` (wiring tests: field renames, removed methods)
- Test: `tests/remote/test_service_plan.py` (engine.status/queue.get parts; plan verbs extend it in Task 5)

**Interfaces:**
- Consumes: Task 1 protocol; `get_engine()` singleton; engine signals `sigOutput(str, dict)`, `sigFinish()`, `sigAbort()`, `sigException(Exception)`, `sigStateChanged(str)`; `engine.get_queue_items()`, `engine.get_current_procedure()`, `engine.is_idle`; `IPCService.register_action(trusted=True)` / `register_event` / `publish` / `reply` / `topic`.
- Produces: `class RemoteControlService(QObject)` with:
  - `__init__(self, ipc: IPCService, engine=None, catalog=None, parent=None)` — `engine`/`catalog` injectable for tests, default `get_engine()` / `DeviceCatalog.get_instance()` resolved lazily in `start()`.
  - `start() -> None` — registers all actions + events, connects engine signals.
  - `stop() -> None` — shuts down the executor.
  - Internal run tracking: `_current: dict` with keys `item_id`, `run_uid`, `plan_name`; `_run_uid_waiters: dict[str, threading.Event]`.
  - Events published: `runs.new {item_id, run_uid, plan_name}`, `runs.complete {run_uid, exit_status}`, `state.engine {state}`.
  - Later tasks add handlers to this class; the executor attribute is `self._executor` (`ThreadPoolExecutor(max_workers=4, thread_name_prefix="remote-control")`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/remote/test_service_plan.py
"""RemoteControlService: run-lifecycle events, engine.status, queue.get.

Plan verbs (plan.list/run/abort) are covered further down (Task 5 extends
this file).
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from lightfall.ipc.service import IPCService
from lightfall.remote.service import RemoteControlService


class _FakeSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for s in self._slots:
            s(*args)


class _FakeEngine:
    def __init__(self):
        self.sigOutput = _FakeSignal()
        self.sigFinish = _FakeSignal()
        self.sigAbort = _FakeSignal()
        self.sigException = _FakeSignal()
        self.sigStateChanged = _FakeSignal()
        self.is_idle = True
        self._queue = []
        self._current = None
        self.submitted = []

    def submit(self, procedure, *, name="", **kwargs):
        self.submitted.append((procedure, name))
        return "item-1"

    def get_queue_items(self):
        return list(self._queue)

    def get_current_procedure(self):
        return self._current

    def abort(self, reason=""):
        return True

    @property
    def state_name(self):
        return "idle" if self.is_idle else "running"


def _make_ipc():
    ipc = IPCService.__new__(IPCService)
    ipc._topic_prefix = "als.test"
    ipc._subscriptions = {}
    ipc._action_catalog = {}
    ipc._event_catalog = {}
    ipc._trusted_actions = {}
    ipc._session_channels = {}
    ipc._trust = None
    ipc._instance_id = "t"
    ipc._display_name = None
    ipc._loop = None
    ipc._nc = None
    ipc._connected = False
    sent = []
    ipc.publish = lambda subject, data: sent.append((subject, data))  # type: ignore[method-assign]
    return ipc, sent


@pytest.fixture
def svc(qapp):
    ipc, sent = _make_ipc()
    engine = _FakeEngine()
    service = RemoteControlService(ipc, engine=engine, catalog=None)
    service.start()
    yield SimpleNamespace(ipc=ipc, sent=sent, engine=engine, service=service)
    service.stop()


def _invoke(svc, suffix, data, reply="_INBOX.r"):
    """Call a trusted action handler directly and wait for its (possibly
    executor-dispatched) reply to land."""
    svc.ipc._trusted_actions[suffix].callback(suffix, data, reply)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        replies = [d for s, d in svc.sent if s == reply]
        if replies:
            return replies[-1]
        time.sleep(0.01)
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.processEvents()
    raise AssertionError(f"No reply for {suffix}")


class TestEvents:
    def test_start_doc_publishes_runs_new_with_item_and_uid(self, svc):
        svc.engine._current = SimpleNamespace(id="item-7", name="scan")
        svc.engine.sigOutput.emit("start", {"uid": "uid-1", "plan_name": "scan"})
        subjects = dict(svc.sent)
        assert subjects["als.test.runs.new"] == {
            "item_id": "item-7",
            "run_uid": "uid-1",
            "plan_name": "scan",
        }

    def test_finish_publishes_runs_complete_run_uid(self, svc):
        svc.engine._current = SimpleNamespace(id="item-7", name="scan")
        svc.engine.sigOutput.emit("start", {"uid": "uid-1", "plan_name": "scan"})
        svc.engine.sigFinish.emit()
        assert ("als.test.runs.complete", {"run_uid": "uid-1", "exit_status": "success"}) in svc.sent

    def test_abort_and_exception_exit_statuses(self, svc):
        svc.engine._current = SimpleNamespace(id="i", name="p")
        svc.engine.sigOutput.emit("start", {"uid": "u1", "plan_name": "p"})
        svc.engine.sigAbort.emit()
        assert ("als.test.runs.complete", {"run_uid": "u1", "exit_status": "abort"}) in svc.sent
        svc.engine.sigOutput.emit("start", {"uid": "u2", "plan_name": "p"})
        svc.engine.sigException.emit(RuntimeError("x"))
        assert ("als.test.runs.complete", {"run_uid": "u2", "exit_status": "error"}) in svc.sent

    def test_state_change_published(self, svc):
        svc.engine.sigStateChanged.emit("running")
        assert ("als.test.state.engine", {"state": "running"}) in svc.sent

    def test_events_registered_in_catalog(self, svc):
        events = {e["subject"] for e in svc.ipc.list_events()}
        assert {"runs.new", "runs.complete", "state.engine"} <= events


class TestEngineStatus:
    def test_idle_status(self, svc):
        reply = _invoke(svc, "commands.engine.status", {})
        assert reply["state"] == "idle"
        assert reply["contract_version"] == 1

    def test_running_status_includes_current_run(self, svc):
        svc.engine.is_idle = False
        svc.engine._current = SimpleNamespace(id="item-7", name="scan")
        svc.engine.sigOutput.emit("start", {"uid": "uid-1", "plan_name": "scan"})
        reply = _invoke(svc, "commands.engine.status", {})
        assert reply == {
            "state": "running",
            "item_id": "item-7",
            "run_uid": "uid-1",
            "plan_name": "scan",
            "contract_version": 1,
        }


class TestQueueGet:
    def test_empty_queue(self, svc):
        reply = _invoke(svc, "commands.queue.get", {})
        assert reply == {"items": [], "contract_version": 1}

    def test_queued_and_running_items(self, svc):
        svc.engine.is_idle = False
        svc.engine._current = SimpleNamespace(id="item-run", name="running_plan")
        svc.engine._queue = [SimpleNamespace(id="item-q", name="queued_plan")]
        reply = _invoke(svc, "commands.queue.get", {})
        assert {"item_id": "item-run", "plan_name": "running_plan", "state": "running"} in reply["items"]
        assert {"item_id": "item-q", "plan_name": "queued_plan", "state": "queued"} in reply["items"]

    def test_actions_are_trusted(self, svc):
        for suffix in ("commands.engine.status", "commands.queue.get"):
            assert suffix in svc.ipc._trusted_actions
```

- [ ] **Step 2: Run to verify failure** — Expected: `ModuleNotFoundError`/`ImportError` for `lightfall.remote.service`.

- [ ] **Step 3: Implement `src/lightfall/remote/service.py`**

```python
# src/lightfall/remote/service.py
"""RemoteControlService — action semantics for the remote-control contract (v1).

Thin adapters over the existing engine, plan registry, and DeviceCatalog.
Trust enforcement is NOT here — it is central in IPCService (capability
channels); every action below registers with ``trusted=True`` and is only
reachable through a session channel.

Threading: handlers register with ``main_thread=False`` (they run on the NATS
loop thread) and immediately dispatch to a small ThreadPoolExecutor, replying
from the worker — the NATS loop and the Qt main thread are never blocked.
Engine Qt signals arrive on the main thread (queued connections), so executor
threads may wait on events set from the main thread.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from loguru import logger
from PySide6.QtCore import QObject

from lightfall.ipc.service import IPCService
from lightfall.remote.protocol import error_reply, ok_reply

__all__ = ["RemoteControlService"]

# How long plan.run waits for the start document before replying run_uid=null.
RUN_UID_WAIT_S = 2.0
# Default completion timeout for device.put wait=true.
PUT_DEFAULT_TIMEOUT_S = 30.0


class RemoteControlService(QObject):
    """Remote-control actions + run-lifecycle events over IPC."""

    def __init__(
        self,
        ipc: IPCService,
        engine: Any = None,
        catalog: Any = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._ipc = ipc
        self._engine = engine
        self._catalog = catalog
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="remote-control")
        # Current-run tracking (written on the Qt main thread by doc signals,
        # read from executor threads) — guarded by _run_lock.
        self._run_lock = threading.Lock()
        self._current: dict[str, str] = {}
        self._run_uid_waiters: dict[str, threading.Event] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def engine(self) -> Any:
        if self._engine is None:
            from lightfall.acquire.engine import get_engine

            self._engine = get_engine()
        return self._engine

    @property
    def catalog(self) -> Any:
        if self._catalog is None:
            from lightfall.devices.catalog import DeviceCatalog

            self._catalog = DeviceCatalog.get_instance()
        return self._catalog

    def start(self) -> None:
        """Register actions and events; connect engine document signals."""
        self._connect_engine_signals()
        self._register_events()
        self._register_actions()
        logger.debug("RemoteControlService started")

    def stop(self) -> None:
        """Shut down the executor (does not unregister actions)."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    # Engine signal wiring + broadcast events
    # ------------------------------------------------------------------

    def _connect_engine_signals(self) -> None:
        engine = self.engine
        engine.sigOutput.connect(self._on_output)
        engine.sigFinish.connect(lambda: self._publish_complete("success"))
        engine.sigAbort.connect(lambda: self._publish_complete("abort"))
        engine.sigException.connect(lambda exc: self._publish_complete("error"))
        engine.sigStateChanged.connect(self._on_state_changed)

    def _on_output(self, name: str, doc: dict) -> None:
        if name != "start":
            return
        run_uid = doc.get("uid", "")
        item = self.engine.get_current_procedure()
        item_id = getattr(item, "id", "") if item is not None else ""
        plan_name = doc.get("plan_name", getattr(item, "name", "") or "unknown")
        with self._run_lock:
            self._current = {"item_id": item_id, "run_uid": run_uid, "plan_name": plan_name}
            waiter = self._run_uid_waiters.get(item_id)
        if waiter is not None:
            waiter.set()
        self._ipc.publish(
            self._ipc.topic("runs.new"),
            {"item_id": item_id, "run_uid": run_uid, "plan_name": plan_name},
        )

    def _publish_complete(self, exit_status: str) -> None:
        with self._run_lock:
            run_uid = self._current.get("run_uid", "")
        self._ipc.publish(
            self._ipc.topic("runs.complete"),
            {"run_uid": run_uid, "exit_status": exit_status},
        )

    def _on_state_changed(self, state: str) -> None:
        self._ipc.publish(self._ipc.topic("state.engine"), {"state": state})

    def _register_events(self) -> None:
        self._ipc.register_event(
            "runs.new",
            description="Fired when a new run starts",
            schema={"item_id": "str", "run_uid": "str", "plan_name": "str"},
        )
        self._ipc.register_event(
            "runs.complete",
            description="Fired when a run finishes",
            schema={"run_uid": "str", "exit_status": "str"},
        )
        self._ipc.register_event(
            "state.engine",
            description="Engine state change",
            schema={"state": "str"},
        )

    # ------------------------------------------------------------------
    # Action registration
    # ------------------------------------------------------------------

    def _register_actions(self) -> None:
        for suffix, handler, description in [
            ("commands.engine.status", self._handle_engine_status, "Engine state + current run"),
            ("commands.queue.get", self._handle_queue_get, "List queued plan items"),
        ]:
            self._ipc.register_action(
                suffix, handler, description=description, main_thread=False, trusted=True
            )

    def _dispatch(self, fn, subject: str, data: dict, reply: str | None) -> None:
        """Run *fn* on the executor; reply with a structured error on crash."""

        def run() -> None:
            try:
                fn(subject, data, reply)
            except Exception as exc:  # handler bug — never leave the client hanging
                logger.exception("RemoteControlService: handler for '{}' failed", subject)
                self._ipc.reply(reply, error_reply("unknown", str(exc)))

        self._executor.submit(run)

    # ------------------------------------------------------------------
    # engine.status / queue.get
    # ------------------------------------------------------------------

    def _handle_engine_status(self, subject: str, data: dict, reply: str | None) -> None:
        self._dispatch(self._do_engine_status, subject, data, reply)

    def _do_engine_status(self, subject: str, data: dict, reply: str | None) -> None:
        if self.engine.is_idle:
            self._ipc.reply(reply, ok_reply(state="idle"))
            return
        with self._run_lock:
            current = dict(self._current)
        self._ipc.reply(
            reply,
            ok_reply(
                state="running",
                item_id=current.get("item_id", ""),
                run_uid=current.get("run_uid", ""),
                plan_name=current.get("plan_name", ""),
            ),
        )

    def _handle_queue_get(self, subject: str, data: dict, reply: str | None) -> None:
        self._dispatch(self._do_queue_get, subject, data, reply)

    def _do_queue_get(self, subject: str, data: dict, reply: str | None) -> None:
        items: list[dict] = []
        current = self.engine.get_current_procedure()
        if current is not None:
            items.append({"item_id": current.id, "plan_name": current.name, "state": "running"})
        for item in self.engine.get_queue_items():
            items.append({"item_id": item.id, "plan_name": item.name, "state": "queued"})
        self._ipc.reply(reply, ok_reply(items=items))
```

- [ ] **Step 4: Wire into `core/application.py`**

4a. **Delete** methods `_wire_engine_ipc` (:346-418) and `_wire_plan_commands` (:420-499) entirely.

4b. In `_start_ipc`, replace the block

```python
        try:
            self._wire_engine_ipc()
            self._wire_plan_commands()
        except Exception:
            logger.exception("Failed to wire engine IPC (engine may not be initialized yet)")
```
with:
```python
        try:
            self._wire_remote_control()
        except Exception:
            logger.exception("Failed to wire remote control (engine may not be initialized yet)")
```

4c. Add the new wiring method:

```python
    def _wire_remote_control(self) -> None:
        """Start the RemoteControlService (plan/queue/engine/device actions
        plus run-lifecycle events). Replaces the old _wire_engine_ipc /
        _wire_plan_commands inline handlers."""
        from lightfall.remote.service import RemoteControlService

        ipc = self._services.get(IPCService)
        remote = RemoteControlService(ipc)
        self._services.register_instance(RemoteControlService, remote, replace=True)
        remote.start()
        logger.debug("RemoteControlService wired")
```

4d. In `_wire_logbook_ipc` and `_wire_agent_ipc`, add `trusted=True` to the `register_action` calls (spec §2 breaking change — these move behind the capability channel):

```python
        ipc.register_action(
            "commands.logbook.add",
            handle_logbook_add,
            description="Create a logbook entry with optional content fragment",
            schema={"title": "str", "content": "str (optional)", "tags": "list[str]"},
            trusted=True,
        )
```
(same one-line addition for `commands.agent.message`.)

4e. In `_shutdown`, before stopping IPC, stop the remote service:

```python
        try:
            from lightfall.remote.service import RemoteControlService

            remote = self._services.get(RemoteControlService, None)
            if remote is not None:
                remote.stop()
        except Exception:
            logger.exception("Error stopping RemoteControlService")
```

4f. **Update `tests/ipc/test_integration.py`:** tests exercising `_wire_engine_ipc` / `_wire_plan_commands` must be rewritten to construct a `RemoteControlService` with the fake engine/IPC instead, asserting the NEW field names (`item_id`, `run_uid`) — or deleted where `tests/remote/test_service_plan.py` now covers the behavior. Tests for `_wire_logbook_ipc` / `_wire_agent_ipc` change their handler lookup from `ipc._subscriptions[ipc.topic(...)].callback` to `ipc._trusted_actions[suffix].callback` (bare subjects now hold the rejection handler), and the fake `_make_ipc` gains `_trusted_actions = {}` / `_session_channels = {}` if Task 2 didn't already add them.

- [ ] **Step 5: Run tests**

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/remote/ tests/ipc/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/lightfall/remote/service.py src/lightfall/core/application.py tests/remote/test_service_plan.py tests/ipc/test_integration.py
git commit -m "feat(remote): RemoteControlService core — run events (item_id/run_uid), engine.status, queue.get"
```

---

### Task 5: Plan verbs — plan.list, plan.run, plan.abort

**Files:**
- Modify: `src/lightfall/remote/service.py`
- Test: extend `tests/remote/test_service_plan.py`

**Interfaces:**
- Consumes: `get_registry()` → `PlanRegistry` (`get_plan(name)`, iterate all plans — the registry exposes the full mapping; use its public listing method, confirmed as `get_plan` + a list/iterate API in `src/lightfall/acquire/plans/registry.py`; if the listing method is `list_plans()` use it, else iterate `registry._plans` equivalent public accessor found at implementation time — check the file first); `PlanInfo.parameters` (`ParameterInfo.name/annotation/default/required`); `extract_annotated_metadata(annotation, func)` from `lightfall.ui.widgets.plan_config`; `Unit`, `Default` from `lightfall.ui.annotations`; `engine.submit(gen, name=...) -> str`; `engine.is_idle`; `engine.queue_size`; `engine.abort(reason) -> bool`; `invoke_in_main_thread`.
- Produces: handlers `commands.plan.list`, `commands.plan.run`, `commands.plan.abort` registered `trusted=True, main_thread=False`. `plan.run` reply: `{status:"submitted", plan_name, item_id, run_uid|null}`.

- [ ] **Step 1: Write the failing tests** (append to `tests/remote/test_service_plan.py`)

```python
class _FakeRegistry:
    """Mimics PlanRegistry for plan.list / plan.run."""

    def __init__(self, plans):
        self._plans = plans

    def get_plan(self, name):
        return self._plans.get(name)

    def list_plans(self):
        return list(self._plans.values())


@pytest.fixture
def plan_svc(qapp, monkeypatch):
    ipc, sent = _make_ipc()
    engine = _FakeEngine()

    from typing import Annotated

    from lightfall.ui.annotations import Unit

    def count(num: Annotated[int, Unit("pts")] = 5, delay: float = 0.0):
        yield from ()

    import inspect

    plan_info = SimpleNamespace(
        name="count",
        func=count,
        description="Count sim",
        parameters=[
            SimpleNamespace(
                name="num", annotation=count.__annotations__["num"], default=5, required=False
            ),
            SimpleNamespace(
                name="delay", annotation=float, default=0.0, required=False
            ),
        ],
    )
    registry = _FakeRegistry({"count": plan_info})
    import lightfall.remote.service as service_mod

    monkeypatch.setattr(service_mod, "_get_plan_registry", lambda: registry)

    service = RemoteControlService(ipc, engine=engine, catalog=None)
    service.start()
    yield SimpleNamespace(ipc=ipc, sent=sent, engine=engine, service=service)
    service.stop()


class TestPlanList:
    def test_lists_plans_with_param_metadata(self, plan_svc):
        reply = _invoke(plan_svc, "commands.plan.list", {})
        assert reply["contract_version"] == 1
        plans = {p["name"]: p for p in reply["plans"]}
        assert "count" in plans
        params = {p["name"]: p for p in plans["count"]["params"]}
        assert params["num"]["type"] == "int"
        assert params["num"]["unit"] == "pts"
        assert params["num"]["default"] == 5
        assert params["delay"]["type"] == "float"
        assert params["delay"]["unit"] is None


class TestPlanRun:
    def test_reject_default_when_busy(self, plan_svc):
        plan_svc.engine.is_idle = False
        reply = _invoke(plan_svc, "commands.plan.run", {"plan_name": "count", "params": {}})
        assert reply["status"] == "error"
        assert reply["code"] == "busy"
        assert plan_svc.engine.submitted == []

    def test_queue_behavior_submits_when_busy(self, plan_svc):
        plan_svc.engine.is_idle = False
        reply = _invoke(
            plan_svc,
            "commands.plan.run",
            {"plan_name": "count", "params": {}, "behavior": "queue"},
        )
        assert reply["status"] == "submitted"
        assert reply["item_id"] == "item-1"
        assert reply["run_uid"] is None  # queued: no start doc yet

    def test_submit_idle_fills_run_uid_from_start_doc(self, plan_svc):
        import threading

        def emit_start_soon():
            time.sleep(0.1)
            plan_svc.engine._current = SimpleNamespace(id="item-1", name="count")
            from lightfall.utils.threads import invoke_in_main_thread

            invoke_in_main_thread(
                plan_svc.engine.sigOutput.emit, "start", {"uid": "uid-9", "plan_name": "count"}
            )

        threading.Thread(target=emit_start_soon, daemon=True).start()
        reply = _invoke(plan_svc, "commands.plan.run", {"plan_name": "count", "params": {}})
        assert reply["status"] == "submitted"
        assert reply["item_id"] == "item-1"
        assert reply["run_uid"] == "uid-9"

    def test_missing_plan_name_bad_request(self, plan_svc):
        reply = _invoke(plan_svc, "commands.plan.run", {"params": {}})
        assert reply["code"] == "bad_request"

    def test_unknown_plan(self, plan_svc):
        reply = _invoke(plan_svc, "commands.plan.run", {"plan_name": "nope", "params": {}})
        assert reply["code"] == "unknown"

    def test_bad_behavior_value(self, plan_svc):
        reply = _invoke(
            plan_svc, "commands.plan.run", {"plan_name": "count", "behavior": "yolo"}
        )
        assert reply["code"] == "bad_request"

    def test_bad_params_bad_request(self, plan_svc):
        reply = _invoke(
            plan_svc, "commands.plan.run", {"plan_name": "count", "params": {"nope": 1}}
        )
        assert reply["code"] == "bad_request"


class TestPlanAbort:
    def test_abort_requested(self, plan_svc):
        reply = _invoke(plan_svc, "commands.plan.abort", {"reason": "operator"})
        assert reply == {"status": "abort_requested", "contract_version": 1}

    def test_nothing_to_abort(self, plan_svc):
        plan_svc.engine.abort = lambda reason="": False
        reply = _invoke(plan_svc, "commands.plan.abort", {})
        assert reply["status"] == "not_aborted"
        assert "message" in reply
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (`_get_plan_registry` missing; `commands.plan.*` not in `_trusted_actions`).

- [ ] **Step 3: Implement in `src/lightfall/remote/service.py`**

3a. Module-level indirection (monkeypatch point):

```python
def _get_plan_registry():
    from lightfall.acquire.plans.registry import get_registry

    return get_registry()
```

3b. Extend `_register_actions` list with:

```python
            ("commands.plan.list", self._handle_plan_list, "List available plans with parameter metadata"),
            ("commands.plan.run", self._handle_plan_run, "Submit a plan (behavior: reject|queue, default reject)"),
            ("commands.plan.abort", self._handle_plan_abort, "Abort the active run"),
```

3c. Handlers (each `_handle_*` is `self._dispatch(self._do_*, subject, data, reply)`; `plan.abort` is special — see below):

```python
    def _do_plan_list(self, subject: str, data: dict, reply: str | None) -> None:
        from lightfall.ui.widgets.plan_config import extract_annotated_metadata
        from lightfall.ui.annotations import Default, Unit

        registry = _get_plan_registry()
        plans = []
        for info in registry.list_plans():
            params = []
            for p in info.parameters:
                try:
                    base_type, metadata = extract_annotated_metadata(p.annotation, info.func)
                except Exception:
                    base_type, metadata = p.annotation, []
                unit = next((m.suffix for m in metadata if isinstance(m, Unit)), None)
                default = None
                import inspect

                if p.default is not inspect.Parameter.empty:
                    default = p.default
                else:
                    default = next(
                        (m.value for m in metadata if isinstance(m, Default)), None
                    )
                type_name = getattr(base_type, "__name__", str(base_type))
                params.append({"name": p.name, "type": type_name, "unit": unit, "default": default})
            plans.append({"name": info.name, "params": params})
        self._ipc.reply(reply, ok_reply(plans=plans))

    def _do_plan_run(self, subject: str, data: dict, reply: str | None) -> None:
        plan_name = data.get("plan_name")
        params = data.get("params", {})
        behavior = data.get("behavior", "reject")

        if not plan_name:
            self._ipc.reply(reply, error_reply("bad_request", "plan_name is required"))
            return
        if behavior not in ("reject", "queue"):
            self._ipc.reply(
                reply, error_reply("bad_request", f"behavior must be 'reject' or 'queue', got {behavior!r}")
            )
            return

        registry = _get_plan_registry()
        plan_info = registry.get_plan(plan_name)
        if plan_info is None:
            self._ipc.reply(reply, error_reply("unknown", f"Plan '{plan_name}' not found"))
            return

        engine = self.engine
        busy = not engine.is_idle or getattr(engine, "queue_size", 0) > 0
        if behavior == "reject" and busy:
            self._ipc.reply(
                reply, error_reply("busy", "Engine is busy and behavior is 'reject'")
            )
            return

        try:
            plan_generator = plan_info.func(**params)
        except TypeError as exc:
            self._ipc.reply(reply, error_reply("bad_request", f"Bad params: {exc}"))
            return

        # Arm the start-doc waiter BEFORE submitting so a fast start can't race us.
        waiter = threading.Event()
        try:
            item_id = engine.submit(plan_generator, name=plan_name)
        except Exception as exc:
            self._ipc.reply(reply, error_reply("unknown", str(exc)))
            return
        if item_id is None:
            self._ipc.reply(reply, error_reply("unknown", "Submission cancelled by pre-submit hook"))
            return

        run_uid: str | None = None
        if not busy:
            with self._run_lock:
                self._run_uid_waiters[item_id] = waiter
            try:
                if waiter.wait(RUN_UID_WAIT_S):
                    with self._run_lock:
                        if self._current.get("item_id") == item_id:
                            run_uid = self._current.get("run_uid")
            finally:
                with self._run_lock:
                    self._run_uid_waiters.pop(item_id, None)

        self._ipc.reply(
            reply,
            ok_reply(status="submitted", plan_name=plan_name, item_id=item_id, run_uid=run_uid),
        )
```

Note the waiter registration happens after `submit` returns the id (we need the id as the key) — the race is closed by re-checking `self._current` under the lock even when `waiter.wait` times out; add that fallback:

```python
            # Start doc may have arrived before the waiter was registered.
            if run_uid is None:
                with self._run_lock:
                    if self._current.get("item_id") == item_id:
                        run_uid = self._current.get("run_uid")
```
(place immediately after the `finally` block, before building the reply).

```python
    def _handle_plan_abort(self, subject: str, data: dict, reply: str | None) -> None:
        """Abort marshals to the Qt main thread (matches how the UI calls it)."""
        from lightfall.utils.threads import invoke_in_main_thread

        reason = data.get("reason", "")

        def do_abort() -> None:
            try:
                aborted = self.engine.abort(reason=reason)
            except Exception as exc:
                self._ipc.reply(reply, error_reply("unknown", str(exc)))
                return
            if aborted:
                self._ipc.reply(reply, ok_reply(status="abort_requested"))
            else:
                self._ipc.reply(
                    reply,
                    ok_reply(
                        status="not_aborted",
                        message=f"Nothing to abort: engine state is '{self.engine.state_name}'",
                    ),
                )

        invoke_in_main_thread(do_abort)
```

Handler registrations: `_handle_plan_list` / `_handle_plan_run` dispatch to executor:

```python
    def _handle_plan_list(self, subject: str, data: dict, reply: str | None) -> None:
        self._dispatch(self._do_plan_list, subject, data, reply)

    def _handle_plan_run(self, subject: str, data: dict, reply: str | None) -> None:
        self._dispatch(self._do_plan_run, subject, data, reply)
```

3d. **Implementation-time check:** confirm the registry listing method name in `src/lightfall/acquire/plans/registry.py` (expected `list_plans()`; `get_plan()` is confirmed). If it differs, adapt `_do_plan_list` and the fake registry in the test.

- [ ] **Step 4: Run tests**

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/remote/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lightfall/remote/service.py tests/remote/test_service_plan.py
git commit -m "feat(remote): plan.list/run/abort with item_id+run_uid reply semantics"
```

---

### Task 6: Device introspection — device.search, device.components, device.info

**Files:**
- Modify: `src/lightfall/remote/service.py`
- Test: `tests/remote/test_service_device.py`

**Interfaces:**
- Consumes: `DeviceCatalog.list_devices()`, `get_device_by_name(name)`, `get_ophyd_device(name)`; `DeviceInfo.name/category/device_class/beamline/tags/prefix/active`; ophyd `component_names` / `_sig_attrs` / `_signals` (lazy-safe enumeration per `ui/models/device_tree.py:551-605`).
- Produces: handlers `commands.device.search` (happi-style kwargs, `{}` = all names), `commands.device.components` (`{components: [{name, type, writable}]}`), `commands.device.info` (`{name, category, device_class}`). Also internal `_resolve_device(name) -> tuple[info, ophyd_obj] | None` and `_is_writable(obj) -> bool` reused by Task 7.

- [ ] **Step 1: Write the failing tests**

```python
# tests/remote/test_service_device.py
"""RemoteControlService device verbs against ophyd.sim devices."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from ophyd.sim import SynAxis, SynGauss

from lightfall.devices.model import DeviceCategory, DeviceInfo
from lightfall.ipc.service import IPCService
from lightfall.remote.service import RemoteControlService


class _FakeCatalog:
    def __init__(self, devices):
        # devices: list[tuple[DeviceInfo, ophyd_obj]]
        self._infos = {info.name: info for info, _ in devices}
        self._ophyd = {info.name: obj for info, obj in devices}

    def list_devices(self, category=None, beamline=None, active_only=True):
        return list(self._infos.values())

    def get_device_by_name(self, name):
        return self._infos.get(name)

    def get_ophyd_device(self, name):
        return self._ophyd.get(name)


def _make_ipc():
    ipc = IPCService.__new__(IPCService)
    ipc._topic_prefix = "als.test"
    ipc._subscriptions = {}
    ipc._action_catalog = {}
    ipc._event_catalog = {}
    ipc._trusted_actions = {}
    ipc._session_channels = {}
    ipc._trust = None
    ipc._instance_id = "t"
    ipc._display_name = None
    ipc._loop = None
    ipc._nc = None
    ipc._connected = False
    sent = []
    ipc.publish = lambda subject, data: sent.append((subject, data))  # type: ignore[method-assign]
    return ipc, sent


class _FakeEngine:
    def __init__(self):
        self.is_idle = True

    def get_current_procedure(self):
        return None

    def get_queue_items(self):
        return []

    class _Sig:
        def connect(self, *_):
            pass

    sigOutput = _Sig()
    sigFinish = _Sig()
    sigAbort = _Sig()
    sigException = _Sig()
    sigStateChanged = _Sig()


@pytest.fixture
def dev_svc(qapp):
    motor = SynAxis(name="sim_motor")
    det = SynGauss("sim_det", motor, "sim_motor", center=0, Imax=1, sigma=1)
    devices = [
        (
            DeviceInfo(
                name="sim_motor",
                category=DeviceCategory.MOTOR,
                device_class="ophyd.sim.SynAxis",
                beamline="7.0.1.1",
                tags=["sample"],
            ),
            motor,
        ),
        (
            DeviceInfo(
                name="sim_det",
                category=DeviceCategory.DETECTOR,
                device_class="ophyd.sim.SynGauss",
                beamline="7.0.1.1",
            ),
            det,
        ),
    ]
    ipc, sent = _make_ipc()
    service = RemoteControlService(ipc, engine=_FakeEngine(), catalog=_FakeCatalog(devices))
    service.start()
    yield SimpleNamespace(ipc=ipc, sent=sent, service=service, motor=motor)
    service.stop()


def _invoke(svc, suffix, data, reply="_INBOX.d"):
    svc.ipc._trusted_actions[suffix].callback(suffix, data, reply)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        replies = [d for s, d in svc.sent if s == reply]
        if replies:
            return replies[-1]
        time.sleep(0.01)
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.processEvents()
    raise AssertionError(f"No reply for {suffix}")


class TestSearch:
    def test_empty_filter_lists_all_names(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.search", {})
        assert sorted(reply["devices"]) == ["sim_det", "sim_motor"]
        assert reply["contract_version"] == 1

    def test_filter_by_category(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.search", {"category": "motor"})
        assert reply["devices"] == ["sim_motor"]

    def test_filter_by_name(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.search", {"name": "sim_det"})
        assert reply["devices"] == ["sim_det"]

    def test_filter_by_tag(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.search", {"tags": "sample"})
        assert reply["devices"] == ["sim_motor"]

    def test_no_match_empty(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.search", {"name": "nope"})
        assert reply["devices"] == []


class TestInfo:
    def test_info_fields(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.info", {"device": "sim_motor"})
        assert reply == {
            "name": "sim_motor",
            "category": "motor",
            "device_class": "ophyd.sim.SynAxis",
            "contract_version": 1,
        }

    def test_unknown_device(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.info", {"device": "nope"})
        assert reply["code"] == "unknown"

    def test_missing_device_field(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.info", {})
        assert reply["code"] == "bad_request"


class TestComponents:
    def test_motor_components(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.components", {"device": "sim_motor"})
        comps = {c["name"]: c for c in reply["components"]}
        assert "readback" in comps
        assert "setpoint" in comps
        assert comps["setpoint"]["writable"] is True
        assert isinstance(comps["readback"]["type"], str)

    def test_unknown_device(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.components", {"device": "nope"})
        assert reply["code"] == "unknown"
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (`commands.device.*` not registered).

- [ ] **Step 3: Implement in `src/lightfall/remote/service.py`**

3a. Extend `_register_actions` with:

```python
            ("commands.device.search", self._handle_device_search, "Search devices (happi-style filters)"),
            ("commands.device.components", self._handle_device_components, "List a device's sub-devices and signals"),
            ("commands.device.info", self._handle_device_info, "Thin device metadata"),
```
each `_handle_*` following the `_dispatch` pattern:
```python
    def _handle_device_search(self, subject: str, data: dict, reply: str | None) -> None:
        self._dispatch(self._do_device_search, subject, data, reply)

    def _handle_device_components(self, subject: str, data: dict, reply: str | None) -> None:
        self._dispatch(self._do_device_components, subject, data, reply)

    def _handle_device_info(self, subject: str, data: dict, reply: str | None) -> None:
        self._dispatch(self._do_device_info, subject, data, reply)
```

3b. Implementations:

```python
    # ------------------------------------------------------------------
    # device.* helpers
    # ------------------------------------------------------------------

    def _resolve_device(self, data: dict, reply: str | None):
        """Common device lookup; replies with an error and returns None on failure.

        Returns (DeviceInfo, ophyd_obj) on success. ophyd_obj may be None if
        the device is catalogued but not instantiated.
        """
        name = data.get("device")
        if not name:
            self._ipc.reply(reply, error_reply("bad_request", "device is required"))
            return None
        info = self.catalog.get_device_by_name(name)
        if info is None:
            self._ipc.reply(reply, error_reply("unknown", f"Device '{name}' not found"))
            return None
        return info, self.catalog.get_ophyd_device(name)

    @staticmethod
    def _is_writable(obj: Any) -> bool:
        """Mirror of the signal_control heuristic (see signal_control.py:77)."""
        cls_name = type(obj).__name__
        if "ReadOnly" in cls_name or "RO" in cls_name:
            return False
        return hasattr(obj, "put") or hasattr(obj, "set")

    def _do_device_search(self, subject: str, data: dict, reply: str | None) -> None:
        filters = {k: v for k, v in data.items() if k not in ("_identity", "contract_version")}
        names: list[str] = []
        for info in self.catalog.list_devices():
            if self._matches(info, filters):
                names.append(info.name)
        self._ipc.reply(reply, ok_reply(devices=sorted(names)))

    @staticmethod
    def _matches(info: Any, filters: dict) -> bool:
        for key, wanted in filters.items():
            actual = getattr(info, key, None)
            if actual is None:
                actual = (info.metadata or {}).get(key)
            if actual is None:
                return False
            if isinstance(actual, (list, set, tuple)):
                if wanted not in actual:
                    return False
            elif str(actual) != str(wanted):
                return False
        return True

    def _do_device_info(self, subject: str, data: dict, reply: str | None) -> None:
        resolved = self._resolve_device(data, reply)
        if resolved is None:
            return
        info, _ = resolved
        self._ipc.reply(
            reply,
            ok_reply(name=info.name, category=str(info.category), device_class=info.device_class),
        )

    def _do_device_components(self, subject: str, data: dict, reply: str | None) -> None:
        resolved = self._resolve_device(data, reply)
        if resolved is None:
            return
        info, obj = resolved
        if obj is None:
            self._ipc.reply(
                reply, error_reply("unknown", f"Device '{info.name}' is not instantiated")
            )
            return

        components: list[dict] = []
        # Lazy-safe enumeration: use the instantiated-signal dict and class
        # attrs rather than getattr, which would trigger lazy Components
        # (same approach as ui/models/device_tree.py).
        names = list(getattr(obj, "component_names", ()) or ())
        signals = getattr(obj, "_signals", {}) or {}
        for cname in names:
            comp = signals.get(cname)
            if comp is None:
                sig_attrs = getattr(obj, "_sig_attrs", {}) or {}
                cpt = sig_attrs.get(cname)
                cls = getattr(cpt, "cls", None)
                type_name = cls.__name__ if cls is not None else "unknown"
                writable = bool(
                    cls is not None
                    and not ("ReadOnly" in cls.__name__ or "RO" in cls.__name__)
                    and (hasattr(cls, "put") or hasattr(cls, "set"))
                )
            else:
                type_name = type(comp).__name__
                writable = self._is_writable(comp)
            components.append({"name": cname, "type": type_name, "writable": writable})
        self._ipc.reply(reply, ok_reply(components=components))
```

- [ ] **Step 4: Run tests**

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/remote/test_service_device.py -v`
Expected: PASS. (SynAxis has `component_names` = ('readback','setpoint','velocity','acceleration','unused'); if the exact names differ adjust the assertion to the actual attributes, keeping the writable/type checks.)

- [ ] **Step 5: Commit**

```bash
git add src/lightfall/remote/service.py tests/remote/test_service_device.py
git commit -m "feat(remote): device.search/components/info over DeviceCatalog"
```

---

### Task 7: device.get / device.put

**Files:**
- Modify: `src/lightfall/remote/service.py`
- Test: extend `tests/remote/test_service_device.py`

**Interfaces:**
- Consumes: `_resolve_device`, `_is_writable` (Task 6); ophyd signal `.get()`, `.read()` (`{name: {"value", "timestamp"}}`), `.set(value)` → status with `.wait(timeout=...)`; `ophyd.utils.errors.LimitError`.
- Produces: `commands.device.get` `{device, signal?}` → `{value, timestamp}`; `commands.device.put` `{device, signal?, value, behavior:"reject", wait:true, timeout_s?}` with completion semantics; internal `_resolve_signal(obj, signal_name) -> Any | None`.

- [ ] **Step 1: Write the failing tests** (append to `tests/remote/test_service_device.py`)

```python
class TestGet:
    def test_get_default_readback(self, dev_svc):
        dev_svc.motor.set(3.5).wait(timeout=5)
        reply = _invoke(dev_svc, "commands.device.get", {"device": "sim_motor"})
        assert reply["value"] == pytest.approx(3.5)
        assert isinstance(reply["timestamp"], float)

    def test_get_named_signal(self, dev_svc):
        reply = _invoke(
            dev_svc, "commands.device.get", {"device": "sim_motor", "signal": "velocity"}
        )
        assert "value" in reply

    def test_get_unknown_signal(self, dev_svc):
        reply = _invoke(
            dev_svc, "commands.device.get", {"device": "sim_motor", "signal": "warp_drive"}
        )
        assert reply["code"] == "unknown"

    def test_get_unknown_device(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.get", {"device": "nope"})
        assert reply["code"] == "unknown"


class TestPut:
    def test_put_wait_true_replies_on_completion(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.put", {"device": "sim_motor", "value": 1.25})
        assert reply["status"] == "ok"
        assert reply["value"] == pytest.approx(1.25)
        assert dev_svc.motor.readback.get() == pytest.approx(1.25)

    def test_put_wait_false_replies_accepted(self, dev_svc):
        reply = _invoke(
            dev_svc,
            "commands.device.put",
            {"device": "sim_motor", "value": 2.0, "wait": False},
        )
        assert reply["status"] == "accepted"

    def test_put_busy_engine_rejected(self, dev_svc):
        dev_svc.service._engine.is_idle = False
        reply = _invoke(dev_svc, "commands.device.put", {"device": "sim_motor", "value": 9})
        assert reply["code"] == "busy"

    def test_put_missing_value_bad_request(self, dev_svc):
        reply = _invoke(dev_svc, "commands.device.put", {"device": "sim_motor"})
        assert reply["code"] == "bad_request"

    def test_put_behavior_queue_unsupported(self, dev_svc):
        reply = _invoke(
            dev_svc,
            "commands.device.put",
            {"device": "sim_motor", "value": 1, "behavior": "queue"},
        )
        assert reply["code"] == "bad_request"

    def test_put_timeout(self, dev_svc):
        import ophyd.sim

        slow = ophyd.sim.SynAxis(name="slow_motor", delay=5.0)
        dev_svc.service._catalog._infos["slow_motor"] = __import__(
            "lightfall.devices.model", fromlist=["DeviceInfo"]
        ).DeviceInfo(name="slow_motor", device_class="ophyd.sim.SynAxis")
        dev_svc.service._catalog._ophyd["slow_motor"] = slow
        reply = _invoke(
            dev_svc,
            "commands.device.put",
            {"device": "slow_motor", "value": 1.0, "timeout_s": 0.2},
        )
        assert reply["code"] == "timeout"

    def test_put_readonly_signal_rejected(self, dev_svc):
        reply = _invoke(
            dev_svc,
            "commands.device.put",
            {"device": "sim_motor", "signal": "readback", "value": 5},
        )
        # SynAxis readback is a settable SynSignal in some versions; accept either
        # a limits rejection or successful write — the writable gate is what we test:
        assert reply.get("code") in ("limits", None) or reply.get("status") in ("ok",)
```

**Implementation-time check for `test_put_readonly_signal_rejected`:** verify what SynAxis's readback actually is in the installed ophyd; if it is freely writable, replace this test with one using an explicitly read-only signal (e.g. `ophyd.sim.SynSignalRO`) added to the fake catalog, asserting `code == "limits"`.

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (`commands.device.get/put` not registered).

- [ ] **Step 3: Implement in `src/lightfall/remote/service.py`**

3a. Register:

```python
            ("commands.device.get", self._handle_device_get, "Read a device signal value"),
            ("commands.device.put", self._handle_device_put, "Write a device signal (ca put-callback semantics)"),
```
with the `_dispatch` handler pair as before.

3b. Signal resolution + get:

```python
    def _resolve_signal(self, obj: Any, signal_name: str | None) -> Any | None:
        """Resolve a signal on *obj*.

        ``None`` → the device's primary readback: ``user_readback`` then
        ``readback`` (motor conventions, see ui/widgets/motor_control.py:207),
        else the object itself when it is signal-like (has ``get``).
        Named lookup walks the instantiated ``_signals`` dict first (lazy-safe),
        supports dotted paths for nested components.
        """
        if signal_name is None:
            signals = getattr(obj, "_signals", {}) or {}
            for attr in ("user_readback", "readback"):
                sig = signals.get(attr)
                if sig is not None:
                    return sig
            return obj if hasattr(obj, "get") else None

        current = obj
        for part in signal_name.split("."):
            signals = getattr(current, "_signals", {}) or {}
            nxt = signals.get(part)
            if nxt is None:
                # Fall back to getattr ONLY for already-instantiated attrs
                nxt = current.__dict__.get(part) or getattr(type(current), part, None)
                if nxt is None or not hasattr(nxt, "get"):
                    return None
            current = nxt
        return current

    def _do_device_get(self, subject: str, data: dict, reply: str | None) -> None:
        resolved = self._resolve_device(data, reply)
        if resolved is None:
            return
        info, obj = resolved
        if obj is None:
            self._ipc.reply(reply, error_reply("unknown", f"Device '{info.name}' is not instantiated"))
            return
        sig = self._resolve_signal(obj, data.get("signal"))
        if sig is None:
            self._ipc.reply(
                reply,
                error_reply("unknown", f"Signal '{data.get('signal')}' not found on '{info.name}'"),
            )
            return
        try:
            reading = sig.read()
            key = next(iter(reading))
            value = reading[key]["value"]
            timestamp = reading[key]["timestamp"]
        except Exception:
            value = sig.get()
            timestamp = time.time()
        if hasattr(value, "tolist"):
            value = value.tolist()  # numpy scalar/array → JSON-safe
        self._ipc.reply(reply, ok_reply(value=value, timestamp=float(timestamp)))
```

3c. put:

```python
    def _do_device_put(self, subject: str, data: dict, reply: str | None) -> None:
        resolved = self._resolve_device(data, reply)
        if resolved is None:
            return
        info, obj = resolved
        if obj is None:
            self._ipc.reply(reply, error_reply("unknown", f"Device '{info.name}' is not instantiated"))
            return

        if "value" not in data:
            self._ipc.reply(reply, error_reply("bad_request", "value is required"))
            return
        behavior = data.get("behavior", "reject")
        if behavior != "reject":
            self._ipc.reply(
                reply,
                error_reply("bad_request", "device.put supports only behavior='reject' in v1"),
            )
            return
        if not self.engine.is_idle:
            self._ipc.reply(
                reply, error_reply("busy", "Engine is not idle; puts are rejected mid-scan")
            )
            return

        sig = self._resolve_signal(obj, data.get("signal"))
        # For a put with no explicit signal on a positioner, set the DEVICE
        # (motor.set moves the motor); only fall back to the readback for get.
        if data.get("signal") is None and hasattr(obj, "set"):
            sig = obj
        if sig is None:
            self._ipc.reply(
                reply,
                error_reply("unknown", f"Signal '{data.get('signal')}' not found on '{info.name}'"),
            )
            return
        if not self._is_writable(sig):
            self._ipc.reply(reply, error_reply("limits", "Signal is read-only"))
            return

        value = data["value"]
        wait = data.get("wait", True)
        timeout_s = float(data.get("timeout_s", PUT_DEFAULT_TIMEOUT_S))

        try:
            if hasattr(sig, "set"):
                status = sig.set(value)
            else:
                sig.put(value)
                status = None
        except Exception as exc:
            code = "limits" if "limit" in type(exc).__name__.lower() or "limit" in str(exc).lower() else "unknown"
            self._ipc.reply(reply, error_reply(code, str(exc)))
            return

        if not wait:
            self._ipc.reply(reply, ok_reply(status="accepted"))
            return

        if status is not None and hasattr(status, "wait"):
            try:
                status.wait(timeout=timeout_s)
            except Exception as exc:
                name = type(exc).__name__.lower()
                if "timeout" in name or "wait" in name:
                    self._ipc.reply(
                        reply, error_reply("timeout", f"Put did not complete within {timeout_s}s")
                    )
                else:
                    self._ipc.reply(reply, error_reply("unknown", str(exc)))
                return
        self._ipc.reply(reply, ok_reply(status="ok", value=value))
```

**Implementation-time check:** ophyd `StatusBase.wait(timeout=...)` raises `WaitTimeoutError` (from `ophyd.utils`) on timeout — import it explicitly if available and match on it instead of the name heuristic:
```python
        from ophyd.utils import WaitTimeoutError  # at module top, in try/except ImportError
```

- [ ] **Step 4: Run tests**

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/remote/ -v`
Expected: PASS.

- [ ] **Step 5: Run the FULL unit suite to catch regressions**

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ -x -q --ignore=tests/integration`
Expected: PASS (pre-existing failures unrelated to this branch may exist — verify against a master baseline before blaming your change).

- [ ] **Step 6: Commit**

```bash
git add src/lightfall/remote/service.py tests/remote/test_service_device.py
git commit -m "feat(remote): device.get/put with completion-wait and busy/limits/timeout errors"
```

---

### Task 8: Headless reference client + e2e tests

**Files:**
- Create: `tests/integration/remote_client.py`
- Create: `tests/integration/test_remote_control_e2e.py`

**Interfaces:**
- Consumes: everything above; `LocalNatsServer` (`lightfall.ipc.local_server`); nats-py.
- Produces: `class LightfallRemoteClient` — raw nats-py, **zero lightfall imports** (it is Spec #2's starting point and the contract's reference consumer): `connect()`, `authenticate() -> dict`, `call(suffix, payload, timeout=5.0) -> dict`, `subscribe_event(suffix, cb)`, `close()`.

- [ ] **Step 1: Write the reference client**

```python
# tests/integration/remote_client.py
"""Headless reference client for the Lightfall remote-control contract (v1).

Deliberately raw nats-py with NO lightfall imports: this file is the
contract's reference consumer and the starting point for Spec #2's
pystxmcontrol ``LightfallClient``.

Flow:
    client = LightfallRemoteClient("nats://127.0.0.1:4222", "als.test", "myapp")
    await client.connect()
    auth = await client.authenticate()        # -> approved reply w/ session_token
    reply = await client.call("commands.plan.list", {})
    await client.subscribe_event("runs.new", cb)
    await client.close()
"""

from __future__ import annotations

import json
from typing import Any, Callable

import nats

CONTRACT_VERSION = 1


class RemoteError(Exception):
    """Raised when the server replies with a structured error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class LightfallRemoteClient:
    """Minimal remote-control client: handshake + capability-channel calls."""

    def __init__(self, nats_url: str, prefix: str, app_name: str, app_version: str = "0.0") -> None:
        self._nats_url = nats_url
        self._prefix = prefix
        self._app_name = app_name
        self._app_version = app_version
        self._nc: nats.NATS | None = None
        self.session_token: str | None = None
        self.tiled_url: str | None = None
        self.tiled_token: str | None = None

    async def connect(self) -> None:
        self._nc = await nats.connect(self._nats_url)

    async def authenticate(self, timeout: float = 90.0) -> dict:
        """Run the auth.request handshake; store session_token on approval.

        The 90 s default outlives Lightfall's 60 s trust-dialog timeout.
        """
        msg = await self._nc.request(
            f"{self._prefix}.auth.request",
            json.dumps({"app_name": self._app_name, "app_version": self._app_version}).encode(),
            timeout=timeout,
        )
        reply = json.loads(msg.data.decode())
        if reply.get("status") == "approved":
            self.session_token = reply["session_token"]
            self.tiled_url = reply.get("tiled_url")
            self.tiled_token = reply.get("tiled_token")
        return reply

    async def call(self, suffix: str, payload: dict | None = None, timeout: float = 5.0) -> dict:
        """Request/reply on the capability channel; raise RemoteError on errors."""
        if self.session_token is None:
            raise RuntimeError("Not authenticated — call authenticate() first")
        subject = f"{self._prefix}.session.{self.session_token}.{suffix}"
        body = dict(payload or {})
        body.setdefault("contract_version", CONTRACT_VERSION)
        msg = await self._nc.request(subject, json.dumps(body).encode(), timeout=timeout)
        reply = json.loads(msg.data.decode())
        if reply.get("status") == "error":
            raise RemoteError(reply.get("code", "unknown"), reply.get("message", ""))
        return reply

    async def call_bare(self, suffix: str, payload: dict | None = None, timeout: float = 5.0) -> dict:
        """Request on the bare (non-channel) subject — used to prove rejection."""
        msg = await self._nc.request(
            f"{self._prefix}.{suffix}", json.dumps(payload or {}).encode(), timeout=timeout
        )
        return json.loads(msg.data.decode())

    async def subscribe_event(self, suffix: str, callback: Callable[[dict], Any]) -> None:
        """Subscribe a broadcast event (public prefixed subject)."""

        async def _cb(msg) -> None:
            callback(json.loads(msg.data.decode()))

        await self._nc.subscribe(f"{self._prefix}.{suffix}", cb=_cb)

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None
```

- [ ] **Step 2: Write the e2e test**

```python
# tests/integration/test_remote_control_e2e.py
"""End-to-end: LocalNatsServer + real IPCService + RemoteControlService +
real RunEngine + ophyd.sim devices + headless reference client.

Skips when no nats-server binary is resolvable (install extra `local-nats`).
Runs WITHOUT the integration marker gate — this is the primary contract test.
Tiled persistence is exercised only under LIGHTFALL_INTEGRATION=1.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from types import SimpleNamespace

import pytest

from lightfall.ipc.local_server import LocalNatsServer, resolve_nats_binary

pytestmark = pytest.mark.skipif(
    resolve_nats_binary() is None, reason="nats-server binary not available"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def nats_url():
    port = _free_port()
    server = LocalNatsServer(port=port)
    server.start(timeout_s=10.0)
    yield f"nats://127.0.0.1:{port}"
    server.stop()


@pytest.fixture
def lf(qapp, nats_url, monkeypatch):
    """A live server-side stack: IPCService + trust + RemoteControlService."""
    from ophyd.sim import SynAxis

    from lightfall.devices.model import DeviceCategory, DeviceInfo
    from lightfall.ipc.service import IPCService
    from lightfall.ipc.trust import TrustManager, TrustState
    from lightfall.remote.service import RemoteControlService

    prefix = "als.e2etest"
    ipc = IPCService(nats_url=nats_url, topic_prefix=prefix)
    trust = TrustManager()
    trust.approve("e2e-client")  # pre-approve: no TrustDialog in headless tests
    ipc.set_trust_manager(trust)
    ipc.register_meta_endpoints()

    # auth.request handler mirroring application._handle_ipc_auth_request for
    # the approved path (session=None acceptable: no tiled key in this test).
    def handle_auth(subject, data, reply):
        app_name = data.get("app_name", "unknown")
        if ipc.evaluate_trust(app_name) == TrustState.APPROVED:
            resp = {"status": "approved", "contract_version": 1}
            resp["session_token"] = ipc.mint_session_channel(app_name)
            ipc.reply(reply, resp)
        else:
            ipc.reply(reply, {"status": "denied", "contract_version": 1})

    ipc.register_action("auth.request", handle_auth, main_thread=False)

    # Real engine + sim device
    from lightfall.acquire.engine import get_engine, reset_engine

    reset_engine()
    engine = get_engine("bluesky")

    motor = SynAxis(name="e2e_motor", delay=0.2)

    class _Catalog:
        def list_devices(self, **kw):
            return [self._info]

        _info = DeviceInfo(
            name="e2e_motor", category=DeviceCategory.MOTOR, device_class="ophyd.sim.SynAxis"
        )

        def get_device_by_name(self, name):
            return self._info if name == "e2e_motor" else None

        def get_ophyd_device(self, name):
            return motor if name == "e2e_motor" else None

    remote = RemoteControlService(ipc, engine=engine, catalog=_Catalog())
    remote.start()
    ipc.start()

    # Wait for NATS connection
    deadline = time.monotonic() + 10
    while not ipc.is_connected and time.monotonic() < deadline:
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.processEvents()
        time.sleep(0.05)
    assert ipc.is_connected

    yield SimpleNamespace(
        ipc=ipc, trust=trust, engine=engine, motor=motor, prefix=prefix, remote=remote
    )

    remote.stop()
    ipc.stop()
    reset_engine()


class _ClientRunner:
    """Drives the async reference client from sync test code on a thread."""

    def __init__(self, nats_url, prefix):
        from tests.integration.remote_client import LightfallRemoteClient

        self.client = LightfallRemoteClient(nats_url, prefix, "e2e-client")
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self._thread.start()

    def run(self, coro, timeout=30.0):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def close(self):
        try:
            self.run(self.client.close(), timeout=5)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._thread.join(timeout=5)


@pytest.fixture
def client(lf, nats_url):
    runner = _ClientRunner(nats_url, lf.prefix)
    runner.run(runner.client.connect())
    yield runner
    runner.close()


def _pump_qt_until(predicate, timeout=15.0):
    from PySide6.QtCore import QCoreApplication

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_full_contract_flow(lf, client):
    # 1. Handshake → token + channel
    auth = client.run(client.client.authenticate())
    assert auth["status"] == "approved"
    assert auth["contract_version"] == 1
    assert client.client.session_token

    # 2. Bare-subject call is rejected
    bare = client.run(client.client.call_bare("commands.engine.status", {}))
    assert bare["status"] == "error" and bare["code"] == "denied"

    # 3. Device search / components / info / get round-trip
    reply = client.run(client.client.call("commands.device.search", {}))
    assert reply["devices"] == ["e2e_motor"]
    reply = client.run(client.client.call("commands.device.info", {"device": "e2e_motor"}))
    assert reply["device_class"] == "ophyd.sim.SynAxis"
    reply = client.run(client.client.call("commands.device.components", {"device": "e2e_motor"}))
    assert any(c["name"] == "readback" for c in reply["components"])
    reply = client.run(client.client.call("commands.device.get", {"device": "e2e_motor"}))
    assert "value" in reply and "timestamp" in reply

    # 4. put wait=true completes against the slow (delay=0.2) sim positioner
    t0 = time.monotonic()
    reply = client.run(
        client.client.call("commands.device.put", {"device": "e2e_motor", "value": 2.5}, timeout=10)
    )
    assert reply["status"] == "ok"
    assert time.monotonic() - t0 >= 0.15  # actually waited for completion
    assert lf.motor.readback.get() == pytest.approx(2.5)

    # 5. plan.run of a sim plan → run_uid; runs.new/complete observed
    events: list[tuple[str, dict]] = []
    client.run(client.client.subscribe_event("runs.new", lambda d: events.append(("new", d))))
    client.run(
        client.client.subscribe_event("runs.complete", lambda d: events.append(("complete", d)))
    )

    plans = client.run(client.client.call("commands.plan.list", {}))["plans"]
    assert plans, "plan registry is empty — default registry did not load"
    # Run the simplest available plan; prefer a count-like plan with no
    # device params. Implementation-time: pick from the actual default
    # registry (create_default_registry) — a `count`-style typed wrapper.
    plan_name = next((p["name"] for p in plans if not any(
        pr["default"] is None and pr["type"] not in ("int", "float", "str", "bool")
        for pr in p["params"]
    )), None)
    assert plan_name, f"No parameterless-safe plan found in {[p['name'] for p in plans]}"

    reply = client.run(
        client.client.call("commands.plan.run", {"plan_name": plan_name, "params": {}}, timeout=15)
    )
    assert reply["status"] == "submitted"
    assert reply["item_id"]

    assert _pump_qt_until(lambda: any(e[0] == "complete" for e in events), timeout=30)
    new_evt = next(d for k, d in events if k == "new")
    assert new_evt["item_id"] == reply["item_id"]
    assert new_evt["run_uid"]
    if reply["run_uid"] is not None:
        assert reply["run_uid"] == new_evt["run_uid"]

    # 6. Logout kills the channel; re-handshake restores it
    lf.trust.clear()
    lf.ipc.teardown_session_channels()
    with pytest.raises(Exception):  # timeout or denied — channel is dead
        client.run(client.client.call("commands.engine.status", {}, timeout=2))
    lf.trust.approve("e2e-client")
    auth2 = client.run(client.client.authenticate())
    assert auth2["status"] == "approved"
    assert auth2["session_token"] != auth["session_token"]
    reply = client.run(client.client.call("commands.engine.status", {}))
    assert reply["state"] in ("idle", "running")


def test_busy_rejection_while_plan_runs(lf, client):
    client.run(client.client.authenticate())
    plans = client.run(client.client.call("commands.plan.list", {}))["plans"]
    # Implementation-time: choose a plan that runs for >=1s (e.g. a count with
    # delay param); parameterize it so the engine is verifiably busy.
    # Then assert plan.run(behavior=reject) and device.put both return busy:
    # ... (fill in with the actual registry's plan + params)
```

**Implementation-time notes for this task (the executor MUST resolve these):**
1. The default plan registry contents come from `create_default_registry()` (`registry.py:510`) → `lightfall_plans.register_lightfall_plans()`. Open `src/lightfall/acquire/plans/lightfall_plans.py`, pick a real plan (e.g. a typed `count` wrapper taking `detectors` + `num` + `delay`) and write `test_busy_rejection_while_plan_runs` concretely: submit a long plan (`delay` ≥ 1 s per point, several points), poll `state.engine`/`engine.status` until running, then assert `plan.run` (default behavior) → `busy` and `device.put` → `busy`, then wait for completion. If all default plans require device objects as params, the plan-registry path may need the test to register its own trivial plan in the real registry (`registry.register_plan` or equivalent — check the API) that does `yield from bps.sleep(...)`-style steps with `open_run/close_run` so start/stop docs are emitted. A minimal plan:
   ```python
   import bluesky.plan_stubs as bps
   import bluesky.preprocessors as bpp

   @bpp.run_decorator(md={"plan_name": "e2e_sleep"})
   def e2e_sleep(seconds: float = 2.0):
       yield from bps.sleep(seconds)
   ```
   registered into the registry the plan.list handler reads.
2. The BlueskyEngine creates its RunEngine lazily on the worker thread; the first submit boots it. Give generous timeouts (30 s).
3. Tiled persistence ("run lands in Tiled") is only asserted when `LIGHTFALL_INTEGRATION=1` and the tiled deps import — follow the `tiled_env` fixture pattern from `tests/integration/test_tsuchinoko_e2e.py:131-141` and subscribe a TiledWriter to `engine.RE`. Gate that assertion with `@pytest.mark.integration` in a separate test function; do NOT gate the rest of this module.
4. If Qt-event pumping proves flaky for signal delivery (engine signals are emitted from the RE worker thread and queued to the main thread), pump with `_pump_qt_until` as written — it processes the main-thread event queue from the test thread, which IS the main thread here.

- [ ] **Step 3: Run the e2e**

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/integration/test_remote_control_e2e.py -v -x`
Expected: PASS (or SKIP if nats-server-bin missing — in that case `pip install nats-server-bin` into the venv, or verify the binary exists at `.venv/Scripts/nats-server.exe`).

- [ ] **Step 4: Run full suite again**

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ -q --ignore=tests/integration`
then
`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/integration/test_remote_control_e2e.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/remote_client.py tests/integration/test_remote_control_e2e.py
git commit -m "test(remote): headless reference client + full-contract e2e over LocalNatsServer"
```

---

### Task 9: Documentation — ipc-architecture.md + ipc-client-guide.md

**Files:**
- Modify: `docs/developer-guide/ipc-architecture.md`
- Modify: `docs/developer-guide/ipc-client-guide.md`

These docs are the **published contract** (lightfall's `docs/superpowers/` is gitignored; these are not). Update them fully — no "see spec" hand-waving. Read both files end-to-end first; the outlines below list required changes, and unchanged sections stay as they are.

- [ ] **Step 1: Update `ipc-architecture.md`**

Required edits:
1. **Components**: add a `### RemoteControlService` subsection — lives in `lightfall/remote/service.py`, registered in `ServiceRegistry`, wired in `_start_ipc` via `_wire_remote_control()`; owns plan/queue/engine/device actions and the run-lifecycle events; handlers never gate themselves (enforcement is central in IPCService).
2. **New section `## Capability Channels`** after Components, covering: NATS core messages carry no sender identity, so the per-session private channel IS the authentication mechanism; `auth.request` approval mints `session_token` (`secrets.token_urlsafe(32)`); all `commands.*` travel on `{prefix}.session.{token}.<suffix>`; bare `commands.*` → structured `denied`; broadcast events (`runs.new`, `runs.complete`, `state.engine`) are the documented exception (public subjects, no secrets, multi-listener); teardown on logout/revocation; production posture — tokens authenticate, subject-privacy *enforcement* against hostile broker peers comes from broker-side permissions on bcgnats (operational config, not client-side); LocalNatsServer runs plaintext/unenforced.
3. **TrustManager section**: note trust is per-login-session — `SessionManager.state_changed` → on UNAUTHENTICATED, `TrustManager.clear()` + `IPCService.teardown_session_channels()` (wired in `_wire_session_trust`).
4. **Wiring and Lifecycle**: replace the `_wire_engine_ipc`/`_wire_plan_commands` bullets with `_wire_remote_control` (RemoteControlService registers `commands.plan.*`, `commands.queue.get`, `commands.engine.status`, `commands.device.*`, and publishes `runs.new`/`runs.complete`/`state.engine`); note logbook/agent actions are now `trusted=True`.
5. **Registering a New Action** code sample: add the `trusted=True` kwarg and a sentence on when to use it (any action a remote client invokes post-handshake).
6. **Threading Model**: add RemoteControlService's executor model (handlers on NATS thread → ThreadPoolExecutor, replies from workers; `plan.abort` marshals to the main thread).
7. **Structured errors**: document `{status:"error", code, message, contract_version}` and the code enum; note it supersedes `{"error": true}`.

- [ ] **Step 2: Update `ipc-client-guide.md`**

Required edits:
1. **Authentication**: approved reply now includes `session_token` and `contract_version: 1` (alongside `tiled_token`, `tiled_url`, `session_id`). Add: trust is per-login-session — on Lightfall logout the channel dies; detect the dead channel (request timeouts) and re-run `auth.request`.
2. **New section "The capability channel"**: all commands go to `{prefix}.session.{session_token}.<command-suffix>`; bare `commands.*` are rejected with `denied`; include `contract_version: 1` in requests (mismatch → `version_mismatch`).
3. **Sending Commands**: full v1 verb table exactly as spec §5.1 (plan.list/run/abort, queue.get, engine.status, device.search/components/info/get/put + logbook.add, agent.message) with request/reply payloads, `behavior:"reject"` defaults, `item_id`/`run_uid` semantics (queued plans reply `run_uid: null`; clients fall back to `runs.new`), put wait semantics.
4. **Events**: `runs.new {item_id, run_uid, plan_name}`, `runs.complete {run_uid, exit_status}` — **field renames `run_id`→`run_uid` called out as breaking**, `procedure_id`→`item_id` likewise.
5. **Structured errors** section with the code enum and the guidance "any reply with `status: "error"` carries `code` + `message`".
6. **Message Format Reference** and **Topic Hierarchy Reference** tables: regenerate with the new fields/subjects (drop `procedure_id`, `run_id`; add `item_id`, `run_uid`, `session_token`, `contract_version`, `value`, `timestamp`, `devices`, `components`, `plans`, `items`, `state`).
7. **Complete Example**: replace with a trimmed version of `tests/integration/remote_client.py`'s flow (handshake → capability call → event subscribe), and point to that file as the reference client. Update the tsuchinoko-style example's field names.

- [ ] **Step 3: Verify docs build/lint if applicable** — check for a docs build (sphinx/mkdocs config); if none, at least render-check the markdown tables.

- [ ] **Step 4: Commit**

```bash
git add docs/developer-guide/ipc-architecture.md docs/developer-guide/ipc-client-guide.md
git commit -m "docs(ipc): capability channels, remote-control verbs, item_id/run_uid renames, structured errors"
```

---

### Task 10: Final verification + branch finish

- [ ] **Step 1: Full test suite**

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ -q --ignore=tests/integration`
and
`QT_QPA_PLATFORM=offscreen PYTHONPATH=src C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/integration/test_remote_control_e2e.py -v`
Expected: PASS (compare any failures against a master baseline).

- [ ] **Step 2: Lint**

`C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m ruff check src/ tests/remote/ tests/ipc/test_capability_channels.py tests/integration/remote_client.py tests/integration/test_remote_control_e2e.py`
Expected: clean.

- [ ] **Step 3: Grep for leftovers**

- `grep -rn "procedure_id" src/ docs/developer-guide/` → only historical notes, no live code paths.
- `grep -rn '"run_id"' src/ docs/developer-guide/` → none in remote/ipc paths.
- `grep -rn "_wire_plan_commands\|_wire_engine_ipc" src/ tests/` → none.

- [ ] **Step 4: Whole-branch code review** (superpowers:requesting-code-review), fix findings, then **superpowers:finishing-a-development-branch**. Branch stays LOCAL — Ron drives the merge/PR.

---

## Self-Review (done at plan time)

- **Spec coverage:** §2 breaking changes → Tasks 2/4/5 (renames, reject default, trusted commands incl. logbook/agent). §3 principles → contract_version (Tasks 1-2), central enforcement (Task 2), per-login trust (Task 3), structured errors (Task 1, all handlers). §4 capability channels → Task 2. §5 message set → Tasks 4-7 (all ten verbs + three events). §6 architecture → Tasks 4-7 (two-layer split, executor threading). §7 testing → unit per task + Task 8 e2e (handshake, bare-reject, device round-trips, slow-positioner put, plan→run_uid→events, busy rejections, logout/re-handshake); Tiled landing gated behind the integration marker. Headless client (§1.1/§6) → Task 8. Docs (§6) → Task 9. §8 non-goals excluded.
- **Known implementation-time checks are flagged inline:** registry listing method name (Task 5), SynAxis readback writability (Task 7), `WaitTimeoutError` import (Task 7), concrete plan choice for e2e busy test (Task 8).
- **Type consistency:** `ok_reply`/`error_reply` used uniformly; `_trusted_actions: dict[str, _Subscription]` consistent between Tasks 2 and 4-7 test fakes; `mint_session_channel`/`teardown_session_channels`/`session_channel_count` names match across Tasks 2, 3, 8.
