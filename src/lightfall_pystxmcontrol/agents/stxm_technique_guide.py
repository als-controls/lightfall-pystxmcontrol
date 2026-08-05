"""STXM technique guide skill plugin.

Gives the embedded Claude agent the science-side context for STXM: what
the technique can measure, which absorption edges and beamlines fit a
given sample/question, and when to reach for the advanced modes
(ptychography, operando cells, time-resolved) instead of conventional
STXM.

Deep material ships in references/ (loaded lazily by the SDK Skill
tool): techniques.md (technique/edge selection, advanced modes) and
als_beamlines.md (per-beamline capability matrix).

Sources: Feggeler et al., JESRP 267 (2023) 147381; Marcus, JESRP 264
(2023) 147310.
"""

from __future__ import annotations

from pathlib import Path

from lightfall.plugins.tool_plugin import ToolPlugin


class StxmTechniqueGuideAgent(ToolPlugin):
    """Skill for matching STXM techniques and beamlines to science questions."""

    def get_skill_dir(self) -> Path:
        return Path(__file__).parent.parent / "skills" / "stxm_technique_guide"

    @property
    def name(self) -> str:
        return "stxm_technique_guide"

    @property
    def display_name(self) -> str:
        return "STXM Technique Guide"

    @property
    def description(self) -> str:
        return (
            "STXM technique/beamline selection expertise: edges and "
            "contrast mechanisms, sample constraints, and when to use "
            "ptychography, operando cells, or time-resolved modes"
        )

    @property
    def category(self) -> str:
        return "acquisition"

    @property
    def priority(self) -> int:
        return 21

    def get_references_dir(self) -> Path | None:
        return Path(__file__).parent / "stxm_technique_guide" / "references"
