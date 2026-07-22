# BL 5.3.2.2 / pystxmcontrol troubleshooting

Source: STXM operations manual 2026. Diagnose first; hardware actions
are the operator's.

## System layout (what runs where)

- Scanning program `stxmcontrol` runs on a Linux box (stxmdev2) on the
  half-rack bottom shelf; reach it via NoMachine from the console.
  Start it by typing `stxmcontrol` in a terminal.
- A separate `stxmserver` process owns motors and the shutter (via an
  Arduino on the bottom shelf).
- The Windows console machine runs feedback + analysis tools.
- Config lives in the pystxmcontrol_cfg folder (`motor.json`, energy
  section, scan defs in `Home/ScanDefs`, case-sensitive filenames).
  After any config edit: Edit tab -> Main window -> **Reload Config
  from Server**.

## Symptom -> cause -> fix

| Symptom | Cause | Fix |
|---|---|---|
| Motor positions display strange large numbers (~16000) | stxmserver died/restarted | Find the terminal containing `<Arduino ready>` (Terminal "All windows"), Ctrl-C, up-arrow, rerun `stxmserver` |
| Timeout messages in the server window when moving a motor | Motor at a travel limit | Home the motor via the Newport XPS controller web interface, then recalibrate its offset (stxm_alignment_focus skill) |
| Yellow "!" markers on the EPS/valve screen | Phoebus CSS comms glitch (not a real fault) | Dismiss and restart the EPS window |
| Stack won't start at multiple energies right after a previous stack | "Single Energy" auto-checked itself when the last stack finished | Reload the energy definition (File -> Open) |
| Scan region silently changed | A previous Scan Data file was opened — it overwrites the Scan Region with the file's region | Re-enter/reload the intended scan region |
| Dwell seems ignored on a fixed-energy image | Dwell is set in the Energy Regions tab, even for single-energy scans | Set dwell there |
| Feature lost after changing scan size around 100 um | Fine/coarse positioning transition (up to ~50 um apparent shift; avoid scan sizes near 100 um) | Re-find the feature in a larger field, then zoom again |
| Vertical feedback weak or dead with N2 filter engaged | Filter gas at the exit slits weakens the photoelectron feedback signal | Expected; at the Fe edge feedback is ineffective — operator steers the beam manually |
| Spurious spectral feature inside the C-K range at half the O-K energy | 2nd-order light (filter not engaged or underpressured) | Engage the N2 filter at 0.6-1.0 Torr (procedure below) |
| Config edits not taking effect | Server still has the old config | Edit -> Main window -> Reload Config from Server |
| Shutter won't open | Chamber pressure above ~1/3 atm — interlock (two redundant pressure switches) | Pump down / check backfill; NEVER bypass the interlock |
| Beam/no counts, everything else fine | VVR207 closed, shutter closed, or PMT HV off / covers off | Walk the beam-on sequence (stxm_sample_exchange skill) |
| Position readbacks fine but images offset from expected hole coords | Motor offsets drifted | Recalibrate offsets in motor.json (stxm_alignment_focus skill) |

## Nitrogen filter (C-edge work only)

Purpose: suppress 2nd-order light, which otherwise imprints a spurious
feature at half the O K-edge energy — inside the C-K scan range.

- Layout: differentially-pumped section with 4 pinholes + turbo pumps +
  a downstream leak valve. Pressures monitored via the Logitech camera
  program on the console.
- **Engage**: close the downstream bypass valve (the upstream one stays
  closed); open the leak valve SLOWLY — it is mounted pointing down, so
  clockwise-from-above = open. Target **0.6-1.0 Torr** in the filter
  sections; the upstream-of-apertures gauges should stay "in the 9's"
  (1e-9 range).
- **Disengage**: close the leak valve; open the downstream bypass only.
- Side effect: exit slits sit in the filter gas -> weaker photoelectron
  signal -> degraded vertical feedback (ineffective at the Fe edge;
  manual steering).

## When to escalate to staff

- Any interlock that will not clear with pressure genuinely below
  threshold.
- Suspected X-ray window damage (chamber won't hold vacuum after an
  overpressure event).
- XPS homing that does not restore sane motion.
- Anything requiring entry into the half-rack electronics beyond the
  documented PMT HV / V-F module swaps.
