"""RunEngine e2e: plans over the live sim fleet; contract v1 must hold."""
import numpy as np
import pytest


@pytest.fixture(scope="module")
def devices(stxm_fleet):
    from ophyd import EpicsMotor
    from lightfall_pystxmcontrol.flyer import StxmLineFlyer
    y = EpicsMotor(stxm_fleet.motor_pv["SampleY"], name="SampleY")
    energy = EpicsMotor(stxm_fleet.motor_pv["energy"], name="energy")
    flyer = StxmLineFlyer(stxm_fleet.fly_prefix, name="Counter1")
    for d in (y, energy, flyer):
        d.wait_for_connection(timeout=30)
    return {"y": y, "energy": energy, "flyer": flyer}


def _run(plan):
    from bluesky import RunEngine
    docs = []
    RE = RunEngine({})
    RE(plan, lambda name, doc: docs.append((name, doc)))
    return docs


def _events(docs):
    """Normalize both 'event' and 'event_page' documents into a flat list of
    per-event dicts (this bluesky/RunEngine version emits event_page for
    flyer collect() output, not bare 'event')."""
    import event_model
    out = []
    for name, doc in docs:
        if name == "event":
            out.append(doc)
        elif name == "event_page":
            out.extend(event_model.unpack_event_page(doc))
    return out


def test_fly_raster_end_to_end(devices):
    from lightfall_pystxmcontrol.plans import stxm_fly_raster
    ny, nx = 4, 8
    docs = _run(stxm_fly_raster(
        devices["flyer"], devices["y"],
        y_start=-2.0, y_stop=2.0, ny=ny,
        x_start=-3.0, x_stop=3.0, nx=nx, dwell=1.0))
    names = [n for n, _ in docs]
    assert names[0] == "start" and names[-1] == "stop"
    events = _events(docs)
    assert len(events) == ny
    for ev in events:
        assert len(ev["data"]["Counter1"]) == nx
        assert len(ev["data"]["SampleX"]) == nx
        assert (np.asarray(ev["data"]["Counter1"]) > 0).all()
    ys = [ev["data"]["SampleY"] for ev in events]
    assert ys == sorted(ys)
    (_, stop_doc) = docs[-1]
    assert stop_doc["exit_status"] == "success"


def test_energy_stack_end_to_end_contract(devices):
    from lightfall_pystxmcontrol import contract
    from lightfall_pystxmcontrol.plans import stxm_energy_stack
    energies = [400.0, 401.0]
    ny, nx = 3, 5
    docs = _run(stxm_energy_stack(
        devices["flyer"], devices["energy"], devices["y"],
        energies=energies, y_start=-1.0, y_stop=1.0, ny=ny,
        x_start=-2.0, x_stop=2.0, nx=nx, dwell_ms=1.0))
    events = _events(docs)
    assert len(events) == len(energies) * ny
    errors = contract.validate_run_documents(docs)
    assert errors == [], errors


def test_slow_axis_actually_moved(devices, stxm_fleet):
    """The RunEngine's bps.mv drives the real motor record."""
    from caproto.threading.client import Context
    ctx = Context()
    (rbv,) = ctx.get_pvs(stxm_fleet.motor_pv["SampleY"] + ".RBV")
    rbv.wait_for_connection(timeout=15)
    from lightfall_pystxmcontrol.plans import stxm_fly_raster
    _run(stxm_fly_raster(devices["flyer"], devices["y"],
                         y_start=0.0, y_stop=4.0, ny=2,
                         x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0))
    assert abs(rbv.read().data[0] - 4.0) < 1e-3
