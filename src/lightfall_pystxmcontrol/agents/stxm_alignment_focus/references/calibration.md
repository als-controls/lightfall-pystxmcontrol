# Calibration procedures (BL 5.3.2.2, pystxmcontrol)

Source: STXM operations manual 2026. Non-routine operations — typically
staff-led. The agent guides; the operator acts and confirms each
verification point.

## OSA focus calibration

Needed after a zone-plate or X-ray-window change, or if the OSA was
bumped. Quick check first: run steps 5-6 below; if the OSA image is
sharp, stop — no calibration needed.

1. OSA Image scan with **auto focus checked**.
2. OSA Focus scan: line ~50 um long, focus range ~200 um, auto focus
   checked.
3. Select the focus (hourglass neck), click **Focus to Cursor**.
4. OSA Image scan, auto focus checked (normal OSA scan).
5. Move ZonePlateZ NEGATIVE by A0.
6. OSA Image scan with auto focus **unchecked** — the OSA should now be
   in focus. If not, repeat from step 1.

(Differs from legacy STXM-UI, where the setup image was taken with the
ZP pulled back and autofocus off — here autofocus stays checked.)

## Motor-offset recalibration

There is no reset/home button in the GUI; calibration = config edit.

1. Establish truth: e.g. center the beam in a known plate hole (hole
   coordinates: Y = 0 / -5000 um rows; X = -7500/-2500/+2500/+7500 um),
   or find the left/right plate edges at Y = -2500 and assert their
   midpoint is X = 0.
2. Files window -> shortcut **pystxmcontrol_cfg** -> open `motor.json`.
3. Find the motor's section; adjust `"offset"` (reading +4000 when truth
   is +3000 -> decrease offset by 1000). Adjust **CoarseY**, not
   SampleY, for the Y axis.
4. Save, then Edit tab -> Main window -> **Reload Config from Server**.
5. Verify: move to a known feature and confirm the readback.

If a motor hits a limit (timeout messages in the server window): home it
via the Newport XPS controller's web interface, then recalibrate its
offset as above.

## Energy calibration

Order rule: **0-order FIRST, then CO2** — moving the grating zero shifts
the CO2 calibration, not vice versa. Skip 0-order if only working at the
C edge and the CO2 check passes.

### 0-order (grating zero) calibration

Hardware setup: rotate the diagnostic-diode selector (downstream of the
exit slits) to **Diode In**; verify signal on the DVM.

1. Vertical feedback OFF.
2. Uncheck autofocus in Scan Regions.
3. Entrance and ExitX slits to 5 um; ExitY to 20 um.
4. Grating Arm motor to 0 — confirm signal on the DVM.
5. Connect the ORTEC V/F module output to the Keysight counter input in
   place of the PMT cable (counts appear in Monitor view).
6. Single Motor scan: motor = Grating Arm, dwell 1000 ms, range -50 to
   +50, step 0.2.
7. Run the file converter — it prints the **centroid**. Target
   |centroid| < 5, ideally < 1.
8. Change the Grating Arm offset by **minus the centroid** (centroid
   +1.5 with offset -420.0 -> -421.5). Rescan; iterate until converged.
9. Restore: undo steps 5 -> 1 in reverse order.

### CO2 calibration (C edge, 292.74 eV)

1. Pump the chamber; fill with **6 Torr CO2** (labeled quick-disconnect).
2. Single Motor scan: motor = Energy, dwell 1000 ms, covering the sharp
   **292.74 eV** feature (energy def `C_calib.json` spans the full CO2
   range including the 294.76 eV peaks).
3. Move energy to the found peak position.
4. Edit the Energy section's **Included angle** in the config (same
   pystxmcontrol_cfg -> edit -> Reload Config from Server flow) so the
   displayed energy reads 292.74 eV.
5. Verify by rescanning the feature.

Cross-check anytime: the I0 spectrum's carbon-contamination dips
(285.1 / 286.7 / 287.6 eV) serve as free internal calibrants.
