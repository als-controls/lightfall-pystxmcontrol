# Phase A STXM Energy-Stack — Follow-ups

Captured from the whole-branch review of `feature/stxm-energy-stack`. Two
Phase-B (Important) items and two cheap optional polish notes. None of these
block Phase A; they are recorded here so they are not lost.

## Important (Phase B)

### 1. `x_motor` provenance (`plans.py`)

`stxm_energy_stack` records `x_motor=flyer.X_DATA_KEY` (`"SampleX"`), which is a
**data-key**, but contract §4.1 defines `x_motor` as a **device name** taken
from the flyer's fast axis. The two happen to coincide in the sim, so nothing
breaks today. A Phase-B consumer that treats `x_motor` as a movable name would
instead receive a data-key string.

Fix before any consumer commands motion off `x_motor`: either source the actual
fast-axis device name from the flyer, or rename the contract field to
`x_data_key` to reflect what is actually stored.

### 2. `scan_panel` validation fails open + misnomer

`_axis_limits` returns `None` on any exception, so soft-limit validation is
**silently skipped**. For the energy axis this is spec §5's primary
reject-at-panel guard; a malformed happi entry therefore lets an out-of-range
scan through to die later at `bps.mv` instead of being caught at the panel.

Additionally, `launch()`'s "devices not connected" message actually fires on
**absent-from-catalog**, not on a disconnected device, and that branch is
untested.

Fast-follow:
- Log when limits cannot be read instead of silently skipping validation.
- Fix the "devices not connected" message to describe the real condition
  (absent from catalog).
- Add a test for that branch.

(Real limit truth arrives in Phase B/D, so full limit enforcement is not
expected here — only the fail-open behavior and the messaging/test gap.)

## Optional polish

### 3. happi build-script determinism (`scripts/build_pystxm_happi_db.py`)

The generated output drops a trailing newline and churns the `creation` /
`last_edit` timestamps on unchanged entries on every regeneration, producing
noisy diffs. Emit a trailing newline and preserve timestamps on entries whose
content has not changed.

### 4. `load_run` on a stack run (`scan_panel.load_run`)

`load_run` renders a stack run's raw `(nE*ny, nx)` rows node as a context
image, so the displayed rows span multiple energies — semantically odd but
non-crashing. Optionally guard on `plan_name` to take frame 0 via
`cube_from_rows` when the run is an energy stack.
