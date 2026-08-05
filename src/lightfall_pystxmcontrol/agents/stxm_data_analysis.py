"""STXM data analysis skill plugin.

Gives the embedded Claude agent the spectroscopic-STXM analysis
pipeline: raw counts -> corrections -> alignment -> OD conversion ->
fitting/chemometrics, plus an artifact-triage catalog and the file
format / tool ecosystem.

Deep material ships in references/ (loaded lazily by the SDK Skill
tool): analysis_pipeline.md (the ordered reduction + analysis recipe)
and artifacts_and_tools.md (artifact triage table, formats, software).

Source: Marcus, *Data analysis in spectroscopic STXM*, JESRP 264 (2023)
147310 (plus format notes from the BL 5.3.2.2 ops manual 2026).
"""

from __future__ import annotations

from pathlib import Path

from lightfall.plugins.tool_plugin import ToolPlugin


class StxmDataAnalysisAgent(ToolPlugin):
    """Skill for reducing and analyzing spectroscopic STXM data."""

    def get_skill_dir(self) -> Path:
        return Path(__file__).parent.parent / "skills" / "stxm_data_analysis"

    @property
    def name(self) -> str:
        return "stxm_data_analysis"

    @property
    def display_name(self) -> str:
        return "STXM Data Analysis"

    @property
    def description(self) -> str:
        return (
            "Spectroscopic STXM analysis expertise: OD conversion, stack "
            "alignment, target fitting, chemometrics, and artifact triage"
        )

    @property
    def category(self) -> str:
        return "analysis"

    @property
    def priority(self) -> int:
        return 22

    def get_references_dir(self) -> Path | None:
        return Path(__file__).parent / "stxm_data_analysis" / "references"
