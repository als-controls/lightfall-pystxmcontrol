---
name: stxm-alignment-focus
description: "BL 5.3.2.2 alignment procedures: focus scans, A0 creep recovery, OSA focus, motor and energy calibration"
---

## STXM Alignment & Focus (BL 5.3.2.2)

Guidance for focus, A0 management, OSA focus, and motor/energy
calibration with pystxmcontrol at ALS Beamline 5.3.2.2.

**Safety posture: these are operator-in-the-loop procedures.** Walk the
human through the steps and verify readbacks with them; never present
yourself as performing optics moves or calibration edits, and never
skip a verification step to save time. A wrong Z move can crash the
sample into the zone plate.

**See `references/focus_and_a0.md`** (focus scans, A0 concept and creep
recovery, fine/coarse gotchas) and **`references/calibration.md`**
(OSA focus sequence, motor-offset recalibration, 0-order and CO2 energy
calibration).

Core facts:

- The OSA is the fixed Z = 0 reference; the sample assembly moves and
  the zone plate moves longitudinally for energy-dependent focus.
  **A0** = sample-OSA distance at focus (typical 320-500 um).
- A focus scan repeats a line across an edge while stepping zone-plate
  Z; the operator picks the "hourglass neck" and clicks Focus to
  Cursor. It never moves the sample — it adjusts A0 and recalibrates
  Sample Z.
- A0 creeps after many sample exchanges; recover with PAIRED A0 /
  Sample-Z moves in 50 um steps, watching that focus and position stay
  fixed — any change means the sample is approaching the zone plate:
  back out. Do this before C-edge work (smallest ZP-sample gap).
- No dynamic focusing: no two stage motors move simultaneously.
- Energy calibration ORDER matters: 0-order (grating zero) FIRST, then
  CO2 (292.74 eV) — changing the grating zero shifts the CO2 result,
  not vice versa. 0-order is only needed when working at edges beyond
  carbon.
