# STXM artifact triage and tool ecosystem

Source: Marcus, JESRP 264 (2023) 147310; format notes from the
BL 5.3.2.2 ops manual 2026.

## Artifact triage table

| Symptom | Cause | Fix / mitigation |
|---|---|---|
| Peaks blunted/flattened in thick regions; spectra saturate | OD saturation (stray light / "hole" effect) | Analyze only OD <~ 1; find thinner regions; no software recovery |
| Spectra compressed at high count rates | Detector deadtime | Apply deadtime correction (see analysis_pipeline.md §2); worst on bright blank areas |
| Constant offset in all counts | Dark counts | Shutter-closed measurement, subtract |
| Red/cyan fringing in bicolor maps; "3D embossed" difference maps | Frame misalignment | Re-run registration (backward stepping, running-sum reference, affine if sheared) |
| Spurious edge features at 1/2 or 1/3 of a strong edge's energy (e.g. Fe L3 imprinting at ~354.5/355.5 eV, mimicking Ca L) | Harmonic contamination (OSA passes some 2nd; ZP focuses 3rd order) | N2 gas filter at C edge; check whether the "edge" tracks a known edge at 2x/3x the energy |
| Distorted spectra / phantom components within a few probe-widths of sharp interfaces | Zone-plate PSF long tails (spectral bleed) | Interpret interface pixels cautiously; a cluster that lives only at interfaces is suspect; ptychography avoids this |
| OD offset between top and bottom of a frame | I0 drift/jump mid-frame (no I0 monitor) | Fit blank-column profile (polynomial x step), divide out |
| Herringbone/striping pattern | Vibration pattern noise | Per-line Fourier notch filter (last resort — removes real signal too) |
| Isolated hot pixels / bad lines | Detector blemishes, interference | Conditional median filter / line interpolation / drop frame |
| Pixels with wild or NaN OD | Opaque regions (T ~ 0) or drifted-out pixels | Mask (T > t_min; in-field mask) before any fitting |
| Spectra of the same phase differ between instruments | Beamline-dependent resolution/calibration | Reference spectra must come from the same beamline, same conditions |

## Quick diagnostic habits

- Before deep analysis, view a band-average tricolor and a raw It movie:
  drift, blemishes, and saturation are visible by eye.
- Check the per-pixel fit-residual (MSE) map after any target fit — it
  localizes both artifacts and genuinely unexpected chemistry.
- Verify the I0 spectrum looks like the beamline transmission (with its
  known contamination dips) — a contaminated "blank" region poisons
  every pixel's OD.

## File formats

- Native pystxmcontrol output: **`.stxm` = a subset of HDF5** (BL 5.3.2.2
  writes to the `BL5322` share on `\\stxmdata2`).
- **Mantis** reads `.stxm` directly.
- **STXM Reader / Linescan Reader** need the desktop converter program
  (also converts single-motor/spectrum scans to 2-column ASCII and
  prints the centroid used in 0-order calibration).
- **aXis2000** reads it renamed to `.hdf5`, opened as pySTXM2.5 (IDL
  runtime >= 9.0).

## Software ecosystem

| Tool | Platform | Notes |
|---|---|---|
| aXis2000 (Hitchcock) | IDL runtime | de-facto standard; derived images are "buffers"; stacks, linescans, tomograms |
| STXM Reader (Marcus) | LabVIEW RTE | derived images are "channels"; built-in pre-edge fit, NNF; companion Linescan Reader; "Quicker Map" for multi-energy quick maps |
| MANTiS | Python (pip) | NNMA, linescans, tomograms; constant pre-edge option |
| scikit-image / scipy | Python | registration (phase_cross_correlation), filters — building blocks for custom pipelines |

Channel-arithmetic idiom (worth reproducing in any custom pipeline):
total T = A + B; fraction xA = A/T; mask M = (T > t_min); display up to
three channels as RGB.

## Lightfall integration notes

- In Lightfall, stack data arrives via Tiled; `stxm_stack_viz` /
  `stxm_map_viz` handle live display, and the stxm-live NATS service
  computes incremental I(E) and OD reductions. This skill's pipeline
  applies to post-acquisition analysis of those same arrays.
- Natural future MCP tools for this skill: OD-convert / align /
  quick-map operations over Tiled runs (via `stxm_analysis_client`).
