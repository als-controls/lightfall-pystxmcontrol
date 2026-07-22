# Spectroscopic STXM analysis pipeline

Source: Marcus, *Data analysis in spectroscopic STXM*, JESRP 264 (2023)
147310. Applies to stacks, linescans, point XANES, and maps (and to
ptychography intensity reconstructions). Formats/tools and the artifact
table live in `artifacts_and_tools.md`.

## Physics recap

Lambert-Beer: It(r,E) = I0(E) * exp(-mu*t). **OD = ln(I0/It)** — natural
log (beware base-10 conventions in some tools). mu decomposes per
element/species; far from edges the cross-sections take tabulated atomic
values (Henke tables / CXRO website) — the basis of elemental
quantification.

## Reduction (do these IN ORDER)

### 1. Dark counts
Measure with the shutter closed; subtract from all data.

### 2. Detector deadtime / nonlinearity
Calibrate against a linear monitor (PIN diode after the last slits) via
a slit scan: Imon = K*F, Idet = S(F)*F with deadtime model
S(F) = exp(-F*tau). Inverse correction:

    Icorr = u(x) * I,  x = I*tau
    u(x) ~ 1 + x + (3/2)x^2 + (5/2)x^4 + (x/0.4040353)^6.933737

good to 1% up to x ~ 0.35 (50% deadtime). Without a monitor, use the
two-slit-scan family method (Collins & Ade). Deadtime matters most on
bright blank regions at low-absorption energies.

### 3. Blemish removal
- Isolated hot/cold pixels: conditional median filter (replace a pixel
  only when the change exceeds a threshold — plain median blurs).
- Bad lines: interpolate across.
- Large corrupted areas (e.g. electrical-interference streaks): delete
  the whole frame.

### 4. Stack alignment / registration
Samples drift and deform over hours-long stacks.
- Cross-correlation translation with subpixel refinement
  (Guizar-Sicairos; scikit-image `phase_cross_correlation`).
- **Step backward, high -> low energy**: above-edge frames have visible
  features; pre-edge frames may be nearly blank.
- Reference = running sum of already-aligned frames (robust against
  single-frame noise).
- Optional Sobel pre-filter — sometimes helps, sometimes hurts; check.
- If shear/rotation/shrinkage is visible (drift within a frame appears
  as shear): fit an affine transform instead of pure translation.

### 5. Masking (after alignment)
Build boolean masks and combine (AND / AND NOT / NOT):
- opaque pixels: T ~ 0 makes OD blow up / NaN — threshold mask
  M = (T > t_min);
- pixels that drifted out of the field during the stack;
- for analysis: pixels with edge jump below threshold (e.g. < 0.1 OD)
  carry no usable spectrum.

### 6. Convert to OD
I0 from the blank region: average **count rates** over blank pixels per
frame, then OD = ln(I0/It) per pixel. (When later averaging sample
spectra, average ODs — the nonlinear transform makes the two orders
differ.) At C/N/O edges the I0 spectrum carries strong dips from
beamline contamination and SiN windows (e.g. 285.1/286.7/287.6 eV at C);
in-field I0 normalizes them out and the dips double as internal energy
calibrants.

### 7. Optional cosmetic fixes
- I0 jumps mid-frame (no monitor!): fit a blank-column average profile
  to polynomial x step, divide out.
- Vibration "pattern noise" (herringbone): per-line Fourier notch filter
  (loses some real information — last resort).

## Analysis methods (pick per question)

### Elemental quantification (column density, atomic ratios)
Fit pre-edge + far post-edge OD to tabulated atomic absorption. Energies
must be FAR from the edge. Elements with no edge in range still
contribute a smooth background and remain quantifiable through it.

### Rough elemental maps
Above-minus-below-edge OD difference. Keep the pair close (background
slope cancels) but know the result is species-dependent — semi-
quantitative only.

### Linear / target fitting (species maps)
OD(x,y,E) = sum_s A_s(x,y) * S_s(E), solved per pixel with non-negative
least squares. Reference spectra S_s normalized to known column density
via their own pre/post-edge atomic fits -> A_s maps in mass loading.
Add a pre-edge background term p(E) = a + b*E^-q (q ~ 2-3), or emulate
with synthetic references S(E) = 1 and S(E) = (E0/E)^q - 1. ("SVD" in
the STXM literature = this least-squares via pseudo-inverse — one matrix
inversion serves all pixels.)

### Functional-group / peak mapping (organics)
Fit the area-average spectrum to Gaussians + arctangent step (+ pre-edge
background); freeze positions/widths; refit amplitudes per pixel;
display as tricolor maps. Caveats: peak -> group assignment is not 1:1
(C=C ~285 eV wanders by tenths of eV with conjugation); cross-check at a
second edge (amide: C 287.9-288.2 eV should pair with N ~401.9 eV).

### Valence / oxidation-state mapping
- Fe L23: two-peak ratio with two-arctangent baseline (van Aken &
  Liebscher) — demanding data quality; standards must be measured on the
  same beamline under the same conditions.
- Also: Ce M4,5; Ti L23 (valence + coordination); S K (sulfide/S0/
  sulfite/sulfate cleanly separated).
- Quick look: band-average tricolor images before committing to fits.

### Dichroism
- Linear: Malus-law trig fit vs polarization angle -> per-pixel optic-
  axis orientation (3D orientation possible).
- Circular: L/R difference -> XMCD magnetization maps.

### Exploratory chemometrics (unknown mixtures)
1. Mask first (edge-jump threshold).
2. PCA; choose component count via scree plot + Malinowski IND.
3. k-means clustering on PCA-reduced pixels.
4. Compute cluster-average spectra FROM RAW DATA (not the PCA-reduced
   version).
5. NNMF seeded with the cluster averages, with closeness-to-guess and
   sparseness cost terms (NNMF alone is non-unique).
6. Inspect the per-pixel fit-MSE map — outlier chemistry hides there.

Caveats: cluster averages are not true end-members (interior-point
argument -> negative loadings can be legitimate); every method here is
math, not chemistry — the analyst assigns meaning.

### De-noising
PCA truncation (verify the residual looks like pure noise; note it
destroys statistical independence of pixels) or the conditional median
filter.

## Energy calibration (analysis side)

Recalibration = relabeling each frame's energy; no data change. Anchor
to a sharp known feature — gas-phase references (CO2 Rydberg lines at
the C edge, 292.74 eV) or the I0 contamination dips as internal
calibrants. The mono has two degrees of freedom (included angle +
grating zero), so single-point calibration is valid near one edge;
multi-point is needed when hopping between distant edges.
