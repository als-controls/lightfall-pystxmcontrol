"""Regenerate tests/fixtures/golden_energy_stack_run.json from a sim run.

Counts are Poisson (non-deterministic); the fixture is validated STRUCTURALLY
(contract.validate_run_documents), never on exact values. Rerun after any
intentional contract change and commit the result.

    C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/make_golden_fixture.py
"""
import asyncio
import json
from pathlib import Path

import numpy as np
from bluesky import RunEngine

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmAxis
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
from lightfall_pystxmcontrol.plans import stxm_energy_stack

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_energy_stack_run.json"


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


def main() -> None:
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"])
    y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")
    en = PystxmAxis(config.DEFAULT_AXES["energy"], name="energy")

    async def _c():
        await flyer.connect(mock=False); await y.connect(mock=False); await en.connect(mock=False)
    asyncio.run(_c())

    docs = []
    RE = RunEngine()
    RE(stxm_energy_stack(flyer, en, y, energies=[500.0, 510.0],
                         y_start=-2, y_stop=2, ny=3,
                         x_start=-4, x_stop=4, nx=4, dwell_ms=1.0),
       lambda n, d: docs.append([n, _jsonable(dict(d))]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(docs, indent=1))
    print(f"Wrote {OUT} ({len(docs)} documents)")


if __name__ == "__main__":
    main()
