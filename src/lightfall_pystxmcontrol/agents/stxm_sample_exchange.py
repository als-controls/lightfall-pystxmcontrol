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

from lightfall.plugins.agent_plugin import AgentPlugin


class StxmSampleExchangeAgent(AgentPlugin):
    """Skill for STXM chamber venting, sample loading, and pump-down (BL 5.3.2.2)."""

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

    def get_system_prompt(self) -> str:
        return """## STXM Sample Exchange (BL 5.3.2.2)

Checklists for venting, sample loading, pump-down, backfill, and
beam-on with pystxmcontrol at ALS Beamline 5.3.2.2.

**Safety posture: the human operates the hardware.** Present the
checklist, confirm each step's verification point (gauge readings,
interlock lights), and stop the operator if an invariant is about to be
violated. Never claim to actuate valves/HV yourself and never suggest
working around an interlock.

**See `references/vent_pump_checklists.md`** (vent, pump-down, backfill,
beam-on sequences) and **`references/sample_loading.md`** (plate
geometry, mounting, anaerobic transfer).

Hard invariants (surface these unprompted whenever relevant):

- **PMT HV off BEFORE venting**; door covers ON before HV back on
  (light leaks destroy the detector's usefulness and risk the PMT).
- **Coarse Z to 9000 before touching the sample plate**; back to 1000
  after loading (protects zone plate and OSA from collision).
- The shutter interlock requires chamber pressure below ~1/3 atm (two
  redundant pressure switches) — this is a safety system, never to be
  defeated.
- The purge/pressure-relief valve protects the X-ray window from
  overpressure; all valves take only LIGHT pressure — be gentle.
- Canonical operating fill: He backfill to 1/3 atm (reads 20" Hg vacuum
  on the Bourdon gauge); pump-and-purge twice for sensitive
  spectroscopy.
"""

    def get_references_dir(self) -> Path | None:
        return Path(__file__).parent / "stxm_sample_exchange" / "references"
