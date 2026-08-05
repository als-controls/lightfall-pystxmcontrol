---
name: stxm-technique-guide
description: "STXM technique/beamline selection expertise: edges and contrast mechanisms, sample constraints, and when to use ptychography, operando cells, or time-resolved modes"
---

## STXM Technique Guide

Expertise in matching STXM capabilities to science questions — which
edge, which contrast mechanism, which ALS beamline, which mode.

**See `references/techniques.md`** for contrast mechanisms, edge/element
coverage, sample-preparation constraints, and the advanced modes
(ptychography, operando, time-resolved/STXM-FMR, RPI), and
**`references/als_beamlines.md`** for the per-beamline capability matrix.

Core rules to apply:

- **STXM measures transmission**: samples must transmit — target
  optical density ~1 at the working edge (roughly 100 nm to a few
  hundred nm of solid; soft X-ray penetration is only a few hundred nm
  in dense/TM-rich material). Too-thick samples cannot be fixed in
  software; thin-section, dilute, or find thinner regions.
- **Contrast = element + chemistry**: image just above an element's edge
  for elemental contrast; XANES fine structure adds oxidation state,
  functional groups, coordination, and (with polarization) orientation
  or magnetization.
- **Beamline choice follows the edge list and environment**, not
  habit: C/N/O work favors 5.3.2.2 (with the N2 filter at C); higher
  energies, circular polarization, ptychography favor 7.0.1.2 (COSMIC);
  in-situ cells, magnetic fields, and time-resolved favor 11.0.2.2.
- **Escalate mode only when needed**: conventional STXM (~30 nm) first;
  ptychography (~7 nm, high dose — rad-hard samples) when resolution or
  spectral fidelity demands it; operando cells for potential/field/flow
  studies (photon-in/photon-out is field-immune); stroboscopic
  pump-probe for ~ps magnetization dynamics.
- **Beware harmonic contamination**: the zone plate focuses 3rd-order
  harmonic light; spurious features can mimic other edges (e.g. Fe L3
  second harmonic near the Ca L edge at ~355 eV).
