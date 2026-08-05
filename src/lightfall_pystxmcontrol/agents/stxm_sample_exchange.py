"""STXM sample exchange skill plugin.

Gives the embedded Claude agent the BL 5.3.2.2 vent / load / pump /
beam-on checklists with their safety invariants.

These procedures involve vacuum hardware, high voltage, and a fragile
X-ray window: the agent's role is to present checklists, track which
step the operator is on, and verify readbacks — never to actuate valves,
HV, or interlocked hardware, and never to suggest bypassing an
interlock.

Deep material ships in references/: vent_pump_checklists.md and
sample_loading.md.

Source: STXM operations manual 2026 (Marcus, ALS BL 5.3.2.2).
"""

from __future__ import annotations

from pathlib import Path

from lightfall.plugins.tool_plugin import ToolPlugin


class StxmSampleExchangeAgent(ToolPlugin):
    """Skill for STXM chamber venting, sample loading, and pump-down (BL 5.3.2.2)."""

    def get_skill_dir(self) -> Path:
        return Path(__file__).parent.parent / "skills" / "stxm_sample_exchange"

    @property
    def name(self) -> str:
        return "stxm_sample_exchange"

    @property
    def display_name(self) -> str:
        return "STXM Sample Exchange"

    @property
    def description(self) -> str:
        return (
            "BL 5.3.2.2 sample-exchange checklists: vent, load, pump "
            "down, backfill, and beam-on with safety invariants"
        )

    @property
    def category(self) -> str:
        return "operations"

    @property
    def priority(self) -> int:
        return 31

    def get_references_dir(self) -> Path | None:
        return Path(__file__).parent / "stxm_sample_exchange" / "references"
