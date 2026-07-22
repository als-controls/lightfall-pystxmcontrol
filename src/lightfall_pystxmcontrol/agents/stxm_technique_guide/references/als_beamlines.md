# ALS STXM beamlines — capability matrix

From Feggeler et al., JESRP 267 (2023) 147381 (Fig. 1 / Table 1 and
text). Four operational soft X-ray STXMs: two insertion-device (EPU),
two bending-magnet (BM).

## Summary table

| | 5.3.2.1 (STXM) | 5.3.2.2 (Polymer STXM) | 7.0.1.2 (COSMIC Imaging) | 11.0.2.2 (MES STXM) |
|---|---|---|---|---|
| Source | BM | BM | EPU | EPU |
| Energy (eV) | 500–2000 | 200–800 | 250–2500 | 200–2000 |
| Elements | Z 8–14 K; 22–36 L; 51–75 M | Z 6–9 K; 17–27 L; 41–56 M | Z 6–16 K; 17–41 L; 43–82 M | Z 6–14 K; 17–37 L; 41–75 M |
| Peak flux (ph/s) | 1e6 @500 eV | 1e6 @300 eV | 1e9 @500 eV | 5e8 @500 eV |
| Detection | PMT | PMT | PIN diode / fast CCD | PIN / APD |
| Polarization | linear horiz. | linear horiz. | inclined linear + circular | inclined linear + circular |
| Spatial res. | 30 nm | 30 nm | 50 nm (7 nm ptycho) | 30, 50 nm |
| Typical dwell | 1–5 ms | 1–5 ms | 0.1 ms (100 ms ptycho) | 1 ms (<20 ps time-res) |
| Sample env. | 0.2 bar He, gas, liquid | same | vacuum, gas, liquid, cryo, ambient | 0.2 bar He, gas, liquid, ambient |
| Stimuli | bias, heat | bias, heat | bias, heat | bias, heat, microwave, B-field |
| Focus area | soft materials | soft materials | hard materials | devices, magnetics, env. science |

## Beamline notes

### 5.3.2.2 (Polymer STXM) — runs pystxmcontrol
- Spherical-grating mono, single grating; exit slits are the source for
  the ZP (typical outer zone width 30 nm).
- Optimized for C/N/O K-edges; sub-100 meV resolution at the C edge.
  Flux extends to 800 eV → TM L-edges up to Co are reachable.
- Harmonic suppression: Ni-coated optics + a 1 m differentially-pumped
  N2-filled section for 2nd harmonic at the C edge (see the scan-setup
  skill's bl5322_numbers.md for filter operation).
- Samples on TEM grids / SiN windows; vacuum or up to ~200 Torr gas
  (usually He); operando capable.
- Typical science: aerosols, organic photovoltaics, battery chemistry,
  meteoritic organics.

### 5.3.2.1 (STXM)
- Second BM branch; dual-grating mono, ~400–2000 eV. Extends the BM
  program to Si/Al K-edges and higher TM L-edges.

### 7.0.1.2 (COSMIC Imaging / Nanosurveyor)
- EPU (38 mm period, min gap 10.5 mm): full polarization control,
  250–2500 eV (K: C–S; L: Cl–Mo; M: Tc–Pb; actinide N edges).
- Collimated plane-grating mono, E/dE ~ 2500; Rh-coated optics; ZP 3 m
  downstream of the coherence-defining exit slit.
- Conventional mode: 45 nm ZP + Si diode; accepts commercial TEM sample
  holders (easy fluid/gas cells).
- Ptychography mode: high-frame-rate CCD; dose-limited resolution to
  7 nm. High dose → hard materials (battery oxides, magnetic films).
- Highest flux of the four (~1000x the BM lines) — fastest dwells.

### 11.0.2.2 (Molecular Environmental Science STXM)
- EPU, full polarization, 200–2000 eV (ZP focal length blocks <200 eV).
- Plane-grating mono, resolving power 3000–5000.
- ZPs: 18/25/45 nm outer zone width. Detectors: AXUV100 photodiodes and
  APDs (<1 ns rise) for pulse-resolved timing; electron & fluorescence
  yield in development.
- Sample logistics: up to 8 samples on standardized plates, minutes to
  exchange; Norcada gas/liquid cells; Hummingbird flow cells.
- Magnetic field: permanent-magnet pair, up to 0.5 T parallel or
  perpendicular to the beam. Temperature control 25–500 K planned.
- Home of TR-STXM / STXM-FMR (microwave excitation phase-locked to the
  500 MHz ring RF; ALS user timing system + high-speed digitizer).

## Choosing quickly

- C/N/O chemistry on soft matter → **5.3.2.2** (N2 filter for C edge).
- Need >800 eV, circular polarization, max flux, or ptychography →
  **7.0.1.2**.
- In-situ cells with fields/microwaves, time-resolved magnetics,
  environmental science → **11.0.2.2**.
- Mid-range K-edges (Al/Si) on a BM line → **5.3.2.1**.

## ALS-U outlook (context for planning, not current capability)

>100x coherent flux is expected to bring ~1 us conventional dwells,
~1 ms ptychography dwells, and spectro-tomography in hours — contingent
on ~10 kfps soft X-ray pixel detectors and video-rate scanning. Faster
acquisition also raises radiation-damage pressure on polymers;
cryo environments are expected to become routine.
