# STXM on Lightfall — Option 5 Architecture & Phase A Vertical Slice

**Date:** 2026-07-07 (rev 2, post adversarial fact-check)
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
| Channel selection ★ | same panel, detector picker (Phase A: flyer selection, §3.3) | A |
| Live image / stack view ★ | `StxmStackVisualization` (§3.4) | A |
| Monitor view (live counts display) | audit vs core device panels (GUI only — distinct from the Phase E proactive-monitor *feed*) | C |
| Motor/beamline panel (`motor_panel.py`) | audit vs core device panels | C |
| Data browser (`data_browser_widget.py`) | audit vs Lightfall run browsing + als-data-portal | C |
| Analysis widget / stack analysis | **not absorbed** — analysis slot, Phase E (§6) | E (slot) |

## 3. Phase A: vertical slice

Thin cut through acquisition → Tiled → Lightfall GUI. Zero changes to
`lightfall` core and to David's repo.

**Demo / acceptance criterion:** in Lightfall (sim): open a prior sim image in
the STXM scan panel, draw a region, define energy ranges, launch; watch the
stack build live in the stack visualization; browse it by energy when done.
Everything through Tiled; no pystxmcontrol GUI code imported. (Live streaming
viz is a lightfall-master feature — PR #22 merged 2026-07-02 — so the live
demo has no unlanded dependencies; see §3.5.)

### 3.1 Sim energy axis

A third axis (fifth device) in `pystxm_happi.json`: name `energy`, class
`PystxmAxis` wrapping the sim `xpsMotor`. Concretely: a new entry in
`config.DEFAULT_AXES` with **eV-scale soft limits** (e.g. 250–2500), then
regenerate `pystxm_happi.json` via `scripts/build_pystxm_happi_db.py` (the JSON
is generated from `DEFAULT_AXES`, not hand-edited). The limit values matter:
`xpsMotor.moveTo` enforces `axis_config` soft limits **even in simulation**
(raises `SoftwareLimitError`), so an entry cloned from the ±100 sample axes
would reject realistic eV setpoints and kill the plan at the first `bps.mv`.

Explicitly a **placeholder**: the real wrap of pystxmcontrol's `derivedEnergy`
(zone-plate A0/A1 focus physics) is Phase B. The slice needs an energy-shaped
`Movable`, not correct optics.

### 3.2 `stxm_energy_stack` plan

New plan in `plans.py` + a UI-annotated adapter in `plan_plugin.py`
(same pattern as `stxm_fly_raster`), registered via a second `PluginEntry
(type_name="plan")`.

- **Structure:** one run. Outer loop over `energies`; per energy:
  `bps.mv(energy_axis, E)`, then the existing per-row line-fly machinery
  (`flyer.prepare → bps.kickoff → bps.complete → bps.collect`) over `ny` rows.
  Emits `nE × ny` line events of shape `(nx,)` into the single `primary` stream.
- **Parameters (intent — exact signature at plan time):** `flyer` (the
  detector/channel choice, `DeviceFilter`-annotated), `energy_axis` and
  `y_axis` device selections, `energies: list[float]` (pre-expanded by the
  panel from ranges), inner-raster geometry (`x_start/x_stop/nx`,
  `y_start/y_stop/ny`), `dwell_ms: float` (milliseconds end-to-end; converted
  at the flyer boundary if a driver needs seconds). Per-range dwell is
  deferred to Phase C (noted in §6).
- **Metadata:** start doc carries the `stxm` block (§4.1). Provenance of the
  recorded names: `data_field` and `x_motor` come from the flyer instance
  (its bluesky `name` and its fast-axis attribute respectively); `y_motor`
  and `energy_motor` from the corresponding device parameters.

### 3.3 STXM scan-definition panel

`STXMScanPanel(BasePanel)` + `StxmScanPanelPlugin(PanelPlugin)`, registered via
`PluginEntry(type_name="panel", name="stxm_scan")`. The XPCS panel is the idiom
precedent **for composition and testability only** (injectable deps for
headless pytest-qt; `RectROI` overlay management) — XPCS reads no Tiled data;
the Tiled-read precedent is core's `VisualizationPanel._resolve_entry`.

- **Context image, through Tiled:** loads a prior run's map via
  `TiledService.get_instance().client[uid]` (the `_resolve_entry` idiom,
  including its disconnected→None and writer-lag KeyError handling). The uid
  comes from Lightfall's run selection (the same selection/`open_run` path the
  visualization panel uses); any run *listing* uses `client.search(...)` with
  `.items()` slicing — never naive catalog iteration (known N+1 trap). Renders
  with a plain pyqtgraph `ImageItem`. The prior run's start-doc extents (§4.1)
  place the image in **motor coordinates** per the §4.1 conventions, so drawn
  regions are directly scan coordinates. With no prior run: blank canvas with
  manual extent entry.
- **Region definition:** pyqtgraph `RectROI` on the image (XPCS
  `ROIOverlayManager` idiom). Slice scope: **one** region (multi-region tiling
  is Phase C); region → `x_start/x_stop/y_start/y_stop`, plus `nx/ny` (or
  step-size) fields.
- **Energy-ranges editor:** rows of `(start, stop, n_points)` + single dwell
  (ms); expands to the flat `energies` list passed to the plan.
- **Channel selection (Phase A = flyer selection):** the detector picker over
  the DeviceCatalog feeds §3.2's `flyer` parameter — with one wrapped DAQ
  family today the choice is trivial, but the seam is real and its result is
  recorded as `data_field` (§4.1). True multi-channel selection (multiple DAQs
  per scan) is Phase C.
- **Submit:** builds plan kwargs and calls `get_engine().submit(...)`. The
  panel holds no acquisition state beyond composing arguments; run state comes
  back through the normal engine/viz paths.
- **Validation:** region within soft limits, read from the selected devices'
  **happi entry kwargs** (`axis_config` `minValue`/`maxValue` — `PystxmAxis`
  exposes no limits on the ophyd device itself); non-empty energies;
  `nx, ny ≥ 1`. Reject at the panel with inline feedback before submit.

### 3.4 Stack visualization

`StxmStackVisualization(BaseVisualization)` + `PluginEntry
(type_name="visualization", name="stxm_stack")`, built on the Phase-2c live-map
machinery (lightfall-master streaming viz):

- `can_handle`: start-doc `plan_name == "stxm_energy_stack"` (primary signal),
  fallback probe like the existing map viz.
- **Start-doc-driven allocation (new machinery):** allocates `(nE, ny, nx)`
  from the start-doc `stxm` block. This is *new* — the 2-D map has no
  production allocation path (`begin_map` is only called by tests/scripts;
  the real flow builds the image from `refresh()`). The stack viz needs the
  start doc because a 3-D cube cannot be inferred from a partial node read.
- **Live blit addressing:** per-line array-data pushes carry an offset;
  `(iE, iy) = divmod(offset_row, ny)` where `offset_row == seq_num - 1`
  (§4.2). Falls back to full `refresh()` (re-read of the Tiled node) for
  non-array updates or before allocation, as the 2-D map does.
- UI: current-energy frame display with **live-follow**: the display tracks
  the energy being acquired; user slider interaction suspends live-follow
  until a Follow toggle is re-enabled (default on at run start). Energy-index
  slider for browsing during and after the run. `ImageItem.updateImage` with
  the existing auto-LUT behavior.
- Numpy-only display. No OD, no I0 normalization, no fitting — those live
  across the analysis boundary.

### 3.5 Explicit non-goals for Phase A

No new pystxmcontrol drivers (still the 2 wrapped families + the energy alias).
No `derivedEnergy` physics. No spiral/ptycho/focus/point-spectrum plans. No
multi-region scans, no per-range dwell, no multi-channel acquisition. No real
hardware; no `FlyMotorInfo`/`StandardDetector`/`StreamResource` work. No
lightfall-core changes — lightfall PR #22 (streaming viz) **is already merged
to master** (2026-07-02), so the slice depends only on released core behavior;
what remains open is this repo's own PR #1 (`feature/stxm-live-map`), which
Phase A builds on top of (landing it is Phase-0 housekeeping, §6). No changes
to David's repo. No proposal/ESAF metadata (`alsapi`) yet.

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
  x_motor: <device name>        # from the flyer's fast axis
  y_motor: <device name>
  energy_motor: <device name>
  data_field: <flyer bluesky name>   # the primary-stream data key, e.g. "STXMLineFlyer"
```

`data_field` is the runtime source of truth for the stream's data key.
Consumers (viz, readers) MUST take the key from the start doc, not from a
hardcoded string — the flyer's bluesky name is set by the happi entry and can
be renamed in config. (The literal appears in exactly one authored place: the
happi build-script input. Today the name is duplicated across `_MAP_FIELD`,
the flyer default `name="Counter1"`, and the build script — Phase A
consolidates on the start-doc field and fixes the flyer's colliding default.)

**Coordinate conventions (normative, referenced by §3.3/§3.4/§7):** the cube
is indexed `data[iE, iy, ix]`, C-order. `ix = 0` corresponds to `x_extent[0]`
and `ix = nx-1` to `x_extent[1]`; likewise `iy` against `y_extent`. Descending
extents (`x_stop < x_start`) are legal and mean descending motor positions
with increasing index. Display orientation (which array axis is drawn
horizontal, pyqtgraph `ImageItem` axis order/transposition) is a viz
implementation detail; the *contract* order is fixed as above.

### 4.2 Primary stream

- One event per acquired line; the data field is named by the start doc's
  `stxm.data_field`, shape `(nx,)`.
- **Line events are atomic:** a row aborted mid-fly emits **no** event.
  Consumers may rely on every event having shape exactly `(nx,)`; partial
  rows do not exist in the stream.
- **Ordering contract:** `seq_num = iE*ny + iy + 1`. Consumers reconstruct
  `(iE, iy)` from `seq_num` + start-doc `shape`. For live array pushes the
  row offset equals `seq_num - 1`, so `(iE, iy) = divmod(offset_row, ny)`.
  No per-event energy readback in v1.
- Future (v2, noted not designed): a second stream with per-energy measured
  readbacks (real monochromators don't land on setpoint; analysis will
  eventually want measured E).

### 4.3 Consumer rules

- Completed runs: read the stream via its table facet (`stream.read()`);
  columns-as-facets are never read mid-run.
- Live: subscribe only to array nodes or the stream's `internal` table node.
- **Partial runs are valid data:** stop-doc `exit_status != "success"` (or a
  missing stop doc) with fewer than `nE*ny` events means unacquired lines;
  consumers fill missing rows with NaN using the ordering contract (whole
  lines only, per §4.2 atomicity). The stack viz and any reader must tolerate
  this.

## 5. Error handling

- **Abort mid-stack** → partial cube per §4.3; mid-row aborts drop the partial
  line per §4.2; viz keeps rendering acquired frames; no special-case code
  paths beyond NaN fill.
- **Tiled down / write failure** → existing `TiledWriter`/engine behavior;
  panel submission is independent of Tiled availability; stack viz shows
  nothing rather than erroring (same degrade as existing map viz).
- **Panel edge cases** → §3.3 validation; submit disabled until valid.
- **Known gotchas carried into implementation:** bluesky 1.14.6 `collect` emits
  `event_page` (unwrap `[0]`); `TiledWriter` default batch size (never 1);
  scalar-column-facet subscription ban; worktree tests need `PYTHONPATH=src`;
  sim soft limits enforced by `xpsMotor.moveTo` (§3.1).

## 6. Later phases (roadmap one-liners, designed when scheduled)

- **Phase 0 (housekeeping, parallel):** land this repo's PR #1
  (`feature/stxm-live-map`); prod smoke on als-tiled 0.2.11. (lightfall PR #22
  is already merged — no core work remains here.)
- **Phase B — device breadth:** config-driven happi generation from
  pystxmcontrol `motor.json`/`daq.json`; wrap remaining driver families; real
  `derivedEnergy` (A0/A1) wrap.
- **Phase C — scan & GUI parity:** spiral fly, point spectrum, focus scans;
  multi-region scans; per-range dwell; multi-channel acquisition; absorb
  remaining GUI rows from §2.2 after the core-panel audit.
- **Phase D — hardware truth:** `simulation=False` bring-up; true continuous
  flyscan (`FlyMotorInfo`, velocity/trajectory, encoder readback);
  2-D detectors via `StandardDetector`/`StreamResource`. The substantive
  unknown; hardware-gated.
- **Phase E — analysis slot & David's tracks:** `xpcs_live`-shaped headless
  service (ptycho-live first candidate; results-to-Tiled contract extension);
  logbook/agent lift (David-led); STXM proactive-monitor feed once lightfall
  `feature/proactive-monitor` merges (distinct from §2.2's monitor-view GUI
  row, which is a Phase C display audit).
- **Cutover criterion:** pystxmcontrol's executor retires from daily ops only
  when B + C + D are proven at the beamline.

## 7. Testing

- **Plan documents test** (pytest, sim RE): event count `nE*ny` on the happy
  path, ordering contract, `stxm` start-doc block correctness (incl.
  `data_field` and motor-name provenance), `event_page` handling, and the
  §4.2 atomicity case (abort mid-row emits no partial event).
- **Panel tests** (headless pytest-qt, injectable deps per XPCS precedent):
  region→kwargs mapping against the §4.1 coordinate conventions (incl.
  descending extents), energy-range expansion, soft-limit validation from
  happi kwargs, submit path with a fake engine.
- **Viz tests** (stub stream-update pattern per `test_stxm_map_viz.py`, plus
  new document-driven tests for the start-doc allocation path): allocation
  from the `stxm` block, per-line blit addressing `(iE, iy)` via the offset
  rule, partial-run NaN fill, slider + live-follow suspension.
- **Contract fixture:** a golden sim run (documents JSON) checked into
  `tests/`, doubling as the executable definition of §4 for future consumers.
- **E2E smoke:** `scripts/smoke_energy_stack.py` mirroring
  `scripts/smoke_stxm_live_map.py` (BlueskyEngine + Tiled node-layout
  verification + live viz) — run the plan, verify the Tiled layout against
  §4, print shape/min/max.
