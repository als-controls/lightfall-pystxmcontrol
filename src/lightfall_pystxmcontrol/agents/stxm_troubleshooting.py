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

from lightfall.plugins.tool_plugin import ToolPlugin


class StxmTroubleshootingAgent(ToolPlugin):
    """Skill for diagnosing pystxmcontrol / BL 5.3.2.2 problems."""

    def get_skill_dir(self) -> Path:
        return Path(__file__).parent.parent / "skills" / "stxm_troubleshooting"

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

    def get_references_dir(self) -> Path | None:
        return Path(__file__).parent / "stxm_troubleshooting" / "references"
