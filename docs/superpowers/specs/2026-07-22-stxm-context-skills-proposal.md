# STXM beamline & technique context skills — proposal (2026-07-22)

Goal: give the embedded Lightfall agent beamline- and technique-specific STXM
knowledge so it can help users plan scans, run the instrument, and triage data
— delivered as `AgentPlugin` entries in lightfall-pystxmcontrol (SKILL.md body
via `get_system_prompt()`, deep material lazily loaded from
`get_references_dir()`).

## Sources assessed

1. Marcus, *Data analysis in spectroscopic STXM*, JESRP 264 (2023) 147310 —
   the raw-counts → OD → chemistry pipeline: I0/blank-region workflow, energy
   calibration, dark/deadtime correction, stack alignment, masking, linear/
   target fitting, valence & functional-group mapping, PCA/k-means/NNMF
   chemometrics, and a rich artifact catalog (saturation above OD≈1, 3rd-
   harmonic contamination mimicking other edges, zone-plate PSF bleed,
   misalignment fringing, I0 drift).
2. Feggeler et al., *STXM at the Advanced Light Source*, JESRP 267 (2023)
   147381 — beamline capability matrix (5.3.2.1, 5.3.2.2, 7.0.1.2 COSMIC,
   11.0.2.2 MES: energy ranges, flux, detectors, polarization, sample
   environments), pystxmcontrol architecture, and technique overviews
   (ptychography, operando cells, TR-STXM/STXM-FMR, RPI).
3. *STXM operations manual 2026* (Marcus, BL 5.3.2.2) — checklist-shaped
   procedures: vent/pump/beam-on with interlocks, sample plate loading,
   focus & A0 management, OSA focus calibration, motor & energy calibration
   (0-order then CO2 292.74 eV), nitrogen filter operation, worked
   spectromicroscopy example with concrete slit/dwell/energy numbers, file
   formats (.stxm HDF5, converter, Mantis/Axis), stxmcontrol-vs-STXM-UI
   differences, and recurring failure modes.

## Proposed skill set (6 AgentPlugins, category-grouped)

### 1. `stxm_technique_guide` (category: acquisition, on by default)
What STXM is and which technique/scan type fits the science question.
- Scan-type vocabulary: image, stack, linescan, point XANES, 2-energy map,
  polarization series; when each applies and its quantitativeness limits.
- Edge/element accessibility per beamline (capability matrix from paper 2);
  water window; which edges need the N2 filter or manual beam steering.
- Dose/thickness constraints (keep OD ≲ 1–1.5; few-hundred-nm penetration),
  when to recommend ptychography instead.
- References: capability matrix table, technique notes (operando, TR-STXM).

### 2. `stxm_scan_setup` (category: acquisition, on by default)
Concrete parameter guidance for the plans this plugin already exposes
(`stxm_fly_raster`, `stxm_energy_stack`).
- Progressive-zoom workflow (2 mm survey → 600 → 200 → 70 → 25 → 5 µm) with
  the fine/coarse 100 µm transition gotcha (avoid scan sizes near it; expect
  ≤50 µm apparent position loss).
- Always include an I0 blank region in stacks/linescans; map-energy pairs
  below/above edge; typical slits (60/50/50 survey, 40/30/30 for Fe stacks);
  dwell-time tradeoffs; per-trajectory (not per-pixel) overhead → favor
  larger scans.
- Energy-region definition conventions matching `energy_ranges.py` rows.

### 3. `stxm_alignment_focus` (category: operations)
- Focus-scan procedure (line across an edge, hourglass neck, Focus to
  Cursor); what A0 is; A0-creep recovery (paired A0/Sample-Z 50 µm steps,
  watch for ZP bump); OSA focus calibration sequence; no dynamic focusing.
- Energy calibration: 0-order (Grating Arm centroid < 5, offset -= centroid)
  BEFORE CO2 (6 Torr, 292.74 eV feature, edit included angle); I0 dips as
  internal calibrants; motor offset recalibration via motor.json.
- References: full step-by-step procedures from the manual.

### 4. `stxm_sample_exchange` (category: operations)
Vent / load / pump / beam-on checklists with the safety invariants stated as
hard rules the agent must surface, never shortcut:
- PMT HV off before venting; covers on before HV on; Coarse Z 9000 before
  sample change, 1000 after; gentle valve pressure; shutter pressure
  interlock (<~1/3 atm); He backfill to 1/3 atm (20" Hg vacuum on gauge).
- Sample-plate geometry (2×4 holes, X/Y hole coordinates, +Y moves beam
  down), three-pin engagement, anaerobic Ar top-hatch transfer.
- This skill should advise and checklist — the human performs the physical
  steps; the agent verifies readbacks where PVs exist.

### 5. `stxm_data_analysis` (category: analysis)
The Marcus pipeline, ordered as a checklist:
dark counts → deadtime correction (explicit polynomial) → blemish removal →
alignment (step backward high→low E, running-sum reference, affine fallback)
→ masking (opaque, drifted-out, low edge-jump) → OD via blank-region I0 →
fitting (atomic pre/post-edge, NNLS target fitting with background term,
peak fitting, valence ratios) → chemometrics (PCA scree/IND → k-means →
NNMF with cluster-average guesses → residual-map inspection).
- Rules of thumb: average count rates for I0 but ODs for spectra; analyze
  only OD ≲ 1; misalignment shows as color fringing/emboss.
- Artifact triage table as a reference doc (harmonics, PSF bleed, pattern
  noise, I0 jumps).
- File formats: .stxm = HDF5 subset; converter for STXM Reader; Mantis reads
  directly; Axis needs rename to .hdf5 + IDL RTE ≥ 9.0.
- Natural home for future MCP tools (e.g. OD-convert / align / quick-map
  over Tiled data via stxm_analysis_client).

### 6. `stxm_troubleshooting` (category: operations)
Symptom → cause → fix table:
- Motor positions read ~16000 → stxmserver died; restart in the <Arduino
  ready> terminal.
- Motor timeout → at limit; home via XPS website, then recalibrate offset.
- EPS screen yellow "!" → comms glitch; restart window.
- Navigation errors near 100 µm scans; Single Energy auto-checked after a
  stack (reload energy def); opening Scan Data overwrites Scan Region.
- Weak/no vertical feedback with N2 filter at Fe edge → steer manually.
- N2 filter engage/disengage procedure and target pressures (0.6–1.0 Torr).

## Cross-cutting decisions

- **SKILL.md stays lean (~1–2k words); depth goes in references/** per the
  AgentPlugin `get_references_dir()` mechanism, so context cost is paid only
  when the topic comes up.
- **Beamline-specificity**: manual content is 5.3.2.2-specific; the plugin
  currently targets COSMIC-style deployments. Either tag each skill with the
  beamline it describes, or split references into `common/` and
  `bl5322/` so porting to 7.0.1.2/11.0.2.2 is additive.
- **Scrub credentials**: the ops manual contains a NoMachine password —
  must NOT be copied into any SKILL.md or references file.
- **Safety posture**: skills 3/4/6 describe physical procedures; wording
  should direct the human, not imply the agent will actuate valves/HV.
- Manifest additions: six `PluginEntry("agent", ...)` rows; modules under
  `lightfall_pystxmcontrol/agents/` with shared `references/` data dirs.

## Suggested build order

1. `stxm_scan_setup` + `stxm_technique_guide` (highest leverage for the
   existing plan plugins, purely advisory, no safety concerns).
2. `stxm_data_analysis` (pairs with stxm_map/stxm_stack viz + Tiled reads).
3. `stxm_troubleshooting`, `stxm_alignment_focus`, `stxm_sample_exchange`
   (require the safety-posture wording pass).
