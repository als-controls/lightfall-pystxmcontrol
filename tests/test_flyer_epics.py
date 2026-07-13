"""StxmLineFlyer against the live sim E712 FLY IOC."""
import numpy as np
import pytest


@pytest.fixture(scope="module")
def flyer(stxm_fleet):
    from lightfall_pystxmcontrol.flyer import StxmLineFlyer
    fl = StxmLineFlyer(stxm_fleet.fly_prefix, name="Counter1")
    fl.wait_for_connection(timeout=20)
    return fl


def test_one_cycle_yields_one_line_event(flyer):
    nx = 6
    flyer.prepare(y=2.0, x_start=-3.0, x_stop=3.0, nx=nx, dwell=1.0)
    flyer.kickoff().wait(timeout=30)
    flyer.complete().wait(timeout=60)
    events = list(flyer.collect())
    assert len(events) == 1
    data = events[0]["data"]
    assert len(data["Counter1"]) == nx
    assert (np.asarray(data["Counter1"]) > 0).all()
    assert len(data["SampleX"]) == nx
    assert data["SampleX"][0] == pytest.approx(-3.0)
    assert data["SampleX"][-1] == pytest.approx(3.0)
    assert data["SampleY"] == pytest.approx(2.0)


def test_describe_collect_reports_arrays(flyer):
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0)
    desc = flyer.describe_collect()["primary"]
    assert desc["Counter1"]["dtype"] == "array"
    assert desc["Counter1"]["shape"] == [4]
    assert desc["SampleX"]["dtype"] == "array"
    assert desc["SampleX"]["shape"] == [4]
    assert desc["SampleY"]["dtype"] == "number"


def test_prepare_rejects_out_of_limit_line(flyer):
    with pytest.raises(RuntimeError, match="(?i)limit"):
        flyer.prepare(y=0.0, x_start=-5000.0, x_stop=1.0, nx=4, dwell=1.0)
    # recovery: a valid prepare works afterwards
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0)


def test_consecutive_rows_index_advances(flyer):
    for row, y in enumerate((0.0, 1.0)):
        flyer.prepare(y=y, x_start=-2.0, x_stop=2.0, nx=5, dwell=1.0)
        flyer.kickoff().wait(timeout=30)
        flyer.complete().wait(timeout=60)
        (event,) = list(flyer.collect())
        assert event["data"]["SampleY"] == pytest.approx(y)
        assert len(event["data"]["Counter1"]) == 5
