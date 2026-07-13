"""Regenerate tests/fixtures/golden_energy_stack_run.json from a sim run.

Counts are Poisson (non-deterministic); the fixture is validated STRUCTURALLY
(contract.validate_run_documents), never on exact values. Rerun after any
intentional contract change and commit the result.

REQUIRES A RUNNING SIM FLEET (spec #2 caproto IOCs, e.g. the ``stxm-iocs``
supervisor or the ``stxm_fleet`` pytest fixture in tests/conftest.py) with
EPICS_CA_ADDR_LIST pointed at it, so the PVs below resolve. This script does
NOT spawn IOCs itself -- start the fleet first (see
_pystxmcontrol_iocs_wt/pystxmcontrol/iocs/supervisor.py), then, with
EPICS_CA_ADDR_LIST set to reach it:

    C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/make_golden_fixture.py

The PV names below match the packaged happi DB (tests/test_happi_db.py):
SampleY -> STXMSIM:E712:SampleY, energy -> STXMSIM:XPS:energy,
flyer prefix -> STXMSIM:E712:FLY.
"""
import json
from pathlib import Path

import numpy as np

from lightfall_pystxmcontrol import epics_env

epics_env.ensure_caproto_layer()  # before any ophyd import

from ophyd import EpicsMotor  # noqa: E402

from lightfall_pystxmcontrol.flyer import StxmLineFlyer  # noqa: E402
from lightfall_pystxmcontrol.plans import stxm_energy_stack  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_energy_stack_run.json"

SAMPLE_Y_PV = "STXMSIM:E712:SampleY"
ENERGY_PV = "STXMSIM:XPS:energy"
FLY_PREFIX = "STXMSIM:E712:FLY"


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
    from bluesky import RunEngine

    y = EpicsMotor(SAMPLE_Y_PV, name="SampleY")
    en = EpicsMotor(ENERGY_PV, name="energy")
    flyer = StxmLineFlyer(FLY_PREFIX, name="Counter1")
    for d in (y, en, flyer):
        d.wait_for_connection(timeout=30)

    docs = []
    RE = RunEngine({})
    RE(stxm_energy_stack(flyer, en, y, energies=[500.0, 510.0],
                         y_start=-2, y_stop=2, ny=3,
                         x_start=-4, x_stop=4, nx=4, dwell_ms=1.0),
       lambda n, d: docs.append([n, _jsonable(dict(d))]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(docs, indent=1))
    print(f"Wrote {OUT} ({len(docs)} documents)")


if __name__ == "__main__":
    main()
