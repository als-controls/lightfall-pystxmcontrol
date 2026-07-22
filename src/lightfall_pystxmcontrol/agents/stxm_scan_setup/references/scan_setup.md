# STXM scan setup playbook (beamline-independent)

Sources: Marcus, *Data analysis in spectroscopic STXM*, JESRP 264 (2023)
147310; Feggeler et al., *STXM at the Advanced Light Source*, JESRP 267
(2023) 147381; STXM operations manual 2026. Beamline-specific numbers live
in `bl5322_numbers.md`.

## 1. Scan-type selection

| Question | Scan type | Notes |
|---|---|---|
| What does the sample look like? | Single-energy image | Pick an energy with contrast for the dominant element (just above its edge). |
| Where is element X? | 2-energy map (below/above edge) | OD difference ~ elemental column density. Semi-quantitative only (see §5). |
| Spectrum along a line/interface? | Linescan (line vs energy) | Same analysis pipeline as stacks; much faster. Leave blank space at one end for I0. |
| Spectrum at a few points? | Point XANES (energy scan at fixed position) | Cheapest spectroscopy; no spatial context. |
| Per-pixel chemistry / species maps? | Full energy stack | Most expensive (can be hours). Needs I0 region, drift tolerance, alignment in analysis. |
| Orientation / magnetization? | Polarization series | Images vs linear polarization angle (Malus fit) or L/R circular difference (XMCD). |

Rule: pick the cheapest type that answers the science question. Suggest a
stack only when per-pixel spectra are genuinely needed; offer a map or
linescan first.

## 2. Progressive zoom workflow

1. Survey scan of the whole sample/plate hole at a contrast energy.
2. Medium field on a candidate region; refocus (focus scan) once features
   are visible.
3. Fine field on the feature of interest; refocus again — depth of focus
   shrinks with field/zone-plate demands, and low-energy work needs the
   smallest sample–zone-plate gaps.
4. Only then set up maps/stacks/linescans.

Never jump straight to a fine scan: navigation offsets between coarse and
fine positioning regimes can displace the field by tens of um (beamline
specifics in `bl5322_numbers.md`).

## 3. I0 strategy (non-negotiable for quantitative work)

- STXMs generally have **no I0 monitor**. I0 comes from a **blank region**
  (no sample, same substrate/window) inside the same acquisition.
- Stacks: choose the region so an off-sample area is included in the field.
- Linescans: extend the line past the sample edge so one end is blank.
- If no blank area exists in the field: take the acquisition, then move to
  a blank area and repeat for I0 (worse — beam drift between the two).
- Averaging rule: average **count rates** over blank pixels to get I0,
  then convert to OD = ln(I0/It); do NOT average ODs to make I0. (Average
  ODs, not counts, when combining sample spectra — the transform is
  nonlinear and the two differ.)
- At C/N/O edges the I0 spectrum has strong dips from beamline carbon/oxygen
  contamination and SiN window absorption. These normalize out only if I0
  and It share the same optics path — another reason for in-field I0. The
  dips double as internal energy calibrants.

## 4. Dwell time, dose, and counting

- Dwell trade-off: statistics improve as sqrt(dwell); dose and radiation
  damage grow linearly. Polymers and biological/organic samples damage
  noticeably — survey at short dwell, spend dwell only on final data.
- Scan software overhead accrues **per trajectory (per line), not per
  pixel** — favor fewer, larger scans over many small ones.
- Keep transmitted-signal OD <~ 1 (ideally < 1.5 everywhere analyzed):
  optically thick regions show peak blunting/saturation that analysis
  cannot recover. If the sample is thick, find a thinner region rather
  than raising dwell.
- Watch detector saturation/deadtime at high count rates (bright blank
  regions at low absorption energies are the usual offender).

## 5. Elemental maps (2-energy)

- Below-edge energy: just under the absorption onset. Above-edge energy:
  on/just past the main rise. Keep the pair close together so the
  background slope cancels, but note the difference then depends on which
  chemical species is present — maps are **not** fully quantitative.
- For multi-element context, acquire pairs at each edge and present as
  tricolor (RGB) overlays.
- Expect energy-dependent image drift between frames; small offsets are
  normal and are corrected by registration in analysis.

## 6. Energy-stack definition

Define energies as (start, stop, n_points) rows (the scan panel expands
rows to a flat eV list; a shared boundary energy appearing twice is
allowed and intentional).

Typical three-zone structure per edge:

| Zone | Extent | Step |
|---|---|---|
| Pre-edge baseline | ~10 eV below onset up to onset | 0.5–1 eV |
| Near-edge (XANES) | onset through white line / fine structure | 0.1–0.25 eV |
| Post-edge tail | past fine structure, +20–40 eV | 0.5–2 eV |

- Pre-edge points are required for background/atomic-absorption fitting —
  do not start the stack at the edge.
- Post-edge points far from the edge enable elemental (column density)
  quantification against tabulated atomic absorption.
- Two-edge stacks (e.g. C then Fe): run as separate stacks; expect to
  shift the region slightly between edges to compensate energy-dependent
  drift; re-check focus (zone-plate focal length scales with energy).
- After a stack completes some UIs revert to single-energy mode — reload
  the energy definition before launching another stack.

## 7. Which edges / which beamline

Soft X-ray STXM covers C, N, O K-edges; transition-metal L-edges; Ca L;
Ce M4,5; S K on some instruments. The "water window" below the O K-edge
permits imaging hydrated samples. ALS capability matrix (energy range,
flux, polarization, detectors, environments per beamline) — see Feggeler
et al. Table 1; brief version:

| Beamline | Energy (eV) | Polarization | Strengths |
|---|---|---|---|
| 5.3.2.1 | 500–2000 | linear horiz. | mid-energy BM STXM |
| 5.3.2.2 | 200–800 | linear horiz. | C/N/O optimized, sub-100 meV at C; gas/operando |
| 7.0.1.2 (COSMIC) | 250–2500 | full (EPU) | high flux, ptychography to 7 nm, hard materials |
| 11.0.2.2 (MES) | 200–2000 | full (EPU) | environmental cells, magnetics, time-resolved |

Harmonic gotcha: the OSA blocks most 2nd-harmonic light but the zone
plate focuses 3rd-order/3rd-harmonic; higher-harmonic contamination can
imprint spurious features (classic trap: Fe L3 2nd harmonic appearing at
~354–356 eV, mimicking the Ca L edge). At the C edge, use the nitrogen
gas filter where available.

## 8. Pre-flight checklist (any quantitative acquisition)

1. Scan type is the cheapest that answers the question.
2. I0 blank region inside the field (or explicit plan for a separate I0).
3. Focus verified at the working energy; refocus after big energy moves.
4. Dwell justified against damage; OD <~ 1 in regions to be analyzed.
5. Energy rows bracket the edge with pre-edge baseline and fine XANES steps.
6. Detector not saturating on blank regions.
7. Sample/experiment metadata fields filled in (FAIR/DOE compliance).
