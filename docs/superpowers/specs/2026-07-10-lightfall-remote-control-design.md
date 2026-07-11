# Lightfall Remote Control API — Design

**Date:** 2026-07-10 (rev 2, 2026-07-11: reconciled with Lightfall IPC docs + code)
**Status:** Approved design (Ron, from David Shapiro's direction), pending implementation plan
**Scope:** Spec #1 of 3 for the pystxmcontrol-as-remote-client program. This spec covers the versioned NATS contract and the Lightfall-core service behind it. Spec #2 (pystxmcontrol `LightfallClient` + UI refactor, David's repo/our fork) and Spec #3 (`lightfall-pystxmcontrol` panel slim-down) follow separately, both bound by the contract defined here.

## 1. Context and goal

David Shapiro wants pystxmcontrol to live independently as a thin remote GUI: the Lightfall instance deployed at the beamline hosts his device drivers in-process (the existing ophyd-async wrappers), executes scans on the bluesky RunEngine, and pushes data to Tiled — while remote pystxmcontrol app instances talk to Lightfall as a GUI+server over NATS and read data back via Tiled. The pystxmcontrol app drops its scan server and HDF5/NeXus writers.

This spec defines the generic, instrument-agnostic remote-control surface: an extension and hardening of Lightfall's **existing** `commands.*` / `runs.*` / `state.*` IPC surface (see §2), adding device get/put, plan/queue/engine introspection, capability-based trust enforcement, and per-login-session channels. Built in Lightfall core from the beginning.

The acquisition stack is untouched: ophyd wrappers, RunEngine, plan queue, TiledWriter, visualization all stay as they are.

### 1.1 Program decomposition (approach C: contract-first, parallel build)

1. **This spec:** contract + core implementation (`lightfall.remote` service module + `IPCService` trust plumbing). Includes a headless test client used by the e2e tests, and the required updates to `docs/developer-guide/ipc-architecture.md` and `ipc-client-guide.md` (the published contract).
2. **Spec #2:** `pystxmcontrol` (fork `als-controls/pystxmcontrol`): `LightfallClient` (raw nats-py + tiled.client, no lightfall imports — the stxm-live stack), UI widgets refactored to speak only the client, standalone app entry point, scan server + HDF5/NeXus writers dropped. Tiled read-side/streaming code ported back from our Lightfall panels.
3. **Spec #3:** `lightfall-pystxmcontrol` panels become thin `PanelPlugin` wrappers importing pystxmcontrol widgets, pointed at the local broker (in-process short-circuiting of loopback NATS messages is a later optimization, explicitly out of scope).

## 2. Reconciliation with the current IPC surface (normative baseline)

What exists today (docs: `ipc-architecture.md`, `ipc-client-guide.md`; code: `lightfall/ipc/service.py`, `ipc/trust.py`, `core/application.py`):

- Actions `commands.plan.run`, `commands.plan.abort`, `commands.logbook.add`, `commands.agent.message`; events `runs.new`, `runs.complete`, `state.engine`; discovery `meta.actions`/`meta.events`; trust handshake `auth.request` (TrustDialog, 60 s timeout, per-app-name in-memory `TrustManager`).
- **Gap 1 — no action authorization:** `commands.*` handlers perform no trust check; any client on the broker knowing the prefix can submit plans. Trust currently gates only Tiled-token delivery.
- **Gap 2 — no sender identity:** NATS core messages carry no identity, so per-handler trust checks are not even implementable as-is. This design closes both gaps with capability channels (§4).
- **Gap 3 — trust is per-process, not per-login:** `TrustManager` persists for the app lifetime; `clear()` exists but is unwired. (`SessionManager.logout()` already clears all service keys, so the Tiled-key half of per-session scoping already works.)
- **No private channels exist today.** They are introduced by this design; the IPC docs must be updated accordingly.

**Deliberate breaking changes (Ron-approved, 2026-07-11 — no known external consumers to break; better to realign now):**

1. Existing `commands.*` actions become trust-gated (untrusted callers are rejected — that is the point).
2. `commands.plan.run` reply field `procedure_id` → **`item_id`** (meaning: the queue item's id; "procedure_id" was unclear), and its default concurrency behavior changes from implicit-queue to **`behavior: "reject"`**.
3. Event payload field `run_id` → **`run_uid`** (align with bluesky/Tiled naming) in `runs.new` / `runs.complete`.

## 3. Contract principles (normative)

1. **JSON-only over NATS.** Arrays and bulk data never cross the bus; data flows via Tiled (streaming reads, same read-side rules as stxm-live: poll/subscribe array or table nodes, never scalar column facets).
2. **Instance targeting:** every subject carries the Lightfall instance's topic prefix (registered via `IPCService.register_action`/`register_event`; discovery via `meta.actions`/`meta.events` comes for free). A client always addresses one specific Lightfall.
3. **Trust before actions, enforced centrally (Gap 1+2 fix):** the only subjects reachable pre-trust are `{prefix}.auth.request` and `{prefix}.meta.*`. All `commands.*` actions are reachable only through the client's capability channel (§4). Enforcement lives in **`IPCService`, not in individual handlers** — receivers never implement their own gating.
4. **Tiled tokens only after trust:** the Tiled API key rides in the `auth.request` approval reply (existing semantics) — never earlier, never on another subject.
5. **Trust is per-login-session:** trust, capability channels, and Tiled keys are all scoped to the Lightfall login session. `SessionManager.logout()` additionally triggers `TrustManager.clear()` and capability-channel teardown (new wiring); clients detect the dead channel and re-run `auth.request` after the next login (client-side precedent: xpcs_live `invalidate_auth_if_session_changed`).
6. **Contract is versioned:** `contract_version: 1` in every reply; mismatch is a structured rejection.
7. **Structured errors everywhere:** `{status: "error", code, message}` with codes `busy | limits | timeout | unknown | denied | bad_request | version_mismatch`. (Supersedes the older `{"error": true}` shape; the docs update covers this.)

## 4. Capability channels (the trust mechanism)

Because NATS core messages carry no sender identity, the per-session private channel **is** the authentication mechanism — a capability. Introduced by this design (new machinery; not in the current docs):

- On `auth.request` approval, the reply additionally carries `session_token` — an unguessable token (≥128-bit, `secrets.token_urlsafe`) minted per app per login session.
- All post-trust actions travel on `{prefix}.session.{session_token}.<action-suffix>` (e.g. `als.7011.session.a1b2c3….commands.device.put`). `IPCService` subscribes the session wildcard at approval and routes to the registered action handlers, attaching the resolved app identity + session to the handler context. Requests on bare `{prefix}.commands.*` subjects are rejected with `denied`.
- Possession of the token = proof of completed handshake in the current login session. Channel privacy also keeps request/reply payloads off shared subjects.
- **Broadcast events are the documented exception** (`runs.new`, `runs.complete`, `state.engine`): they carry no secrets and multi-listener is the point; they publish on the public prefixed subjects.
- Teardown: on logout (or trust revocation in Preferences), the session wildcard subscriptions are unsubscribed and tokens invalidated; `TrustManager.clear()` runs on logout.
- **Production posture:** capability tokens authenticate; *enforcement* of subject privacy against a hostile broker peer comes from broker-side permissions on bcgnats (operational configuration, documented here, not implemented client-side). Local dev (`LocalNatsServer`) runs plaintext/unenforced as today.

## 5. The message set (v1 — full set is milestone 1)

Suffixes below are logical names; post-trust actions travel inside the capability channel (§4). All payloads JSON.

### 5.1 Actions (req/reply)

| Subject (suffix) | Request | Reply |
|---|---|---|
| `commands.plan.list` | `{}` | `{plans: [{name, params: [{name, type, unit, default}]}]}` — from the plan-plugin registry, reusing the `Annotated` param metadata the plan UI reads |
| `commands.plan.run` | `{plan_name, params, behavior: "reject"\|"queue"}` (default **reject**) | `{status:"submitted", plan_name, item_id, run_uid\|null}` or error (`busy` when `behavior:"reject"` and engine busy) |
| `commands.plan.abort` | `{item_id? \| run_uid?, reason?}` | `{status:"abort_requested"}` / `{status:"not_aborted", message}` or error |
| `commands.queue.get` | `{}` | `{items: [{item_id, plan_name, state}]}` |
| `commands.engine.status` | `{}` | `{state: "idle"\|"running", item_id, run_uid, plan_name}` |
| `commands.device.search` | `{**kwargs}` (happi-style filters; `{}` = list all) | `{devices: [name, ...]}` — names only |
| `commands.device.components` | `{device}` | `{components: [{name, type, writable}]}` — sub-devices and signals; hierarchy walkable by repeated calls |
| `commands.device.info` | `{device}` | `{name, category, device_class}` — thin metadata; units/limits are read as their own signals via `get` (EPICS `.EGU`/`.HLM` style) |
| `commands.device.get` | `{device, signal?}` | `{value, timestamp}` — `signal` defaults to the device's primary readback |
| `commands.device.put` | `{device, signal?, value, behavior: "reject", wait: true, timeout_s?}` | `wait:true` (default): replies on **completion** (ca put-callback semantics) `{status:"ok", value}`; `wait:false`: replies `{status:"accepted"}` on dispatch. Errors: `busy \| limits \| timeout \| unknown` |

Existing `commands.logbook.add` and `commands.agent.message` are unchanged in shape but move behind the capability channel like everything else.

### 5.2 Events (published, broadcast, public subjects)

| Subject (suffix) | Payload |
|---|---|
| `state.engine` | `{state: "idle"\|"running"}` (existing event, unchanged) |
| `runs.new` | `{item_id, run_uid, plan_name}` (existing event; `run_id`→`run_uid`, gains `item_id`) |
| `runs.complete` | `{run_uid, exit_status}` (existing event; `run_id`→`run_uid`) |

### 5.3 Semantics

- **run_uid timing:** a queued plan has no run_uid at submission. `plan.run` always replies with `item_id`; `runs.new` publishes the `item_id → run_uid` mapping when the RunEngine opens the run. For the common case (idle engine, `behavior:"reject"`), the handler waits briefly (~2 s) for the start doc and fills `run_uid` directly in the reply; clients fall back to the event when it is null.
- **Concurrency model:** `behavior` defaults to `"reject"` on both `plan.run` and `device.put`. UIs are expected to lock scan submission and manual controls while `state.engine != idle` (first line of defense); the reject reply is the race backstop. Multiple trusted clients are allowed (free-for-all); all clients listen on the broadcast events. Leases/single-operator control are explicitly deferred.
- **`device.put` mid-scan:** rejected by default (`behavior:"reject"` + engine busy → `busy` error). No scan-safe allowlist in v1.
- **No device value streaming.** Monitoring is the controller's (IOC's) responsibility and David's device classes don't support it; UIs poll `device.get`. Data progress has no bus events — clients watch the run in Tiled.

## 6. Lightfall-side architecture

Two layers, split by responsibility:

- **`IPCService` (lightfall/ipc/service.py) — trust plumbing, generic:** capability-channel minting on approval (`session_token`, wildcard subscription, identity attach), central pre-handler trust gate (bare `commands.*` → `denied`), channel teardown API, logout hook (`SessionManager.logout()` → `TrustManager.clear()` + teardown — mirrors the existing service-key clearing at session.py:546). No action semantics here.
- **`lightfall/remote/service.py` — `RemoteControlService`, action semantics:** registered in `ServiceRegistry`, wired at startup where `_wire_plan_commands` lives today (absorbing/replacing it). Thin adapters, no new state:
  - `plan.*` / `queue.*` → the existing engine submit/queue (`engine.submit` → item_id) + plan-plugin registry (param introspection from the same `Annotated` metadata the plan UI reads).
  - `device.*` → `DeviceCatalog` + ophyd signals. `search` mirrors happi's `.search(...)`.
  - `engine.*` / run events → a subscription on the engine's document stream (start/stop docs drive `runs.new`/`runs.complete` and the item_id→run_uid resolution). The busy check reads the same engine source of truth the UI uses.
- **Threading:** action handlers arrive per the existing IPC threading model; anything touching the RunEngine or ophyd goes through the same thread-safe entry points the panels use. `device.put` completion waits run on an executor with a timeout — never blocking the NATS loop or the Qt main thread.
- **Docs deliverable:** `ipc-architecture.md` + `ipc-client-guide.md` updated in the same milestone — capability channels, new verbs, renamed fields, structured errors, per-login-session trust. The client guide remains the single published contract.
- **Headless test client** ships with the core tests (raw nats-py, performs the full handshake + capability-channel flow) and doubles as the contract's reference consumer and Spec #2's starting point.

## 7. Testing

- **Unit (lightfall):** IPCService capability plumbing (mint on approve, route + identity attach, bare-subject rejection, teardown on logout/revoke); each action handler against mock engine/queue/DeviceCatalog; busy/reject paths; put wait/timeout paths; version mismatch.
- **e2e (lightfall):** local nats-server (`LocalNatsServer`) + sim devices + real RunEngine: headless client authenticates → gets token + channel; bare-subject call rejected; searches devices, walks components, get/put round-trips (put completion verified against a slow-moving sim positioner); `plan.run` of a sim plan → run_uid → run lands in Tiled; `runs.new`/`runs.complete` observed; busy rejections while a plan runs; logout kills the channel and a re-handshake restores it.
- **Cross-repo (later, Spec #2):** the pystxmcontrol standalone app against a live local Lightfall — the same golden-run rigor as the stxm-live smoke.

## 8. Non-goals (v1)

Device value streaming over NATS; single-operator leases; per-action authorization beyond app trust; scan-safe device allowlist for mid-scan puts; in-process short-circuiting of loopback NATS calls (Spec #3's later optimization); broker-side permission provisioning on bcgnats (production posture documented, configured operationally); the stxm-live analysis service (unaffected).

## 9. Impact on existing work

- `lightfall-pystxmcontrol` acquisition layer (wrappers, flyer, plans, viz): unchanged — it is the hardware-adjacent execution layer this design assumes.
- Our native panels (scan, spectrum): their Tiled read-side/streaming logic gets ported back into David's widgets under Spec #2; the panels themselves are superseded by Spec #3's thin wrappers.
- `stxm-live` (external analysis, 2026-07-09): unaffected — it reads Tiled and speaks its own `stxm.*` namespace. Its `auth.request` usage transparently gains a capability channel it doesn't need to use (it only listens to `stxm.*` binds and reads Tiled); no change required in v1.
- Existing IPC docs examples (tsuchinoko-style client): updated as part of the docs deliverable to the new handshake + field names.
