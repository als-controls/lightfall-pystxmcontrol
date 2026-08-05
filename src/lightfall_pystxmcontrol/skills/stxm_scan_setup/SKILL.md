---
name: stxm-scan-setup
description: "STXM scan configuration expertise: scan-type selection, progressive zoom, I0 regions, dwell/slit heuristics, and energy-stack definition"
---

## STXM Scan Setup

Expertise in configuring STXM acquisitions with the `stxm_fly_raster` and
`stxm_energy_stack` plans (positions in um; dwell in MILLISECONDS).

**See `references/scan_setup.md`** for the full playbook (scan-type
selection, progressive zoom, I0 regions, dwell and stack strategy) and
**`references/bl5322_numbers.md`** for Beamline 5.3.2.2-specific values
(slits, survey settings, fine/coarse gotchas).

Core rules to apply when helping plan a scan:

- **Pick the cheapest scan type that answers the question**: single-energy
  image for morphology; 2-energy map (below/above edge) for elemental
  contrast; linescan for spectra along one line; full energy stack only
  when per-pixel XANES is needed (stacks can take hours).
- **Always leave an I0 blank region** (sample-free area) inside stack and
  linescan fields — STXMs have no I0 monitor; quantitative OD conversion
  is impossible without it.
- **Zoom progressively** (survey -> feature -> fine scan), refocusing as
  the field shrinks. Never jump straight to a fine scan on a fresh sample.
- **Dwell trade-off**: longer dwell = better statistics + more dose/damage.
  Scan overhead accrues per trajectory (per line), not per pixel — a few
  large scans beat many small ones.
- **Keep OD <~ 1** in the analyzed regions: thicker areas saturate
  (peak blunting) and are not recoverable in analysis.
- **Energy stacks**: define energies as (start, stop, n_points) rows —
  fine steps (~0.1 eV) only across the near-edge region, coarse steps in
  pre-edge and post-edge tails. Bracket the edge with enough pre-edge
  baseline for background fitting.
