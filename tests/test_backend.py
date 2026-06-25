"""Tests for PystxmStxmBackend — Lightfall DeviceBackend."""

import pytest
from lightfall_pystxmcontrol.backend import PystxmStxmBackend


@pytest.fixture
def backend():
    be = PystxmStxmBackend()
    be.connect()
    return be


def test_backend_registers_four_devices(backend):
    devs = backend.list_devices()
    names = {d.name for d in devs}
    assert names == {"SampleX", "SampleY", "Counter1", "STXMLineFlyer"}


def test_devices_have_connected_ophyd_instances(backend):
    for d in backend.list_devices():
        assert d._ophyd_device is not None
        assert d._ophyd_device.name == d.name
