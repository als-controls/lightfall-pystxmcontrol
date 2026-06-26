# Unified Tiled-Streaming Visualization Updates + STXM Live Map (Phase 2c)

**Date:** 2026-06-25
**Status:** Design — pending implementation plan
**Author:** Ron Pandolfi (with Ayaka)
**Scope:** Cross-repo — the unified streaming mechanism lives in **lightfall-core**
(`~/PycharmProjects/ncs/lightfall`); the STXM consumer lives in **lightfall-pystxmcontrol**.

## Context

Phase 2a added a simulated STXM *fly* scan (`PystxmLineFlyer` over `getLine`, one `event_page`
per raster line); Phase 2b made it launchable from Lightfall's UI. Phase 2c makes the fly-scan
**visible**: the STXM map renders live as lines arrive, and — per the unifying decision below — it
does so through a **new streaming update path that replaces polling for *all* Lightfall
visualizations**, not just STXM.

Today Lightfall's `VisualizationPanel` updates every visualization by a **2-second `QTimer`** that
calls `BaseVisualization.refresh()`, which re-reads the Tiled node. Lightfall already auto-writes
every run to Tiled via a patched `TiledWriter` (builds appendable-table schemas from descriptor
`data_keys` dtype hints — not pyarrow inference — and writes array data via `patch(extend=True)`),
and obtains an authenticated Tiled client from the `TiledService` singleton.

A prior investigation + a **proven local spike** (Tiled 0.2.9) established the streaming primitive:
a producer appends array chunks via `ArrayClient.patch(line, offset=(row,0), extend=True)` and a
separate subscriber receives each chunk **live over WebSocket as an inline `array-data` payload**
(no refetch), provided the **server has a `streaming_cache` configured** (`streaming_cache: {uri:
"memory"}` / `TILED_STREAMING_CACHE_URI`). Tiled 0.2.9 streaming covers `array-data`, `table-data`,
and `container-child-created` (with per-structure schemas). The deployed `als-tiled` server is
confirmed current and has the streaming support.

### Verified universality precondition

Every shipped Lightfall visualization (`HeatmapVisualization`, `Plot1DVisualization`,
`TableVisualization`, `ScatterVisualization`, `AdaptivePlotVisualization`, `ScanViewerVisualization`,
`ImageStackVisualization`, and the adaptive heatmap) reads only **array** structures (`ArrayClient`)
or **table** columns — both streamable in 0.2.9. None read sparse/awkward/xarray. So a streaming-only
update path is achievable across the entire current viz set.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Update mechanism | **Streaming-only** — Tiled WebSocket push replaces the 2s poll for ALL visualizations | The unifying requirement; one update path, not a STXM special case |
| Fallback | **None (all-or-nothing)** | If push can't work universally it isn't worth doing; the poll timer is removed, not kept as a fallback |
| `BaseVisualization` contract | Add `on_stream_update(update)`, called on the **GUI thread**; **default implementation calls `self.refresh()`** | Every existing viz becomes push-driven with zero per-viz changes; a viz can override to apply the inline payload efficiently |
| STXM viz | A new `BaseVisualization` subclass that **overrides `on_stream_update`** to blit each pushed line into a growing 2-D image | Showcases efficient inline-payload use; the live STXM map |
| Threading | Tiled subscription callback (bg daemon thread) → **Qt signal** → GUI-thread slot | Qt is never touched off the GUI thread |
| Persistence | **Reuse** the existing patched `TiledWriter` (verify it yields a streamable map array; no new writer unless it doesn't) | The write path already does `patch(extend=True)`; don't reinvent |
| Auth / client | **Reuse** `TiledService.get_instance().client` | Existing authenticated client (API-key/Keycloak/none) |
| Lightfall core | **Modified** (the viz subsystem) | The unified mechanism is inherently core; first phase to change lightfall-core |
| HDF5 | **Out** | Dropped — not a requirement |

## Architecture

```
BlueskyEngine run ─▶ patched TiledWriter (existing, auto-subscribed) ─▶ Tiled
                       arrays via patch(extend=True), tables          (als-tiled, streaming_cache on)
                                                                              │
VisualizationPanel (active run/stream/viz)                                    │ WS push:
  ├─ StreamBridge (QObject)  ── tiled.client.stream subscription ◀────────────┘  array-data /
  │     callback on bg thread ── emits Qt signal ──▶ GUI thread                   table-data /
  │                                                  │                            container-child-created
  │                                                  ▼
  │                                      BaseVisualization.on_stream_update(update)
  │                                          default: self.refresh()  (re-read Tiled — every existing viz)
  │                                          STXM override: blit pushed line into 2-D image
  └─ engine doc-stream subscription (existing) ── start/stop ──▶ switch active run, (re)subscribe
        on run-switch / teardown: StreamBridge.disconnect()  (release before hide/remove)
```

The 2-second `QTimer` poll is **removed**. `refresh()` survives as (1) the initial render on
`set_run`/`set_stream` and (2) the default body of `on_stream_update`. The existing engine
doc-stream subscription (start/stop → run switching) stays.

## Components

### lightfall-core

**`StreamBridge` (new, e.g. `lightfall/visualization/stream_bridge.py` or under `services/`)**
- A `QObject` that, given a Tiled node (the active run/stream container) + an authenticated client,
  opens a `tiled.client.stream` subscription and registers a callback.
- The callback (bg thread) emits a Qt signal carrying the decoded update; a GUI-thread slot forwards
  it to the active viz's `on_stream_update`.
- `connect()` / `disconnect()` lifecycle; idempotent; safe teardown. Reuses the SOCKS-proxy patch
  already installed in `TiledService` for off-LBL clients.
- **Spike-pinned unknown:** the exact subscription surface for a *container/run* (vs the per-array
  `ArrayClient.subscribe()` the spike proved). Tiled 0.2.9 exposes `container-schema` +
  `container-child-created`, so a container subscription should exist — confirm endpoint/API + the
  routing of child `array-data`/`table-data` to the right viz.

**`BaseVisualization` (modify `lightfall/visualization/base_visualization.py`)**
- Add `def on_stream_update(self, update) -> None:` with a **default body `self.refresh()`**.
- `refresh()` and `set_run`/`set_stream` unchanged in signature.

**`VisualizationPanel` (modify `lightfall/ui/panels/visualization_panel.py`)**
- **Remove** the 2-second `QTimer` and `_on_refresh_tick`.
- On run/stream activation: create/point a `StreamBridge` at the active Tiled node; connect its
  GUI-thread signal to the active viz's `on_stream_update`; do one initial `refresh()`.
- On run-switch / panel teardown: `StreamBridge.disconnect()` **before** hiding/removing the widget
  (theater-teardown ordering).

### lightfall-pystxmcontrol

**`StxmMapVisualization(BaseVisualization)` (new) + `PanelPlugin` registration**
- `can_handle(run)` scores high when the run exposes the STXM map array (by name/structure).
- `set_run`/`set_stream`: open the map `ArrayClient`; initial `refresh()` renders the rows present.
- `on_stream_update(update)`: **override** — when the update is `array-data` for the map, blit the
  inline line payload into the growing 2-D image at its `offset` row (no full re-read).
- Registered via a `PluginEntry("panel", ...)` in the package manifest (alongside the Phase-2b
  `device_backend` + `plan` entries).

**Persistence verification (no new writer expected)**
- Confirm the existing patched `TiledWriter` turns the fly-scan's array-per-line `event_page`
  (`STXMLineFlyer[nx]` per event) into a Tiled **array** that grows by `patch(extend=True)` into a
  usable 2-D `(ny, nx)` map. If it instead yields a 1-D-per-event internal column (the
  `tiled_writer_internal_array_shape` hazard), apply the **minimal** fix (flyer descriptor
  adjustment or a thin array-writer callback via the open `engine.subscribe`) — decided by the spike,
  not assumed here.

## Data flow

1. Plan runs; patched `TiledWriter` writes each line into the Tiled map array via `patch(extend=True)`.
2. With the run active, `StreamBridge` is subscribed to the run/stream node; the Tiled server pushes
   an `array-data` (inline payload) per write.
3. Bridge callback (bg thread) → Qt signal → GUI thread → active viz `on_stream_update`.
4. Existing viz: default `on_stream_update` → `refresh()` re-reads the Tiled node and redraws. STXM
   map viz: override blits the pushed line into the 2-D image directly.
5. Run switch / teardown: bridge disconnects before the widget is hidden/removed.

## Streaming-only stance & universality

- The poll timer is removed; there is no fallback. The mechanism is required to drive **every**
  current visualization (all read array/table — both streamable). The implementation's acceptance
  gate is that each shipped viz updates via push with no regression.
- Hard dependency: the connected Tiled server MUST have `streaming_cache` enabled (als-tiled is
  confirmed). If a deployment's server lacks it, live updates do not occur — that is the accepted
  consequence of all-or-nothing, not a code path to soften.
- Boundary: a *future* viz reading a non-streamable structure (sparse/awkward/xarray) would not be
  covered until Tiled streaming supports it; such a viz is out of scope here.

## Threading & lifecycle

- The Tiled subscription runs on a daemon thread (`start_in_thread`). The bridge **must** marshal to
  the GUI thread via a Qt signal before any widget touch. No viz/widget call happens off-GUI-thread.
- Subscriptions are 1:1 with the active run; switching runs disconnects the old subscription first.
  Teardown disconnects before widget hide/remove (the theater-teardown interaction rule). Guard the
  spike's observed "disconnect can hang against a cache-less server" by only subscribing when the
  server advertises streaming and bounding disconnect.

## Genuine unknowns to pin via a build spike (Task 1)

1. The **container/run-level subscription** API/endpoint in Tiled 0.2.9 and how child
   `array-data`/`table-data`/`container-child-created` messages route to the correct active viz.
2. Whether the existing patched `TiledWriter` persists the fly-scan as a streamable 2-D map array
   (shape/append behavior), or needs the minimal fix above.
3. End-to-end confirmation that a push reaches a viz's `on_stream_update` on the GUI thread in the
   real `VisualizationPanel` — and that at least one existing viz (array + table) updates via push
   with the timer removed (the all-or-nothing regression gate).

## Testing

- **Core unit:** `StreamBridge` marshals a bg-thread callback to a GUI-thread signal exactly once per
  update (fake stream); `BaseVisualization.on_stream_update` default invokes `refresh()`;
  `VisualizationPanel` subscribes on activate and disconnects on teardown/switch (no leaked
  subscription).
- **Core integration (headless):** against a local streaming Tiled 0.2.9 (the proven spike harness),
  a `patch(extend=True)` write delivers an `on_stream_update` to a stub viz on the GUI thread; an
  array viz and a table viz both update via push with the poll timer removed (regression gate).
- **STXM:** `StxmMapVisualization` assembles N pushed lines into the correct `(ny, nx)` image;
  persistence verification (the fly-scan map array is present + grows in Tiled).
- Run in **Lightfall's 3.14 venv** via `.venv/Scripts/python -m pytest`, never bare `pytest`.

## Risks

1. **Server `streaming_cache` is a hard dependency.** No fallback by decision. *Mitigation:* als-tiled
   confirmed current; document the requirement; the build spike asserts it.
2. **GUI-thread marshaling correctness.** A missed marshal = a crash. *Mitigation:* a single
   `StreamBridge` choke-point; unit-test the thread→signal hop; no widget access in the callback.
3. **Subscription lifecycle leaks / teardown hangs.** *Mitigation:* 1:1 subscription per run,
   disconnect-before-hide, bounded disconnect (the spike's cache-less-hang guard).
4. **Existing-writer persistence shape.** The map may not land as a clean 2-D array. *Mitigation:*
   the spike verifies before any viz work; minimal fix if needed.
5. **Column-array read race** (`primary[col].read()` 500s mid-append). Pre-existing in the poll model;
   the default refresh-on-push inherits it, the STXM override (inline payload) sidesteps it.
   *Mitigation:* prefer `stream.read()` table-facet reads where a viz re-reads; not a new regression.
6. **Core blast radius.** Changing the shared viz update path affects every viz. *Mitigation:* the
   `on_stream_update`→`refresh()` default keeps existing viz behavior-equivalent; the regression gate
   covers array + table viz.

## Out of scope

HDF5 export (dropped); rewriting existing viz internals (they ride the default refresh-on-push);
non-visualization uses of Tiled streaming; Tiled auth changes; live updates for non-streamable
structures (sparse/awkward/xarray); faithful X velocity/trajectory, per-point encoder readback, real
hardware (`simulation=False`).
