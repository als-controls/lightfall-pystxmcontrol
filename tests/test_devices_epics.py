"""StxmCounter against the live sim DAQ IOC."""
import time

import pytest


@pytest.fixture(scope="module")
def counter(stxm_fleet):
    from lightfall_pystxmcontrol.devices import StxmCounter
    c = StxmCounter(stxm_fleet.daq_prefix, name="Counter1")
    c.wait_for_connection(timeout=20)
    return c


def test_trigger_completes_after_acquisition(counter):
    counter.dwell.set(150.0).wait(timeout=10)   # ms
    t0 = time.monotonic()
    st = counter.trigger()
    st.wait(timeout=30)
    assert time.monotonic() - t0 >= 0.13, "trigger returned before acquisition"
    assert st.success


def test_read_keys_on_device_name(counter):
    counter.dwell.set(5.0).wait(timeout=10)
    counter.trigger().wait(timeout=30)
    reading = counter.read()
    assert "Counter1" in reading
    assert reading["Counter1"]["value"] > 0
    desc = counter.describe()
    assert "Counter1" in desc


def test_counts_hinted(counter):
    assert "Counter1" in counter.hints.get("fields", [])
