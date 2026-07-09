# STXM-Live — External NATS Analysis Service (Option-5 Layer 3)

**Date:** 2026-07-09
**Status:** Approved design (Ron), pending implementation plan
**Companion to:** `2026-07-07-stxm-lightfall-option5-design.md` (this is the deferred "analysis slot", spec §2/§6 Phase E)
**Repos:** NEW `github.com/als-controls/stxm-live` (private) + `lightfall-pystxmcontrol` (in-Lightfall half). `lightfall` core: no changes.

## 1. Context and goal

Option-5's third layer: demonstrate an **external headless analysis process** communicating with Lightfall over **NATS**, mirroring `xpcs_live` and Tsuchinoko. Unlike a throwaway demo, this is the **seed of David Shapiro's real STXM analysis service** — a standalone repo with production shape (CLI + config), structured so David grows it into full stack analysis (OD / PCA / clustering), while v1 proves the wiring end-to-end.

The feature completes the option-5 story: acquisition (Phase A) → Tiled → **external analysis over NATS**, with results surfaced back in Lightfall.

### 1.1 Precedents (grounded)

- **XPCS** (`lightfall-endstation-7011` + external `lbl-camera/xpcs_live`): in-Lightfall panel + binding controller; external headless correlator; three transports (EPICS PV images, inline NATS `xpcs.g2.updated`, Tiled snapshots). Bind triple `{run_uid, tiled_url, tiled_api_key}` published on RE start/stop.
- **Tsuchinoko** (`lightfall/acquire/nats_bridge.py` + `plans/adaptive.py`): external engine reads Tiled, publishes on its own subject; bind carries the same triple + `lightfall_prefix`.
- **Lightfall IPC** (`lightfall/ipc/service.py`, `docs/developer-guide/ipc-client-guide.md`): NATS bus, `auth.request` handshake → `{tiled_token, tiled_url}`, default prefix `als.7011`, default broker `nats://bcgnats.als.private.lbl.gov:4222` (TLS), local dev broker via `ipc_use_local_nats` → `LocalNatsServer` on `127.0.0.1:4222` (core NATS, plaintext, no JetStream).

## 2. Architecture — three layers, two repos

Cross-repo (like Phase 2c), joined by ONE versioned NATS contract (§3):

```
 lightfall-pystxmcontrol (in-Lightfall)              github als-controls/stxm-live (NEW, private, own env)
 ─────────────────────────────────────              ─────────────────────────────────────────────────────
 StxmRunBinder  ──stxm.run.bind {uid,url,key}──────▶ nats.service
   (RunEngine start/stop subscription)                 │ reads <run>/primary/<data_field> from Tiled (poll)
 StxmAnalysisClient (QObject/IPCService)               │ IntensitySpectrumReducer (incremental I(E))
 StxmSpectrumPanel ◀─stxm.spectrum.updated {I(E)}───── │
   (Enable-analysis toggle + live pyqtgraph plot)      │
                      ◀────stxm.run.stop───────────────┤ (on stop) StackReducer wraps pystxmcontrol
                      ◀─stxm.reduction.complete──────── └─▶ utils/stack.py → Tiled durable stream stxm_analysis/
```

- **`lightfall-pystxmcontrol`** (in-Lightfall half): a run-binder, a thin client, a spectrum panel. All copied in shape from the XPCS `binding.py` / `client.py` / panel. Registered as a `PanelPlugin`. No lightfall-core change.
- **`als-controls/stxm-live`** (new, private): the headless service — `nats/`, `tiled/`, `analysis/`, a re-implemented read-side `contract.py`, CLI + pydantic config. Runs in its own environment with pystxmcontrol installed (so `stack.py` imports cleanly; the numpy<2 pin is contained to this env and is not a Lightfall concern — an eventual numpy upgrade in pystxmcontrol is optional cleanup, out of scope here).

### 2.1 Boundary rules (normative)

1. **JSON-only over NATS.** Frames and full arrays NEVER cross the bus. Only small results (the I(E) spectrum = nE scalars) go inline; full arrays go via Tiled.
2. **stxm-live does NOT import `lightfall_pystxmcontrol` or `lightfall`.** It talks raw `nats-py` + `tiled.client`, and re-implements the read-side contract (§3.4) against this doc — exactly as `xpcs_live` re-implements against its design doc. The only cross-package dependency stxm-live has is on `pystxmcontrol` (for `StackReducer`).
3. **The binder never blocks or breaks the RunEngine** — its document callback is wrapped in try/except (XPCS pattern).
4. **Never subscribe to a scalar Tiled column facet** (500s + hangs). stxm-live reads the flyer **array** node by polling; the panel renders from NATS events, not Tiled.
5. **Contract is versioned.** `contract_version` travels in the start doc and the bind; a mismatch is a logged refusal, not a crash.

## 3. The NATS contract (load-bearing; documented verbatim in BOTH repos)

Namespace `stxm.*`. In-Lightfall clients use `IPCService` (prefixing handled by the service); the external raw client prefixes every subject with the configured `lightfall_prefix` (default `als.7011.`).

### 3.1 Subjects and payloads

| Subject (suffix) | Direction | Kind | Payload |
|---|---|---|---|
| `auth.request` (core, reused) | service→LF | req/reply | req `{app_name:"stxm-live", app_version}` → reply `{status:"approved", tiled_token, tiled_url, session_id}` |
| `stxm.run.bind` | binder→service | publish | `{run_uid, tiled_url, tiled_api_key, lightfall_prefix, contract_version}` |
| `stxm.run.stop` | binder→service | publish | `{run_uid}` |
| `stxm.spectrum.updated` | service→LF | publish | `{run_uid, energies:[float], intensity:[float\|null], energies_done:int, seq:int}` |
| `stxm.status` | service→LF | publish | `{run_uid, state:"binding"\|"reducing"\|"idle", energies_done:int, total:int}` |
| `stxm.error` | service→LF | publish | `{run_uid, error:str}` |
| `stxm.reduction.complete` | service→LF | publish | `{run_uid, tiled_path:str, products:[str]}` |
| `_stxm.discover` / `stxm.meta.actions` / `stxm.meta.events` | service | req/reply | discovery parity with XPCS (service advertises its own actions/events) |

- `intensity` is aligned index-for-index with `energies` (length nE); entries for not-yet-acquired energies are `null` (JSON) / NaN. `seq` increments per publish so a late subscriber can order updates; `energies_done` is the count of non-null entries.
- `bind`/`stop` are fire-and-forget PUBLISHES (run-doc handlers must not block on replies) — the XPCS convention.
- `lightfall_prefix` is threaded in the bind (Tsuchinoko convention) so the external service can build correctly-prefixed reply/event subjects without hardcoding.

### 3.2 Auth + connect (external service)

At startup: `nats.connect(nats_url, tls=…)` (plaintext for the local dev broker), then `request("{prefix}.auth.request", {"app_name":"stxm-live"})` → `{tiled_token, tiled_url}` for the base Tiled URL. Per-run credentials arrive in each `stxm.run.bind`. On a Tiled 401, re-run `auth.request` (keys ~1wk TTL; Lightfall restart invalidates old keys).

### 3.3 Tiled durable record

The service writes results into the **bound run** via `bluesky_tiled_plugins._RunWriter` (the machinery Tsuchinoko's `TiledPublisher` and `xpcs_live` use), lazily opening a **`stxm_analysis/`** stream on first write (so bound runs with no output get no stream pollution). Contents:
- `spectrum` — `{energies, intensity}` (the final I(E)).
- The `StackReducer` products at run-complete (e.g. `od`, `components`, `maps` — whatever stack.py yields), each as an array node.

### 3.4 Read-side contract (re-implemented in stxm-live, per option-5 spec §4)

The service reads the energy-stack the Phase-A plan produced:
- Start doc carries `stxm: {contract_version, shape:[nE,ny,nx], energies:[…], dwell_ms, x_extent, y_extent, x_motor, y_motor, energy_motor, data_field}`.
- Data node: `run["primary"][data_field]` — a growing `(k, nx)` 2-D array, one row per acquired line.
- Ordering: `seq_num = iE*ny + iy + 1`; row index `= seq_num - 1`; `(iE, iy) = divmod(row, ny)`.
- Reshape: `cube_from_rows(rows, [nE,ny,nx])` → NaN-filling unacquired lines. stxm-live ships its own minimal copy of this (≈10 lines) guarded by `contract_version == 1`.

## 4. stxm-live service internals

```
stxm-live/
  pyproject.toml            # hatch + hatch-vcs; deps: nats-py, tiled[client], numpy, pydantic, click, pystxmcontrol (own env)
  src/stxm_live/
    contract.py             # read-side: parse start.stxm, cube_from_rows, decode_line_index, version guard
    nats/
      config.py             # pydantic AppConfig (nats_url, lightfall_prefix, poll_interval_s, app_name, ...)
      client.py             # nats-py connect + auth.request + prefixed pub/sub helpers
      service.py            # event loop: on bind -> track; poll Tiled; publish spectrum; on stop -> reduce+write
    tiled/
      connect.py            # from_uri(tiled_url, api_key=...); 401 -> re-auth hook
      reader.py             # poll the (k,nx) rows node; yield newly-complete energy frames
      writer.py             # _RunWriter wrapper; lazily open stxm_analysis/ stream; write spectrum + products
    analysis/
      base.py               # Reducer protocol: incremental(cube_so_far, energies_done) + finalize(cube)
      spectrum.py           # IntensitySpectrumReducer: per-energy frame-mean -> I(E) (numpy only)
      stack_adapter.py      # StackReducer: wraps pystxmcontrol utils/stack.py for the run-complete full reduction
    cli.py                  # `stxm-live run --nats-url ... --lightfall-prefix als.7011 --config config.yml`
  tests/                    # unit + e2e smoke (see §7)
  README.md
```

- **v1 reducer scope**: `IntensitySpectrumReducer` computes the per-energy **whole-frame mean** transmitted intensity (ROI-restricted spectra are a documented extension — ROI would arrive over a future `stxm.roi.set` action, mirroring XPCS; NOT in v1). `StackReducer` calls stack.py on the finished cube at run-stop.
- **Incremental cadence**: `reader` polls `run["primary"][data_field]` every `poll_interval_s`; when `rows >= (iE+1)*ny` for the next unfinished energy, that frame is complete → reduce → publish. Polling (not WS-subscribe) keeps the headless service simple and avoids the scalar-facet trap.

## 5. In-Lightfall half (`lightfall-pystxmcontrol`)

New files (mirroring XPCS `xpcs/`):
- `stxm_analysis_client.py` — `StxmAnalysisClient(QObject)` over `get_ipc_service()`: subscribes `stxm.spectrum.updated` / `stxm.status` / `stxm.error` → Qt signals (`spectrumUpdated`, `statusChanged`, `errorReceived`); `bind_run(uid, tiled_url, tiled_api_key)` / `run_stop(uid)` publishers. Injectable `ipc=` for headless tests. Degrades to no-op when `ipc is None`.
- `stxm_binder.py` — `StxmRunBinder`: on `enable()`, subscribes `get_engine().RE`; on `start` doc publishes `stxm.run.bind` with credentials (via `ServiceRegistry`→`TiledService` + `SessionManager.get_api_key("tiled")`, mirroring XPCS `binding.py` / adaptive `_get_tiled_credentials`); on `stop` publishes `stxm.run.stop`. Document callback wrapped in try/except.
- `stxm_spectrum_panel.py` — `StxmSpectrumPanel(BasePanel)` + `StxmSpectrumPanelPlugin(PanelPlugin)`: an **Enable analysis** toggle that arms/disarms the binder (the `run.bind` published on the next run start IS the "start analyzing" signal — v1 has no separate `processing.enable` action), and a pyqtgraph plot of I(E) fed by `StxmAnalysisClient.spectrumUpdated`. Injectable deps (`client=`, `binder=`) per the XPCS test pattern. Manifest gains `PluginEntry("panel", "stxm_spectrum", …, preload=True)`.

## 6. Data flow (one run)

1. Enable-analysis toggle in `StxmSpectrumPanel` → `StxmRunBinder.enable()` (RE subscription).
2. Scan starts → binder publishes `stxm.run.bind {uid, tiled_url, tiled_api_key, lightfall_prefix, contract_version}`.
3. Service opens the run in Tiled, polls the rows node; as each energy's `ny` lines complete → frame-mean → append to I(E) → publish `stxm.spectrum.updated`.
4. Panel client re-emits → live pyqtgraph spectrum grows energy-by-energy.
5. Scan stops → binder publishes `stxm.run.stop` → service runs `StackReducer` (stack.py) on the complete cube, writes `spectrum` + products to the `stxm_analysis/` Tiled stream, publishes `stxm.reduction.complete`.

## 7. Error handling, auth, broker/env

- **Dev/CI broker**: local `nats-server` (core NATS, plaintext) via `ipc_use_local_nats` / `LocalNatsServer`; service connects `nats://127.0.0.1:4222`, no TLS ctx. Production: bcgnats TLS.
- **Auth**: `tiled_token` is a ~1wk API key; Tiled 401 → re-`auth.request`. Per-run key from the bind.
- **Degrade**: no NATS/Tiled → panel toggle shows disconnected, binder no-ops; service logs + idles. Partial runs (abort) → spectrum carries NaNs; `StackReducer` runs on the acquired cube or is skipped with a logged `stxm.status`. Contract-version mismatch → logged refusal, no crash.
- **Never blocks the RunEngine**; JSON-only over NATS.

## 8. Testing

- **stxm-live unit**: `IntensitySpectrumReducer` on a synthetic `(nE,ny,nx)` cube (incremental + finalize); `StackReducer` on a fixture (or skipped/xfail if pystxmcontrol analysis fixtures are heavy); `contract.py` read-side (reshape, version guard); `nats/client` against a fake broker; `tiled/reader` + `writer` against a local Tiled.
- **In-Lightfall unit** (pytest-qt, injectable deps — XPCS pattern): binder (fake IPC + fabricated start/stop docs → asserts bind/stop payloads); client (fake IPC emits events → Qt signals); panel (toggle arms binder; `spectrumUpdated` → plot curve).
- **Cross-repo e2e smoke** (in stxm-live): start local `nats-server` + local streaming Tiled; write a golden energy-stack run to Tiled (reuse the Phase-A golden fixture / `stxm_energy_stack` plan output); run the service; assert it (a) binds, (b) publishes `stxm.spectrum.updated` with correct I(E) for a known synthetic cube, (c) writes the `stxm_analysis/` Tiled stream, (d) publishes `stxm.reduction.complete`. Mirrors the Phase-A smoke's rigor (loud assertions, clean teardown).

## 9. Scope / non-goals (v1)

**In v1**: the two-repo skeleton; bind/stop/spectrum/status/error/reduction.complete subjects; incremental whole-frame I(E) reducer; StackReducer wrapping stack.py at run-complete; inline-NATS live + Tiled durable; the in-Lightfall binder + client + spectrum panel; local-broker e2e smoke.

**Deferred**: ROI-restricted spectra (`stxm.roi.set` action); reading the durable Tiled stream back into the panel for completed runs (v1 panel is live-only); a proactive-monitor `MonitorFeed` over the results (belongs to the separate proactive-monitor track); real-hardware / non-sim runs; production bcgnats deployment + packaging/CI for stxm-live; live ptychography reconstruction; the numpy-2 upgrade in pystxmcontrol.

## 10. Repo bootstrap note

`github.com/als-controls/stxm-live` does not exist yet — it must be created (private) before or during implementation. The implementation plan should either create it via `gh repo create als-controls/stxm-live --private` (Ron drives, per his push pattern) or scaffold locally under `~/PycharmProjects/ncs/stxm-live` and let Ron create the remote. The in-Lightfall half lands on `lightfall-pystxmcontrol` `main` (kept local; Ron drives PRs).
