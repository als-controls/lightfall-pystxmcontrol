# Beamline 5.3.2.2 — concrete scan-setup numbers

From the *STXM operations manual 2026* (Marcus). These values are specific
to ALS Beamline 5.3.2.2 running pystxmcontrol; treat as defaults to adapt,
not universal truths.

## Energy / optics

- Range ~200–800 eV (optimized C/N/O K-edges; TM L-edges up to Co).
- Sub-100 meV energy resolution achievable at the C edge.
- Nitrogen filter (differential-pumped section) required for clean C-edge
  work: suppresses 2nd-order light (spurious feature at half the O K-edge
  energy lands inside the C-K range). Target 0.6–1.0 Torr in the filter
  sections. Side effect: weaker photoelectron signal at the exit slits
  degrades vertical feedback — at the Fe edge feedback is ineffective and
  the beam must be steered manually.

## Slits (entrance / exit-X / exit-Y, um)

| Purpose | Slits |
|---|---|
| Survey / navigation | 60 / 50 / 50 |
| Fe-edge stacks (better E + spatial resolution) | 40 / 30 / 30 |

Smaller slits = better resolution, less flux. Open up for surveys, close
down for final spectroscopy.

## Progressive zoom (worked example)

2 mm survey ("2mm survey" scan def, 295 eV for C contrast) -> 600 um ->
200 um (100x100 px) -> 70 um -> 25 um -> focus on a particle -> 5 um fine
scans. Survey scan is engineered to keep the X stage <= 1 mm/s (X pixel
smaller than Y).

## Fine/coarse transition gotcha

- The fine/coarse positioning handoff happens at **100 um scan size**.
- Avoid scan sizes near 100 um (navigation errors).
- Expect up to ~50 um apparent position loss when crossing the transition
  (e.g. going from 200 um to 70 um scans) — re-find the feature in the
  larger field before trusting fine coordinates.

## Focus / A0

- A0 = sample–OSA distance at focus; typical 320–500 um.
- Refocus when the field shrinks and whenever energy changes appreciably.
- Walk A0 down (paired A0 / Sample-Z moves, 50 um steps) before low-energy
  (C-edge) work — the zone-plate–sample gap is smallest there. If focus or
  position shifts during a step, the sample is bumping the zone plate:
  back out.
- No dynamic focusing: Z cannot move during a scan (no two XPS motors move
  simultaneously).

## Stage / plate geometry

- Sample plate: 2 rows x 4 holes, 2 mm holes, 5 mm apart.
- Hole centers: Y = 0 (bottom row), Y = -5000 um (top row);
  X = -7500, -2500, +2500, +7500 um left-to-right in beam's-eye view.
- Axis sense: X increases to the right; **+Y moves the beam DOWN on the
  sample** (opposite of the legacy STXM-UI convention).

## Dwell / typical acquisitions

- Dwell is entered in MILLISECONDS everywhere in pystxmcontrol.
- Energy-calibration and 0-order scans use 1000 ms dwell (spectroscopy on
  a single motor); imaging dwells are typically 1–5 ms at BM flux.
- Energy definitions load from `Home/ScanDefs` (`*.json`, case-sensitive).
  After a stack finishes, "Single Energy" auto-checks — reload the energy
  definition before the next stack. Opening a previous Scan Data file
  overwrites the current Scan Region.

## Stack recipe (from the worked example)

1. Take single images at the map energies first (e.g. 280 / 295 / 700 /
   710 eV for a C/Fe tricolor quick-map) to confirm contrast and framing.
2. Choose the stack region on a single-energy image, including an I0 blank
   area in the field.
3. Load the energy definition from file; check dwell in the Energy Regions
   tab (dwell lives there even for fixed-energy scans).
4. For a second edge (e.g. Fe after C): shift the region slightly for
   energy-dependent drift, tighten slits (40/30/30), refocus.
5. Fill in Sample and Comment fields (Experiment tab) — FAIR/DOE metadata.

## Chamber / environment defaults

- Canonical operating fill: He backfill to 1/3 atm (reads 20" Hg vacuum on
  the Bourdon gauge). Pump-and-purge a couple of times for sensitive
  spectroscopy.
- Shutter interlock requires chamber pressure below ~1/3 atm.
- Energy calibration gas: 6 Torr CO2 (292.74 eV feature; def `C_calib.json`).

## Data files

- Native format `.stxm` = HDF5 subset (server share `BL5322` on
  `\\stxmdata2`). Mantis reads it directly; STXM Reader / Linescan Reader
  need the desktop converter; Axis (IDL RTE >= 9.0) reads it renamed to
  `.hdf5` opened as pySTXM2.5.
