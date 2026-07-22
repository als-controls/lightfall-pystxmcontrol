# STXM techniques and when to use them

Sources: Feggeler et al., *STXM at the Advanced Light Source*, JESRP 267
(2023) 147381; Marcus, *Data analysis in spectroscopic STXM*, JESRP 264
(2023) 147310. Beamline specifics in `als_beamlines.md`.

## 1. What STXM is

A zone plate focuses monochromatic soft X-rays to a spot (~tens of nm,
down to ~7 nm with ptychography); the sample is raster-scanned through
the spot and transmitted intensity is recorded per pixel. Tuning the
photon energy across an absorption edge turns each pixel into a XANES
spectrometer. Resolution sits between TEM and optical/X-ray microprobe;
contrast is elemental AND chemical, dose is far below TEM.

- Optics chain: zone plate (ZP) + order-sorting aperture (OSA). The OSA
  blocks most 2nd-harmonic light, but the ZP focuses 3rd-order /
  3rd-harmonic — see §6 harmonics.
- Photon-in/photon-out: immune to electric potentials and magnetic
  fields at the sample — this is what enables true operando work.

## 2. Edge and element coverage (soft X-ray, ~200–2500 eV)

| Edge family | Examples | Science handles |
|---|---|---|
| K-edges, low Z | C (285 eV), N (~400), O (~530) | organics, polymers, functional groups, biominerals |
| K-edges, mid Z | Si, P, S (~1800–2500) | minerals, sulfur speciation (sulfide/S0/sulfite/sulfate well separated) |
| L-edges, 3d TM | Ti, Mn, Fe (~708), Co, Ni, Cu | oxidation state (L3 multiplet/ratio), magnetism (XMCD) |
| L-edge, Ca | ~350 eV | biominerals; calcite vs aragonite fingerprinting |
| M-edges | Ce M4,5 | lanthanide valence |

- **Water window** (between C and O K-edges, ~284–543 eV): water is
  relatively transparent — hydrated/biological samples imageable in
  liquid.
- Transition-metal K-edges are NOT reachable on soft X-ray STXMs (hard
  X-ray nanoprobes only).

## 3. Sample constraints (check before proposing any measurement)

1. **Thickness**: target OD ~ 1 at the working edge; penetration depth
   is a few hundred nm in dense or TM-rich material, more in organics.
   Above OD ~1–1.5, absorption saturates (peak blunting) and the data
   cannot be repaired in analysis. Typical preparations: ultramicrotomed
   thin sections (e.g. battery electrodes), drop-cast particles,
   thin films on SiN windows, TEM grids.
2. **Substrate**: SiN windows (TEM-format 3 mm frames) or TEM grids;
   substrate absorption normalizes out via the I0 blank region.
3. **Radiation sensitivity**: polymers and biological material damage
   under dose; survey fast, dwell long only on final acquisitions.
   Ptychography's dose is much higher — see §5.1.
4. **Environment**: vacuum or ~1/3 atm He is standard; gas/liquid flow
   cells, heating, bias, and magnetic fields are available on specific
   beamlines (see `als_beamlines.md`).

## 4. Contrast mechanisms → measurement modes

| You want | Mode | Notes |
|---|---|---|
| Morphology | single-energy image | pick an energy just above the dominant element's edge |
| Element distribution | 2-energy map (below/above edge) | semi-quantitative; tricolor overlays for multi-element |
| Chemical speciation per pixel | energy stack + reference-spectrum fitting | needs good reference spectra taken on the same instrument |
| Oxidation-state maps | stack over a TM L-edge; peak-ratio or LCF analysis | Fe L23 van Aken method; demanding data quality; standards on same beamline |
| Functional groups (organics) | C/N K-edge stacks + Gaussian peak fitting | peak→group assignment not 1:1; cross-check at a second edge (amide: C ~288 eV pairs with N ~401.9 eV) |
| Molecular orientation | linear-polarization series (Malus-law fit) | needs polarization control (EPU beamlines) |
| Magnetization maps | XMCD: L/R circular polarization difference | EPU beamlines; element-specific magnetometry |
| Quantitative column density | pre-/post-edge fit to tabulated atomic absorption | energies far from the edge; Henke/CXRO tables |

## 5. Advanced modes — escalate only when conventional STXM can't do it

### 5.1 Ptychography (spectro-ptychography)
- Replace the single-pixel detector with a pixelated one; reconstruct
  from overlapping coherent diffraction patterns.
- Gains: ~10x spatial resolution (to ~7 nm), removes zone-plate spectral
  distortions, adds a phase channel (better chemical sensitivity).
- Costs: much higher dose (in practice restricted to hard/rad-tolerant
  materials — oxides, batteries, magnetic films), large data volumes,
  HPC reconstruction pipeline. Sample must still be thin.
- At ALS: 7.0.1.2 (COSMIC).

### 5.2 Operando / in-situ cells
- Photon-in/photon-out means applied potentials, fields, gas or liquid
  flow do not perturb the measurement — genuine operando.
- Geometry constraint: the focal plane sits close to the OSA, so the
  cell must be very thin on the upstream side; ambient gas/liquid layer
  around the sample only a few hundred nm thick. Micromachined TEM-style
  cells (Norcada, Hummingbird) are the standard approach.
- Canonical example: electrochemical flow cell, XAS vs applied voltage
  (Co L3 oxidation-state tracking during OER).

### 5.3 Time-resolved STXM / STXM-FMR
- Stroboscopic pump-probe against the synchrotron RF: excitation must be
  phase-locked to a harmonic of the 500 MHz storage-ring frequency;
  sub-20 ps resolution with APD detection in multibunch mode.
- Probes element-specific magnetization dynamics via XMCD; transverse
  geometry gives true time- and phase-resolved precession maps.
- Analysis: pixel-by-pixel sinusoidal fit of the image time series →
  HSV maps (hue = phase, brightness = amplitude, saturation = fit
  quality); directly comparable to micromagnetic simulation output.
- At ALS: 11.0.2.2 (bias field via permanent-magnet pair, microwave
  excitation on resonator samples).

### 5.4 Full-field / RPI (randomized probe imaging)
- A speckle-patterned probe (custom zone plate, ~6.75 um spot with 30 nm
  speckle) allows single-frame full-field reconstruction at ~60 nm —
  speed limited by flux/frame rate, not stage motion. For millisecond
  dynamics or fast spectroscopy where scanning is too slow.

## 6. Cross-cutting gotchas

- **Harmonics**: the OSA passes and the ZP focuses 3rd-order light;
  2nd-harmonic leakage also exists. Spurious features appear at 1/2 or
  1/3 the energy of strong high-energy edges — classic trap: Fe L3
  (709/711 eV) 2nd harmonic imprints at ~354.5/355.5 eV and mimics the
  Ca L edge. Mitigations: N2 gas filter at the C edge, Ni/Rh-coated
  optics, beamline design.
- **Zone-plate PSF tails**: intensity leaks several probe-widths across
  sharp interfaces → distorted spectra near boundaries and phantom
  "interface components" in cluster analysis. Ptychography avoids this.
- **Energy-dependent focus**: ZP focal length scales with energy —
  refocus after large energy moves; two-edge studies need a refocus and
  usually a small region shift between edges.
- **Reference spectra rule**: quantitative species mapping is only as
  good as the reference spectra; acquire them on the same instrument,
  same conditions, on uniform films of known composition.
