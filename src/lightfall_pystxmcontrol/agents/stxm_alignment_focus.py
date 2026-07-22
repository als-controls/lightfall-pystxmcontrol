"""STXM alignment, focus, and calibration skill plugin.

Gives the embedded Claude agent the BL 5.3.2.2 procedures for focus
scans, A0 management, OSA focus, and motor/energy calibration.

These are physical-instrument procedures: the agent's role is to guide
the human operator step by step and sanity-check readbacks — never to
imply it will move optics or edit calibrations autonomously.

Deep material ships in references/: focus_and_a0.md and calibration.md.

Source: STXM operations manual 2026 (Marcus, ALS BL 5.3.2.2).
"""

from __future__ import annotations

from pathlib import Path

from lightfall.plugins.agent_plugin import AgentPlugin


class StxmAlignmentFocusAgent(AgentPlugin):
    """Skill for STXM focus, A0, OSA, and calibration procedures (BL 5.3.2.2)."""

    @property
    def name(self) -> str:
        return "stxm_alignment_focus"

    @property
    def display_name(self) -> str:
        return "STXM Alignment & Focus"

    @property
    def description(self) -> str:
        return (
            "BL 5.3.2.2 alignment procedures: focus scans, A0 creep "
            "recovery, OSA focus, motor and energy calibration"
        )

    @property
    def category(self) -> str:
        return "operations"

    @property
    def priority(self) -> int:
        return 30

    def get_system_prompt(self) -> str:
        return """## STXM Alignment & Focus (BL 5.3.2.2)

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
"""

    def get_references_dir(self) -> Path | None:
        return Path(__file__).parent / "stxm_alignment_focus" / "references"
