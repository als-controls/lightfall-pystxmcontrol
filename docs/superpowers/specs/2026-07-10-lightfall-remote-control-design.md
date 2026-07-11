# Lightfall Remote Control API (`lightfall.remote`) — Design

**Date:** 2026-07-10
**Status:** Approved design (Ron, from David Shapiro's direction), pending implementation plan
**Scope:** Spec #1 of 3 for the pystxmcontrol-as-remote-client program. This spec covers the versioned NATS contract and the Lightfall-core `RemoteControlService`. Spec #2 (pystxmcontrol `LightfallClient` + UI refactor, David's repo/our fork) and Spec #3 (`lightfall-pystxmcontrol` panel slim-down) follow separately, both bound by the contract defined here.

## 1. Context and goal

David Shapiro wants pystxmcontrol to live independently as a thin remote GUI: the Lightfall instance deployed at the beamline hosts his device drivers in-process (the existing ophyd-async wrappers), executes scans on the bluesky RunEngine, and pushes data to Tiled — while remote pystxmcontrol app instances talk to Lightfall as a GUI+server over NATS and read data back via Tiled. The pystxmcontrol app drops its scan server and HDF5/NeXus writers.

This spec defines the generic, instrument-agnostic remote-control surface Lightfall exposes to make that possible: **`remote.*`** — plan execution, device get/put, engine/queue introspection, and lifecycle events. It is built "right from the beginning" as a Lightfall-core capability (not a plugin), following the existing IPC best-practice documentation for trusted, secure channels.

The acquisition stack is untouched: ophyd wrappers, RunEngine, plan queue, TiledWriter, visualization all stay as they are. This is an additive control surface.

### 1.1 Program decomposition (approach C: contract-first, parallel build)

1. **This spec:** contract + `lightfall.remote` core service. Includes a headless test client used by the e2e tests.
2. **Spec #2:** `pystxmcontrol` (fork `als-controls/pystxmcontrol`): `LightfallClient` (raw nats-py + tiled.client, no lightfall imports — the stxm-live stack), UI widgets refactored to speak only the client, standalone app entry point, scan server + HDF5/NeXus writers dropped. Tiled read-side/streaming code ported back from our Lightfall panels.
3. **Spec #3:** `lightfall-pystxmcontrol` panels become thin `PanelPlugin` wrappers importing pystxmcontrol widgets, pointed at the local broker (in-process short-circuiting of loopback NATS messages is a later optimization, explicitly out of scope).

Both repos build against this contract concurrently; the pystxmcontrol side can develop against a fake broker using the established FakeIPC/local-nats test patterns.

## 2. Contract principles (normative)

1. **JSON-only over NATS.** Arrays and bulk data never cross the bus; data flows via Tiled (streaming reads, same read-side rules as stxm-live: poll/subscribe array or table nodes, never scalar column facets).
2. **Instance targeting:** every `remote.*` subject carries the Lightfall instance's topic prefix (e.g. `als.7011.remote.plan.run`) — registered via `IPCService.register_action`/`register_event`, so prefixing, `_lightfall.discover` discovery, and reply plumbing come for free. A client always addresses one specific Lightfall.
3. **Trust before actions:** the only subject available to an un-trusted client is `{prefix}.auth.request`. Every `remote.*` handler rejects senders that have not completed the trust handshake.
4. **Tiled tokens only after trust:** the Tiled API key rides in the `auth.request` approval reply (existing semantics) — never earlier, never on another subject.
5. **Private channels post-trust:** the approval reply grants a per-session private subject space — `{prefix}.remote.{session_token}.>` with an unguessable `session_token` — and all subsequent actions and replies occur inside it. **Broadcast events are the documented exception** (`engine.state`, `run.started`, `run.stopped`, `remote.error`): they carry no secrets and multi-listener is the point. The exact mechanism must align with the existing IPC secure-channel documentation; production *enforcement* of subject privacy (vs. obscurity) comes from broker-side permissions on bcgnats and is stated as the production posture, not implemented client-side.
6. **Trust is per-login-session.** Trust, private channels, and Tiled keys are scoped to the Lightfall login session (Keycloak `sub`, already carried as `session_id` in auth replies). On logout, Lightfall clears the trust table and tears down private channels; clients detect the drop and re-run `auth.request` after the next login (client-side pattern precedent: xpcs_live `invalidate_auth_if_session_changed`).
7. **Contract is versioned.** `contract_version: 1` in every reply; mismatch handling is a logged, structured rejection.
8. **Structured errors everywhere:** `{status: "error", code, message}` with codes `busy | limits | timeout | unknown | denied | bad_request | version_mismatch`.

## 3. The message set (v1 — full set is milestone 1)

Subject naming: the tables below give **logical suffixes**. Pre-trust there is exactly one reachable subject, `{prefix}.auth.request`. Post-trust, actions travel inside the client's private space — transport subject `{prefix}.remote.{session_token}.<suffix>` (e.g. `als.7011.remote.a1b2c3.plan.run`), with the service subscribing the session's wildcard at trust establishment and unsubscribing at logout. Events are the broadcast exception and publish on the public `{prefix}.remote.<suffix>` subjects.

### 3.1 Actions (req/reply)

| Subject (suffix) | Request | Reply |
|---|---|---|
| `remote.plan.list` | `{}` | `{plans: [{name, params: [{name, type, unit, default}]}]}` — from the plan-plugin registry, reusing the `Annotated` param metadata the plan UI reads |
| `remote.plan.run` | `{plan, params, behavior: "reject"\|"queue"}` | `{status:"accepted", item_id, run_uid\|null}` or error (`busy` when `behavior:"reject"` and engine busy) |
| `remote.plan.abort` | `{item_id\|run_uid}` | `{status:"ok"}` or error |
| `remote.queue.get` | `{}` | `{items: [{item_id, plan, state}]}` |
| `remote.engine.status` | `{}` | `{state: "idle"\|"running", item_id, run_uid, plan}` |
| `remote.device.search` | `{**kwargs}` (happi-style filters; `{}` = list all) | `{devices: [name, ...]}` — names only |
| `remote.device.components` | `{device}` | `{components: [{name, type, writable}]}` — sub-devices and signals; hierarchy walkable by repeated calls |
| `remote.device.info` | `{device}` | `{name, category, device_class}` — thin metadata; units/limits are read as their own signals via `get` (EPICS `.EGU`/`.HLM` style) |
| `remote.device.get` | `{device, signal?}` | `{value, timestamp}` — `signal` defaults to the device's primary readback |
| `remote.device.put` | `{device, signal?, value, behavior: "reject", wait: true, timeout_s?}` | `wait:true` (default): replies on **completion** (ca put-callback semantics) `{status:"ok", value}`; `wait:false`: replies `{status:"accepted"}` on dispatch. Errors: `busy \| limits \| timeout \| unknown` |

### 3.2 Events (published, broadcast)

| Subject (suffix) | Payload |
|---|---|
| `remote.engine.state` | `{state: "idle"\|"running"}` |
| `remote.run.started` | `{item_id, run_uid, plan}` — the item_id → run_uid resolution |
| `remote.run.stopped` | `{run_uid, exit_status}` |
| `remote.error` | `{context, message}` |

### 3.3 Semantics

- **run_uid timing:** a queued plan has no run_uid at submission. `plan.run` always replies immediately with `item_id`; `remote.run.started` publishes the `item_id → run_uid` mapping when the RunEngine opens the run. For the common case (idle engine, `behavior:"reject"`), the handler waits briefly (~2 s) for the start doc and fills `run_uid` directly in the reply; clients fall back to the event when it is null.
- **Concurrency model:** `behavior` defaults to `"reject"` on both `plan.run` and `device.put`. UIs are expected to lock scan submission and manual controls while `engine.state != idle` (first line of defense); the reject reply is the race backstop. Multiple trusted clients are allowed (free-for-all); all clients can act as listeners on the broadcast events. Leases/single-operator control are explicitly deferred.
- **`device.put` mid-scan:** rejected by default (`behavior:"reject"` + engine busy → `busy` error). No scan-safe allowlist in v1.
- **No device value streaming.** Monitoring is the controller's (IOC's) responsibility and David's device classes don't support it; UIs poll `device.get`. Data progress has no `remote.*` events — clients watch the run in Tiled.

## 4. Lightfall-side architecture (`lightfall.remote`)

- **`lightfall/remote/service.py` — `RemoteControlService`**, registered in `ServiceRegistry` and wired during app startup alongside the existing `auth.request` registration. Registers every `remote.*` action via `IPCService.register_action` and the events via `register_event`.
- **Thin adapters, no new state:**
  - `plan.*` → the existing plan queue + plan-plugin registry (param introspection from the same `Annotated` metadata the plan UI reads).
  - `device.*` → `DeviceCatalog` + ophyd signals. `search` mirrors happi's `.search(...)`.
  - `engine.*` / run events → a subscription on the engine's document stream (start/stop docs drive `run.started`/`run.stopped` and the item_id→run_uid resolution). The busy check reads the same engine source of truth the UI uses.
- **Threading:** action handlers arrive on the IPC thread; anything touching the RunEngine or ophyd goes through the same thread-safe entry points the panels use. `device.put` completion waits run on an executor with a timeout — never blocking the NATS loop.
- **Trust plumbing:** a handler-level guard rejects `remote.*` from un-trusted senders (`denied`). Session-scoped state (trust table, private-channel tokens) lives with the existing trust machinery in `IPCService`/application; logout clears it (principle 6).
- **Headless test client** ships with the core tests (raw nats-py, mirrors what Spec #2's `LightfallClient` will do) and doubles as the contract's reference consumer.

## 5. Testing

- **Unit (lightfall):** each action handler against fakes (FakeIPC pattern; mock engine/queue/DeviceCatalog); trust guard (untrusted → `denied`); busy/reject paths; put wait/timeout paths; session-logout clears trust + channels.
- **e2e (lightfall):** local nats-server (`LocalNatsServer`) + sim devices + real RunEngine: headless client authenticates, searches devices, walks components, get/put round-trips (put completion verified against an actual slow-moving sim positioner), `plan.run` of a sim plan → run_uid → run lands in Tiled, `run.started`/`run.stopped` observed, busy rejections while a plan runs.
- **Cross-repo (later, Spec #2):** the pystxmcontrol standalone app against a live local Lightfall — the same golden-run rigor as the stxm-live smoke.

## 6. Non-goals (v1)

Device value streaming over NATS; single-operator leases; per-action authorization beyond app trust; scan-safe device allowlist for mid-scan puts; in-process short-circuiting of loopback NATS calls (Spec #3's later optimization); broker-side permission provisioning on bcgnats (production posture documented here, configured operationally); the stxm-live analysis service (unaffected by this program).

## 7. Impact on existing work

- `lightfall-pystxmcontrol` acquisition layer (wrappers, flyer, plans, viz): unchanged, becomes the hardware-adjacent execution layer this design assumes.
- Our native panels (scan, spectrum): their Tiled read-side/streaming logic gets ported back into David's widgets under Spec #2; the panels themselves are superseded by Spec #3's thin wrappers.
- `stxm-live` (external analysis, 2026-07-09): unaffected — it reads Tiled and speaks its own `stxm.*` namespace regardless of who triggered the run.
