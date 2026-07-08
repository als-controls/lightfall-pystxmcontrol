# tests/test_energy_stack_plan.py
"""Task 5: stxm_energy_stack — documents-level contract tests (spec §3.2, §4)."""
import asyncio

import numpy as np
import pytest
from bluesky import RunEngine

from lightfall_pystxmcontrol import config, contract
from lightfall_pystxmcontrol.devices import PystxmAxis
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
from lightfall_pystxmcontrol.plans import stxm_energy_stack, stxm_fly_raster

NE, NY, NX = 2, 3, 4
ENERGIES = [500.0, 510.0]


def _devices(flyer_cls=PystxmLineFlyer):
    flyer = flyer_cls(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"])
    y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")
    en = PystxmAxis(config.DEFAULT_AXES["energy"], name="energy")

    async def _c():
        await flyer.connect(mock=False)
        await y.connect(mock=False)
        await en.connect(mock=False)
    asyncio.run(_c())
    return flyer, en, y


def _run(flyer, en, y):
    docs = []
    RE = RunEngine()
    RE(stxm_energy_stack(flyer, en, y, energies=ENERGIES,
                         y_start=-2, y_stop=2, ny=NY,
                         x_start=-4, x_stop=4, nx=NX, dwell_ms=1.0),
       lambda n, d: docs.append((n, d)))
    return docs


def test_emits_nE_times_ny_lines_and_validates():
    docs = _run(*_devices())
    names = [n for n, _ in docs]
    assert names.count("event_page") == NE * NY
    assert contract.validate_run_documents(docs) == [], contract.validate_run_documents(docs)


def test_start_doc_stxm_block():
    docs = _run(*_devices())
    start = next(d for n, d in docs if n == "start")
    s = start["stxm"]
    assert s["shape"] == [NE, NY, NX]
    assert s["energies"] == ENERGIES
    assert s["data_field"] == "STXMLineFlyer"
    assert s["x_motor"] == "SampleX" and s["y_motor"] == "SampleY"
    assert s["energy_motor"] == "energy"
    assert s["x_extent"] == [-4.0, 4.0] and s["y_extent"] == [-2.0, 2.0]


def test_line_shape_and_positive_counts():
    docs = _run(*_devices())
    for _, d in [x for x in docs if x[0] == "event_page"]:
        line = np.asarray(d["data"]["STXMLineFlyer"][0])
        assert line.shape == (NX,)
        assert (line > 0).all()


def test_energy_moves_between_frames():
    flyer, en, y = _devices()
    docs = _run(flyer, en, y)
    # After the run the energy axis sits at the last setpoint.
    assert asyncio.run(en.readback.get_value()) == ENERGIES[-1]


class _PoisonFlyer(PystxmLineFlyer):
    """Raises in complete() on the (k+1)-th row — mid-row abort simulation."""
    FAIL_AT_ROW = 4  # 0-based global line index

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._rows_done = 0

    def complete(self):
        if self._rows_done == self.FAIL_AT_ROW:
            raise RuntimeError("detector died mid-row")
        self._rows_done += 1
        return super().complete()


def test_abort_mid_row_emits_no_partial_event():
    flyer, en, y = _devices(_PoisonFlyer)
    docs = []
    RE = RunEngine()
    with pytest.raises(RuntimeError):
        RE(stxm_energy_stack(flyer, en, y, energies=ENERGIES,
                             y_start=-2, y_stop=2, ny=NY,
                             x_start=-4, x_stop=4, nx=NX, dwell_ms=1.0),
           lambda n, d: docs.append((n, d)))
    names = [n for n, _ in docs]
    assert names.count("event_page") == _PoisonFlyer.FAIL_AT_ROW  # only whole lines
    for _, d in [x for x in docs if x[0] == "event_page"]:
        assert len(d["data"]["STXMLineFlyer"][0]) == NX  # every emitted line is full (§4.2)
    stop = next(d for n, d in docs if n == "stop")
    assert stop["exit_status"] != "success"
    assert contract.validate_run_documents(docs) == []  # partial runs are valid data (§4.3)


def test_fly_raster_records_extents():
    flyer, _, y = _devices()
    docs = []
    RE = RunEngine()
    RE(stxm_fly_raster(flyer, y, y_start=-2, y_stop=2, ny=2,
                       x_start=-4, x_stop=4, nx=NX, dwell=1.0),
       lambda n, d: docs.append((n, d)))
    start = next(d for n, d in docs if n == "start")
    assert start["x_extent"] == [-4.0, 4.0] and start["y_extent"] == [-2.0, 2.0]
