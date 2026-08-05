"""STXM scan setup skill plugin.

Gives the embedded Claude agent concrete parameter guidance for the STXM
plans this package contributes (stxm_fly_raster, stxm_energy_stack):
progressive-zoom strategy, I0 blank regions, dwell/slit heuristics, and
energy-region conventions.

Deep procedures and numeric tables ship in references/ (loaded lazily by
the SDK Skill tool): scan_setup.md (beamline-independent practice) and
bl5322_numbers.md (Beamline 5.3.2.2-specific values from the 2026
operations manual).

Sources: Marcus, JESRP 264 (2023) 147310; Feggeler et al., JESRP 267
(2023) 147381; STXM operations manual 2026 (BL 5.3.2.2).
"""

from __future__ import annotations

from pathlib import Path

from lightfall.plugins.tool_plugin import ToolPlugin


class StxmScanSetupAgent(ToolPlugin):
    """Skill for configuring STXM scans (images, stacks, linescans, maps)."""

    def get_skill_dir(self) -> Path:
        return Path(__file__).parent.parent / "skills" / "stxm_scan_setup"

    @property
    def name(self) -> str:
        return "stxm_scan_setup"

    @property
    def display_name(self) -> str:
        return "STXM Scan Setup"

    @property
    def description(self) -> str:
        return (
            "STXM scan configuration expertise: scan-type selection, "
            "progressive zoom, I0 regions, dwell/slit heuristics, and "
            "energy-stack definition"
        )

    @property
    def category(self) -> str:
        return "acquisition"

    @property
    def priority(self) -> int:
        return 20

    def get_references_dir(self) -> Path | None:
        return Path(__file__).parent / "stxm_scan_setup" / "references"
