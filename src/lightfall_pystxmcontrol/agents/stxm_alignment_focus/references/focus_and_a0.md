# Focus and A0 management (BL 5.3.2.2, pystxmcontrol)

Source: STXM operations manual 2026. Operator performs all moves; the
agent guides and cross-checks readbacks.

## Geometry

- OSA = fixed Z = 0 reference. Sample assembly moves in Z; zone plate
  (ZP) moves longitudinally to hold focus as energy changes (focal
  length scales with energy).
- **A0** = sample-OSA distance that yields focus; typical 320-500 um.
  A1 lives in the Staff tab and is entered POSITIVE (legacy STXM-UI
  used negative).
- Top-view camera helps judge sample-OSA clearance (the ZP holder is
  10.4-10.5 mm wide — use it for scale).

## Focus scan procedure

1. Take an image containing a sharp feature (particle edge, grid bar).
2. Lower "Line" tab: set position/length/angle of the focus line across
   the feature. Lower "Focus" tab: set the ZP travel range.
3. Run the Focus scan type: it repeats the line at varying ZP Z.
4. Look for the "hourglass neck" (narrowest line profile) in the
   resulting (position vs Z) image; click **Focus to Cursor** on it.
5. The scan type reverts to Image afterward.

Key semantics: the focus scan NEVER moves the sample. Focus-to-cursor
moves the ZP, adjusts A0, and recalibrates Sample Z to equal A0.

Refocus whenever: the field of view shrinks a zoom level, the energy
moves appreciably (ZP focal length), or after a sample exchange.

## A0 creep recovery

After many sample exchanges A0 drifts. Recovery (do BEFORE low-energy /
C-edge work, where the ZP-sample gap is smallest):

1. Move A0 and Sample Z by the SAME amount, in **50 um steps**.
2. After each step, verify focus and image position are unchanged.
3. Any change in focus or position = the sample is bumping/approaching
   the zone plate — back out immediately.

## Fine/coarse positioning gotchas

- The fine/coarse handoff happens at **100 um scan size**; avoid scan
  sizes near this value (navigation errors).
- Expect up to ~50 um apparent position loss crossing the transition
  (e.g. 200 um scan -> 70 um scan): re-find the feature before trusting
  coordinates.
- Use **Sample X / Sample Y** in Move Motors, not the Coarse/Fine
  motors directly.
- No dynamic focusing: the controller moves only one stage motor at a
  time (no Z tracking during a scan).
- +Y moves the beam DOWN on the sample; X increases to the right
  (beam's-eye view) — opposite Y sense vs the legacy STXM-UI.
