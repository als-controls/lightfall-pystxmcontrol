# STXM on Lightfall — Option 5 Architecture & Phase A Vertical Slice

**Date:** 2026-07-07
**Status:** Approved design (Ron), pending implementation plan
**Repos:** `lightfall-pystxmcontrol` (all Phase A work), `lightfall` (no changes), `pystxmcontrol` (no changes)

## 1. Context and decision

pystxmcontrol (David Shapiro's STXM control application) and Lightfall are being
integrated. Five options were evaluated (full integration; pystxmcontrol GUI on
Lightfall services; Lightfall on pystxmcontrol server; parallel GUI + agent/logbook
via MCP; XPCS-shaped split). The decision is **option 5**, the XPCS-shaped split:

- **Absorb the GUI elements of pystxmcontrol's acquisition workflow into
  Lightfall** as plugin panels/visualizations, re-implemented on Lightfall idioms.
- **Bluesky owns scan orchestration.** pystxmcontrol's executor server, asyncio
  scan engine, ZMQ protocol, and GUI are not used.
- **Analysis is out of Lightfall entirely.** When live reduction is needed
  (ptychography reconstruction, stack chemometrics), it runs as a separate
  headless NATS-aware process whose *results* are written to Tiled — the
  `xpcs_live` shape. Until then there is no analysis component at all.
- **Tiled is the boundary.** All Lightfall visualization reads Tiled.
  pystxmcontrol data structures (`writeNX.stxm`, `.stxm` files, config dicts)
  appear in **no** contract on our side.

Precedents: the Tsuchinoko rescope and the XPCS integration
(`lightfall-endstation-7011` panel + external `xpcs_live` service + NATS/Tiled
transports), and this repo's own Phases 1/2a/2b/2c (ophyd-async device wrapping,
sim line flyer, plan UI binding, Tiled-streaming live map).

### 1.1 Endgame

The Lightfall plugin supersedes pystxmcontrol's GUI for acquisition. David's app
persists as his own analysis tool on his side of the Tiled boundary. His
executor/scan engine retires from daily operation only when device breadth, scan
parity, and hardware truth (Phases B–D) are proven — nothing in this design
requires ripping it out now, and his app keeps working unchanged throughout.

## 2. Architecture (umbrella)

Four tracks, decoupled by the Tiled contract:

| Track | Where | What |
|---|---|---|
| Acquisition + controls | `lightfall-pystxmcontrol` plugin | ophyd-async devices over pystxmcontrol drivers; Bluesky plans; STXM panels + visualizations |
| Data | Tiled (existing `TiledWriter` path) | bluesky-native run layout (§4); system of record for Lightfall-acquired runs |
| Analysis slot (future) | separate headless repo/process | NATS-aware service; consumes runs from Tiled, writes reduced results back to Tiled; Lightfall renders results through Tiled |
| David's independent tracks | David-led | logbook entries → Lightfall `LogbookClient`; his agent work → `AgentPlugin`(s); no dependency on the tracks above |

### 2.1 Boundary rules (normative)

1. No analysis in the Lightfall process. Visualizations are numpy-only
   measurement evaluation (existing Lightfall boundary).
2. No pystxmcontrol GUI code is imported. GUI *functions* are absorbed,
   re-implemented on Lightfall idioms (`BasePanel`, `BaseVisualization`,
   pyqtgraph). His PySide widgets are coupled to his client protocol and
   `writeNX` buffers; lifting code wholesale would smuggle his data structures in.
3. No `writeNX.stxm` object, `.stxm` file, or pystxmcontrol config dict in any
   contract. The contract is the bluesky document stream and its Tiled
   representation (§4).
4. Plugin→driver imports stay lazy and minimal (current pattern:
   factory-function-local imports in `config.py`), pinned to the
   `als-controls/pystxmcontrol` fork until the lazy-import guard merges upstream.
5. Live viz subscribes only to array nodes or a stream's `internal` table node —
   never a scalar column facet (known 500/hang).

### 2.2 GUI absorption inventory

pystxmcontrol GUI elements and their absorption targets. Phase A absorbs the
starred rows; Phase C audits the rest against what Lightfall core already
provides and absorbs only genuine gaps.

| pystxmcontrol element | Absorption target | Phase |
|---|---|---|
| Scan/region definition (`scanDef.py`, `regionDef_UI.py`) ★ | STXM scan-definition panel (§3.3) | A |
| Energy-range definition (`energyDef.py`) ★ | same panel, energy-ranges editor | A |
| Channel selection ★ | same panel, detector picker | A |
| Live image / stack view ★ | `StxmStackVisualization` (§3.4) | A |
| Monitor view (live counts) | audit vs core device panels | C |
| Motor/beamline panel (`motor_panel.py`) | audit vs core device panels | C |
| Data browser (`data_browser_widget.py`) | audit vs Lightfall run browsing + als-data-portal | C |
| Analysis widget / stack analysis | **not absorbed** — analysis slot (§2, future) | — |

## 3. Phase A: vertical slice

Thin cut through acquisition → Tiled → Lightfall GUI. Zero changes to
`lightfall` core and to David's repo.

**Demo / acceptance criterion:** in Lightfall (sim): open a prior sim image in
the STXM scan panel, draw a region, define energy ranges, launch; watch the
stack build live in the stack visualization; browse it by energy when done.
Everything through Tiled; no pystxmcontrol GUI code imported.

### 3.1 Sim energy axis

A third device in `pystxm_happi.json`: name `energy`, class `PystxmAxis`
wrapping the sim `xpsMotor` (same factory pattern as the existing axes, new
entry in `config.py`). Explicitly a **placeholder**: the real wrap of
pystxmcontrol's `derivedEnergy` (zone-plate A0/A1 focus physics) is Phase B.
The slice needs an energy-shaped `Movable`, not correct optics.

### 3.2 `stxm_energy_stack` plan

New plan in `plans.py` + a UI-annotated adapter in `plan_plugin.py`
(same pattern as `stxm_fly_raster`), registered via a second `PluginEntry
(type_name="plan")`.

- **Structure:** one run. Outer loop over `energies`; per energy:
  `bps.mv(energy_axis, E)`, then the existing per-row line-fly machinery
  (`flyer.prepare → bps.kickoff → bps.complete → bps.collect`) over `ny` rows.
  Emits `nE × ny` line events of shape `(nx,)` into the single `primary` stream.
- **Parameters (intent — exact signature at plan time):** flyer + energy-axis
  device selection (`DeviceFilter`-annotated), `energies: list[float]`
  (pre-expanded by the panel from ranges), inner-raster geometry
  (`x_start/x_stop/nx`, `y_start/y_stop/ny`), single `dwell`.
  Per-range dwell is deferred to Phase C (noted in §6).
- **Metadata:** start doc carries the `stxm` block (§4.1).

### 3.3 STXM scan-definition panel

`STXMScanPanel(BasePanel)` + `StxmScanPanelPlugin(PanelPlugin)`, registered via
`PluginEntry(type_name="panel", name="stxm_scan")`. Composition (XPCS panel is
the idiom precedent — injectable deps for headless pytest-qt):

- **Context image, through Tiled:** loads a prior run's map via Lightfall's
  `TiledService` client and renders it with a plain pyqtgraph `ImageItem`.
  The prior run's start-doc extents (§4.1) place the image in **motor
  coordinates**, so drawn regions are directly scan coordinates. With no prior
  run: blank canvas with manual extent entry.
- **Region definition:** pyqtgraph `RectROI` on the image (XPCS
  `ROIOverlayManager` idiom). Slice scope: **one** region (multi-region tiling
  is Phase C); region → `x_start/x_stop/y_start/y_stop`, plus `nx/ny` (or
  step-size) fields.
- **Energy-ranges editor:** rows of `(start, stop, n_points)` + single dwell;
  expands to the flat `energies` list passed to the plan.
- **Channel selection:** detector picker over the DeviceCatalog (trivial with
  one sim counter today; the seam is what matters).
- **Submit:** builds plan kwargs and calls `get_engine().submit(...)`. The
  panel holds no acquisition state beyond composing arguments; run state comes
  back through the normal engine/viz paths.
- **Validation:** region within the axis soft limits where limits are known
  from device metadata; non-empty energies; `nx, ny ≥ 1`. Reject at the panel
  with inline feedback before submit.

### 3.4 Stack visualization

`StxmStackVisualization(BaseVisualization)` + `PluginEntry
(type_name="visualization", name="stxm_stack")`, extending the Phase-2c live-map
pattern from 2-D to 3-D:

- `can_handle`: start-doc `plan_name == "stxm_energy_stack"` (primary signal),
  fallback probe like the existing map viz.
- Allocates `(nE, ny, nx)` from the start-doc `stxm` block; per-line stream
  updates blit into `(iE, iy)` decoded from event ordering (§4.2); falls back
  to full `refresh()` exactly as the 2-D map does.
- UI: current-energy frame display (live follows the energy being acquired) +
  an energy-index slider for browsing; `ImageItem.updateImage` with the
  existing auto-LUT behavior.
- Numpy-only display. No OD, no I0 normalization, no fitting — those live
  across the analysis boundary.

### 3.5 Explicit non-goals for Phase A

No new pystxmcontrol drivers (still the 2 wrapped families + the energy alias).
No `derivedEnergy` physics. No spiral/ptycho/focus/point-spectrum plans. No
multi-region scans, no per-range dwell. No real hardware; no
`FlyMotorInfo`/`StandardDetector`/`StreamResource` work. No lightfall-core
changes (landing open PRs #22/#1 remains Phase-0 housekeeping and does **not**
block the slice; live-streaming viz features that depend on #22 degrade to
refresh-on-complete without it). No changes to David's repo. No proposal/ESAF
metadata (`alsapi`) yet.

## 4. STXM Tiled run-layout contract (normative)

The load-bearing artifact of Phase A: the layout both the acquisition side and
any future consumer (analysis service, David's loaders, portal) code against.
Bluesky-native; versioned.

### 4.1 Start document

```yaml
plan_name: "stxm_energy_stack"
stxm:                      # single namespaced block, contract_version-gated
  contract_version: 1
  shape: [nE, ny, nx]
  energies: [...]          # setpoints, eV, length nE
  dwell_ms: <float>
  x_extent: [x_start, x_stop]   # motor units
  y_extent: [y_start, y_stop]
  x_motor: <device name>
  y_motor: <device name>
  energy_motor: <device name>
```

### 4.2 Primary stream

- One event per acquired line; data field is the flyer's device name (today the
  literal `"STXMLineFlyer"`), shape `(nx,)`.
- **Ordering contract:** `seq_num = iE*ny + iy + 1`. Consumers reconstruct
  `(iE, iy)` from `seq_num` + start-doc `shape`; no per-event energy readback
  in v1.
- The PoC's hardcoded node-key fragility is acknowledged: consumers must derive
  the field name from a single shared constant (exported by the plugin), not
  re-hardcode the string.
- Future (v2, noted not designed): a second stream with per-energy measured
  readbacks (real monochromators don't land on setpoint; analysis will
  eventually want measured E).

### 4.3 Consumer rules

- Completed runs: read the stream via its table facet (`stream.read()`);
  columns-as-facets are never read mid-run.
- Live: subscribe only to array nodes or the stream's `internal` table node.
- **Partial runs are valid data:** stop-doc `exit_status != "success"` (or a
  missing stop doc) with fewer than `nE*ny` events means unacquired lines;
  consumers fill missing rows with NaN using the ordering contract. The stack
  viz and any reader must tolerate this.

## 5. Error handling

- **Abort mid-stack** → partial cube per §4.3; viz keeps rendering acquired
  frames; no special-case code paths beyond NaN fill.
- **Tiled down / write failure** → existing `TiledWriter`/engine behavior;
  panel submission is independent of Tiled availability; stack viz shows
  nothing rather than erroring (same degrade as existing map viz).
- **Panel edge cases** → §3.3 validation; submit disabled until valid.
- **Known gotchas carried into implementation:** bluesky 1.14.6 `collect` emits
  `event_page` (unwrap `[0]`); `TiledWriter` default batch size (never 1);
  scalar-column-facet subscription ban; worktree tests need `PYTHONPATH=src`.

## 6. Later phases (roadmap one-liners, designed when scheduled)

- **Phase 0 (housekeeping, parallel):** land lightfall PR #22 + this repo's
  PR #1; prod smoke on als-tiled 0.2.11.
- **Phase B — device breadth:** config-driven happi generation from
  pystxmcontrol `motor.json`/`daq.json`; wrap remaining driver families; real
  `derivedEnergy` (A0/A1) wrap.
- **Phase C — scan & GUI parity:** spiral fly, point spectrum, focus scans;
  multi-region scans; per-range dwell; absorb remaining GUI rows from §2.2
  after the core-panel audit.
- **Phase D — hardware truth:** `simulation=False` bring-up; true continuous
  flyscan (`FlyMotorInfo`, velocity/trajectory, encoder readback);
  2-D detectors via `StandardDetector`/`StreamResource`. The substantive
  unknown; hardware-gated.
- **Phase E — analysis slot & David's tracks:** `xpcs_live`-shaped headless
  service (ptycho-live first candidate; results-to-Tiled contract extension);
  logbook/agent lift (David-led); STXM monitor feed once lightfall
  `feature/proactive-monitor` merges.
- **Cutover criterion:** pystxmcontrol's executor retires from daily ops only
  when B + C + D are proven at the beamline.

## 7. Testing

- **Plan documents test** (pytest, sim RE): event count `nE*ny`, ordering
  contract, `stxm` start-doc block correctness, `event_page` handling.
- **Panel tests** (headless pytest-qt, injectable deps per XPCS precedent):
  region→kwargs mapping incl. coordinate frame from extents, energy-range
  expansion, validation gating, submit path with a fake engine.
- **Viz tests** (document replay, Phase-2c regression pattern): allocation from
  start doc, per-line blit addressing `(iE, iy)`, partial-run NaN fill, slider.
- **Contract fixture:** a golden sim run (documents JSON) checked into
  `tests/`, doubling as the executable definition of §4 for future consumers.
- **E2E smoke:** `scripts/smoke_energy_stack.py` mirroring
  `smoke_gridscan.py` — run the plan through `BlueskyEngine`, verify the Tiled
  node layout, print shape/min/max.
