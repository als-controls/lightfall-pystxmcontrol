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

from lightfall.plugins.agent_plugin import AgentPlugin


class StxmScanSetupAgent(AgentPlugin):
    """Skill for configuring STXM scans (images, stacks, linescans, maps)."""

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

    def get_system_prompt(self) -> str:
        return """## STXM Scan Setup

Expertise in configuring STXM acquisitions with the `stxm_fly_raster` and
`stxm_energy_stack` plans (positions in um; dwell in MILLISECONDS).

**See `references/scan_setup.md`** for the full playbook (scan-type
selection, progressive zoom, I0 regions, dwell and stack strategy) and
**`references/bl5322_numbers.md`** for Beamline 5.3.2.2-specific values
(slits, survey settings, fine/coarse gotchas).

Core rules to apply when helping plan a scan:

- **Pick the cheapest scan type that answers the question**: single-energy
  image for morphology; 2-energy map (below/above edge) for elemental
  contrast; linescan for spectra along one line; full energy stack only
  when per-pixel XANES is needed (stacks can take hours).
- **Always leave an I0 blank region** (sample-free area) inside stack and
  linescan fields — STXMs have no I0 monitor; quantitative OD conversion
  is impossible without it.
- **Zoom progressively** (survey -> feature -> fine scan), refocusing as
  the field shrinks. Never jump straight to a fine scan on a fresh sample.
- **Dwell trade-off**: longer dwell = better statistics + more dose/damage.
  Scan overhead accrues per trajectory (per line), not per pixel — a few
  large scans beat many small ones.
- **Keep OD <~ 1** in the analyzed regions: thicker areas saturate
  (peak blunting) and are not recoverable in analysis.
- **Energy stacks**: define energies as (start, stop, n_points) rows —
  fine steps (~0.1 eV) only across the near-edge region, coarse steps in
  pre-edge and post-edge tails. Bracket the edge with enough pre-edge
  baseline for background fitting.
"""

    def get_references_dir(self) -> Path | None:
        return Path(__file__).parent / "stxm_scan_setup" / "references"
