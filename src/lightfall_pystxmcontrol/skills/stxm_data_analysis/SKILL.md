---
name: stxm-data-analysis
description: "Spectroscopic STXM analysis expertise: OD conversion, stack alignment, target fitting, chemometrics, and artifact triage"
---

## STXM Data Analysis

Expertise in the spectroscopic-STXM reduction and analysis pipeline
(raw counts -> OD -> chemistry maps).

**See `references/analysis_pipeline.md`** for the ordered reduction
recipe (dark/deadtime -> blemish -> alignment -> masking -> OD ->
fitting -> chemometrics) and **`references/artifacts_and_tools.md`**
for the artifact-triage table, file formats, and software ecosystem.

Core rules to apply:

- **Follow the pipeline order**; corrections applied out of order (e.g.
  OD conversion before alignment/masking) corrupt downstream fits.
- **OD = ln(I0/It)** — natural log. I0 comes from a blank region in the
  same acquisition. Average **count rates** over blank pixels to build
  I0; average **ODs** when combining sample spectra (the transform is
  nonlinear; the two differ).
- **Mask before interpreting**: opaque pixels (T ~ 0 blows up OD),
  pixels that drifted out of field, and pixels with edge jump below
  threshold (~0.1 OD) have no usable spectrum.
- **Trust only OD <~ 1**: thicker regions show saturation/peak blunting
  that no correction recovers.
- **Align stacks stepping backward** (high -> low energy, above-edge
  features visible), cross-correlating against a running sum of aligned
  frames; misalignment shows as red/cyan fringing or an embossed look
  in difference maps.
- **Fits are math, not chemistry**: cluster averages are not true
  end-members, NNMF is non-unique, and peak -> functional-group
  assignment is not 1:1 — always sanity-check against reference spectra
  acquired on the same instrument and, where possible, a second edge.
