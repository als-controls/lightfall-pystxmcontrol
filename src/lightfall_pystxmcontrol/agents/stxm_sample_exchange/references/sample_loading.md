# Sample mounting and loading (BL 5.3.2.2)

Source: STXM operations manual 2026.

## Sample plate geometry

- 2 rows x 4 holes; 2 mm holes on 5 mm centers.
- Nominal hole coordinates (beam's-eye view, X increases to the right):
  - bottom row: Y = 0; top row: Y = **-5000 um** (Y DECREASES going up);
  - X = -7500, -2500, +2500, +7500 um, left to right.
- Note the axis sense: **+Y moves the beam DOWN on the sample** —
  opposite the legacy STXM-UI convention.

## Mounting samples

- Substrates: TEM grids or SiN windows (TEM-format 3 mm frames, 0.5 mm
  windows).
- Attachment: nail polish, Elmer's glue, or double-sticky tape (punch
  the tape out of the holes with a hand drill so it doesn't block the
  beam).
- Pre-map sample coordinates on the visible-light microscope (VLM)
  outside the hutch — it has an encoded stage; note approximate hole
  coordinates before pumping down.

## Plate insertion / removal

Wear a glove.

- Insert: the plate engages **three slotted pins** — verify all three
  by feel; push down on the top to seat; hook the retaining wire.
- Remove: swing the retaining wire off, grasp the top, pull straight up.
- Chamber must be vented and **Coarse Z at 9000** before reaching in
  (see vent_pump_checklists.md).

## Anaerobic transfer (air-sensitive samples)

- Transfer from the drybox in O-ring-sealed diver's boxes.
- Pump the chamber and backfill with **Ar** (heavier than air — it
  stays in the chamber).
- Load through the **top hatch**; do NOT open the front door (would
  dump the Ar blanket).

## After loading

1. Pump down per checklist; Coarse Z back to 1000; He backfill to
   1/3 atm.
2. Survey scan at a contrast energy to find the samples (see the
   stxm_scan_setup skill's progressive-zoom workflow).
3. Fill in the Experiment tab: Proposal (auto-populates experimenters
   from the ESAF), plus **Sample and Comment fields — DOE/FAIR metadata
   compliance requires them**.
