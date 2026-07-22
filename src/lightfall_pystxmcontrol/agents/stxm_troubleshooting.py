"""STXM troubleshooting skill plugin.

Gives the embedded Claude agent the BL 5.3.2.2 symptom -> cause -> fix
catalog for pystxmcontrol and the beamline: server restarts, motor
limits, EPS glitches, UI state traps, and nitrogen-filter operation.

Fixes involving hardware (homing motors, valves, beam steering) are
operator actions: the agent diagnoses and guides; the human acts.

Deep material ships in references/: troubleshooting.md.

Source: STXM operations manual 2026 (Marcus, ALS BL 5.3.2.2).
"""

from __future__ import annotations

from pathlib import Path

from lightfall.plugins.agent_plugin import AgentPlugin


class StxmTroubleshootingAgent(AgentPlugin):
    """Skill for diagnosing pystxmcontrol / BL 5.3.2.2 problems."""

    @property
    def name(self) -> str:
        return "stxm_troubleshooting"

    @property
    def display_name(self) -> str:
        return "STXM Troubleshooting"

    @property
    def description(self) -> str:
        return (
            "BL 5.3.2.2 symptom->cause->fix catalog: stxmserver restarts, "
            "motor limits, EPS glitches, UI state traps, N2 filter"
        )

    @property
    def category(self) -> str:
        return "operations"

    @property
    def priority(self) -> int:
        return 32

    def get_system_prompt(self) -> str:
        return """## STXM Troubleshooting (BL 5.3.2.2)

Symptom -> cause -> fix expertise for pystxmcontrol at ALS Beamline
5.3.2.2. Diagnose from the symptom table before proposing anything;
hardware fixes (homing, valves, beam steering) are performed by the
human operator.

**See `references/troubleshooting.md`** for the full symptom table and
nitrogen-filter procedure.

Fastest wins to know cold:

- **Motor positions read huge numbers (~16000)** -> stxmserver died.
  Find the terminal showing `<Arduino ready>` (Terminal "All windows"),
  Ctrl-C, up-arrow, rerun `stxmserver`.
- **Motor timeout messages in the server window** -> motor at a limit.
  Home it from the Newport XPS web interface, then recalibrate its
  offset (see the stxm_alignment_focus skill).
- **Yellow "!" on the EPS/valve screen** -> Phoebus comms glitch, not a
  real fault: dismiss and restart the window.
- **UI state traps**: "Single Energy" auto-checks after a stack (reload
  the energy definition before the next one); opening a previous Scan
  Data file OVERWRITES the current Scan Region; dwell lives in the
  Energy Regions tab even for fixed-energy scans.
- **Feature "vanishes" after zooming** -> the 100 um fine/coarse
  transition (up to ~50 um apparent shift): re-find it in a larger
  field.
- **Weak/lost vertical feedback with the N2 filter engaged** -> the
  filter gas weakens the exit-slit photoelectron signal; at the Fe edge
  feedback is ineffective — steer the beam manually.
"""

    def get_references_dir(self) -> Path | None:
        return Path(__file__).parent / "stxm_troubleshooting" / "references"
