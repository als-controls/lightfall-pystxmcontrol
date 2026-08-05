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

from lightfall.plugins.tool_plugin import ToolPlugin


class StxmAlignmentFocusAgent(ToolPlugin):
    """Skill for STXM focus, A0, OSA, and calibration procedures (BL 5.3.2.2)."""

    def get_skill_dir(self) -> Path:
        return Path(__file__).parent.parent / "skills" / "stxm_alignment_focus"

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

    def get_references_dir(self) -> Path | None:
        return Path(__file__).parent / "stxm_alignment_focus" / "references"
