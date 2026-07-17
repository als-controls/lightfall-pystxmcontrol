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
    flyer.prepare(y=2.0, x_start=-3.0, x_stop=3.0, nx=nx, dwell=1.0).wait(timeout=60)
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
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0).wait(timeout=60)
    desc = flyer.describe_collect()["primary"]
    assert desc["Counter1"]["dtype"] == "array"
    assert desc["Counter1"]["shape"] == [4]
    assert desc["SampleX"]["dtype"] == "array"
    assert desc["SampleX"]["shape"] == [4]
    assert desc["SampleY"]["dtype"] == "number"


def test_prepare_rejects_out_of_limit_line(flyer):
    with pytest.raises(RuntimeError, match="(?i)limit"):
        flyer.prepare(y=0.0, x_start=-5000.0, x_stop=1.0, nx=4, dwell=1.0).wait(timeout=60)
    # recovery: a valid prepare works afterwards
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0).wait(timeout=60)


def test_failed_prepare_invalidates_prior_cycle_state(flyer):
    # successful cycle first
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0).wait(timeout=60)
    flyer.kickoff().wait(timeout=30)
    flyer.complete().wait(timeout=60)
    list(flyer.collect())
    # failed prepare must not leave the previous row's state behind
    with pytest.raises(RuntimeError, match="(?i)limit"):
        flyer.prepare(y=0.0, x_start=-5000.0, x_stop=1.0, nx=4, dwell=1.0).wait(timeout=60)
    with pytest.raises(RuntimeError, match="before prepare"):
        flyer.kickoff()


def test_consecutive_rows_index_advances(flyer):
    for row, y in enumerate((0.0, 1.0)):
        flyer.prepare(y=y, x_start=-2.0, x_stop=2.0, nx=5, dwell=1.0).wait(timeout=60)
        flyer.kickoff().wait(timeout=30)
        flyer.complete().wait(timeout=60)
        (event,) = list(flyer.collect())
        assert event["data"]["SampleY"] == pytest.approx(y)
        assert len(event["data"]["Counter1"]) == 5


# -- Fix A: Preparable protocol -------------------------------------------

def test_flyer_is_preparable(flyer):
    from bluesky.protocols import Preparable
    assert isinstance(flyer, Preparable)


def test_prepare_returns_status_that_resolves_success(flyer):
    from ophyd.status import Status
    st = flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0)
    # prepare() runs its blocking CA puts on a background thread and hands
    # back a Status the caller awaits (rather than blocking in-line). We do
    # not assert st.done is False here -- the sim worker can resolve in
    # <10ms, so that would be racy -- only that it is a Status that resolves.
    assert isinstance(st, Status)
    st.wait(timeout=60)
    assert st.success
    # the flyer is left in a usable, ARMED state after the Status resolves
    flyer.kickoff().wait(timeout=30)
    flyer.complete().wait(timeout=60)
    list(flyer.collect())


def test_overlapping_prepare_second_call_wins(flyer, monkeypatch):
    """A second prepare() issued before the first's worker finishes must win:
    the superseded first worker must not clobber _row/_index0 nor report
    success against the newer call (epoch/lost-update guard).

    We deterministically hold the FIRST worker at its ARM step (past its
    config puts, so it isn't holding an ophyd per-signal set lock -- that
    lock is a *separate* guard that would otherwise non-deterministically
    decide which worker's set() collides first). While the first worker is
    parked, the second prepare runs to completion and takes over the state;
    then we release the first worker and confirm it no-ops rather than
    corrupting the second's row.
    """
    import threading
    import time as _t
    from ophyd.status import Status

    release = threading.Event()
    seen_arm = []
    original_arm_set = flyer.arm.set

    def gated_arm_set(*args, **kwargs):
        seen_arm.append(1)
        if len(seen_arm) == 1:  # the first worker: park here until released
            assert release.wait(timeout=30), "first worker never released"
        return original_arm_set(*args, **kwargs)

    monkeypatch.setattr(flyer.arm, "set", gated_arm_set)

    first = flyer.prepare(y=1.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0)
    assert isinstance(first, Status)
    # Wait until the first worker has finished its 4 config puts and reached
    # the (gated) ARM -- guarantees its sets are done, so the second worker's
    # sets won't collide with them on the ophyd per-signal lock.
    for _ in range(500):
        if seen_arm:
            break
        _t.sleep(0.01)
    assert seen_arm, "first worker never reached ARM"

    # Second prepare now runs cleanly to completion and must win.
    second = flyer.prepare(y=2.0, x_start=-2.0, x_stop=2.0, nx=7, dwell=1.0)
    assert isinstance(second, Status)
    second.wait(timeout=60)
    assert second.success
    assert flyer._row["nx"] == 7  # second's state is live
    index0_after_second = flyer._index0

    # Release the parked first worker: it will ARM, see STATE=ARMED, then
    # find its captured epoch stale -> must NOT overwrite _row/_index0 and
    # must fail (not succeed) its own now-orphaned Status.
    release.set()
    exc = first.exception(timeout=60)  # blocks until done
    assert first.done, "superseded prepare() Status left unresolved"
    assert not first.success, "stale first prepare wrongly reported success"
    assert isinstance(exc, RuntimeError)

    # Ground truth: the stale worker did NOT clobber the second's row.
    assert flyer._row["nx"] == 7
    assert flyer._row["y"] == pytest.approx(2.0)
    assert flyer._index0 == index0_after_second

    # Recovery: a fresh, un-raced prepare/cycle still works end-to-end.
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=5, dwell=1.0).wait(timeout=60)
    flyer.kickoff().wait(timeout=30)
    flyer.complete().wait(timeout=60)
    (event,) = list(flyer.collect())
    assert len(event["data"]["Counter1"]) == 5


def test_prepare_status_carries_arm_failure(flyer):
    from ophyd.status import Status
    st = flyer.prepare(y=0.0, x_start=-5000.0, x_stop=1.0, nx=4, dwell=1.0)
    assert isinstance(st, Status)
    with pytest.raises(RuntimeError, match="(?i)limit"):
        st.wait(timeout=60)
    # recovery
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0).wait(timeout=60)


# -- Fix B: bounded complete() + STATE/ERROR failure path -----------------

def test_complete_returns_bounded_status_for_normal_line(flyer):
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0).wait(timeout=60)
    flyer.kickoff().wait(timeout=30)
    st = flyer.complete()
    assert st.timeout is not None and st.timeout > 0
    st.wait(timeout=60)
    assert st.success
    list(flyer.collect())


def test_complete_fails_fast_when_ioc_state_is_error(flyer):
    """Force STATE=ERROR out-of-band (bad ARM params written directly to the
    signals, bypassing flyer.prepare()'s own validation) so the IOC flips
    :STATE to ERROR *before* complete() is called. This exercises complete()'s
    STATE-subscription failure path deterministically and fast (no need to
    wait out a real dead-IOC timeout): the subscribe(run=True) fires
    immediately with the already-ERROR value, so complete()'s Status should
    fail promptly rather than hang or silently succeed on the GO put (which
    itself completes successfully at the CA level even though the line was
    rejected -- see e712_ioc.go putter's "GO rejected: state is ERROR" path).
    """
    # valid prepare first so self._row/_index0 are set and PVs are connected
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0).wait(timeout=60)

    # force ERROR via raw signals (out-of-limit START), independent of
    # flyer.prepare()'s own invalidation/exception path
    flyer.x_start.set(-5000.0).wait(timeout=10)
    flyer.arm.set(1).wait(timeout=30)
    assert flyer.state.get() == "ERROR"

    flyer.kickoff()  # GO put while STATE=ERROR; the put itself still succeeds
    st = flyer.complete()
    with pytest.raises(RuntimeError, match="(?i)error"):
        st.wait(timeout=15)

    # recovery: a fresh valid prepare/cycle still works afterwards
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0).wait(timeout=60)
    flyer.kickoff().wait(timeout=30)
    flyer.complete().wait(timeout=60)
    list(flyer.collect())
