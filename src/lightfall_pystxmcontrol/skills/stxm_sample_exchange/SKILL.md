---
name: stxm-sample-exchange
description: "BL 5.3.2.2 sample-exchange checklists: vent, load, pump down, backfill, and beam-on with safety invariants"
---

## STXM Sample Exchange (BL 5.3.2.2)

Checklists for venting, sample loading, pump-down, backfill, and
beam-on with pystxmcontrol at ALS Beamline 5.3.2.2.

**Safety posture: the human operates the hardware.** Present the
checklist, confirm each step's verification point (gauge readings,
interlock lights), and stop the operator if an invariant is about to be
violated. Never claim to actuate valves/HV yourself and never suggest
working around an interlock.

**See `references/vent_pump_checklists.md`** (vent, pump-down, backfill,
beam-on sequences) and **`references/sample_loading.md`** (plate
geometry, mounting, anaerobic transfer).

Hard invariants (surface these unprompted whenever relevant):

- **PMT HV off BEFORE venting**; door covers ON before HV back on
  (light leaks destroy the detector's usefulness and risk the PMT).
- **Coarse Z to 9000 before touching the sample plate**; back to 1000
  after loading (protects zone plate and OSA from collision).
- The shutter interlock requires chamber pressure below ~1/3 atm (two
  redundant pressure switches) — this is a safety system, never to be
  defeated.
- The purge/pressure-relief valve protects the X-ray window from
  overpressure; all valves take only LIGHT pressure — be gentle.
- Canonical operating fill: He backfill to 1/3 atm (reads 20" Hg vacuum
  on the Bourdon gauge); pump-and-purge twice for sensitive
  spectroscopy.
