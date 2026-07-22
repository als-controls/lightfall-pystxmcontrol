# Vent / pump / beam-on checklists (BL 5.3.2.2)

Source: STXM operations manual 2026 (a PowerPoint version of the
pump/vent checklist also lives on the console Desktop). The operator
performs every step; verify each checkpoint before moving on.

## Hardware orientation

- PMT HV supply: brown single-width NIM module in the half-rack.
- VVR207: valve upstream of the hutch; controlled from the EPS screen
  ("Phoebus CSS" desktop shortcut). Yellow "!" markers on that screen
  mean an EPS comms glitch — dismiss and restart the window.
- Fill gases on labeled quick-disconnects: house N2, He, Ar, CO2
  (energy calibration). The purge/pressure-relief valve limits chamber
  pressure to protect the X-ray window.
- Roughing-pump switch: above the console, left of the monitor.
- Interlock status box: on the wall left of the console.
- **All valves need only light pressure — be gentle.**

## Venting (to load a sample)

1. PMT HV **off**.
2. VVR207 and shutter **closed**.
3. If venting to a full atmosphere: loosen the door-closing bolt.
4. All valves closed.
5. Fill gas flowing through the pressure-relief (purge) valve.
6. Open the vent valve until the desired pressure is reached.
7. If changing/loading a sample: **Coarse Z to 9000** (retracts the
   sample away from the zone plate / OSA before anyone reaches in).

## Pumping down

1. PMT HV **off**.
2. Vent valve closed.
3. VVR207 closed.
4. Doors closed.
5. Open the chamber roughing valve; roughing pump on.
6. When pressure < 1 Torr: close the roughing valve.
7. If a sample was just loaded: **Coarse Z back to 1000**.

Backfill: He to 1/3 atm is the canonical operating fill (reads
**20" Hg vacuum** on the Bourdon gauge — that is 1/3 atm absolute).
For sensitive spectroscopy, pump-and-purge a couple of times to dilute
residual air.

## Beam-on sequence

1. Open VVR207 (EPS screen).
2. Chamber pressure below ~1/3 atm — the shutter interlock (two
   independent redundant pressure switches, RSS-style; replaced the old
   door switches) will not permit the shutter otherwise. **Never defeat
   or work around this interlock.**
3. Open the shutter — the "Door lock enabled" light goes off.
4. Put the door covers ON, **then** PMT HV on (light leaking into the
   detector with HV on is the failure mode this ordering prevents).

## Common pitfalls

- Venting with PMT HV on (step 1 of both checklists exists for a
  reason) — always confirm HV is off first.
- Forgetting Coarse Z 9000 before a plate swap: risks crushing the zone
  plate or OSA with the plate or fingers.
- Forcing a valve: the seats are delicate and the X-ray window is one
  overpressure event away from destruction.
- Sitting at full atmosphere with the door bolt tight (step 3 of vent):
  the door can jam.
