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


# === Unified load pipeline ===
# DeviceCatalog._load_and_connect_backend drives backends through three hooks
# on startup: connect() (worker) -> load_metadata() -> per-device instantiate()
# + check_connection() (via DeviceConnectionManager). These exercise that path
# directly, the way the catalog does, rather than only calling connect().

EXPECTED_NAMES = {"SampleX", "SampleY", "Counter1", "STXMLineFlyer"}


def test_load_metadata_returns_device_infos(backend):
    infos = backend.load_metadata()
    assert {i.name for i in infos} == EXPECTED_NAMES


def test_load_metadata_connects_if_needed():
    """load_metadata() is self-connecting and idempotent (mirrors MockBackend)."""
    be = PystxmStxmBackend()  # no explicit connect()
    infos = be.load_metadata()
    assert {i.name for i in infos} == EXPECTED_NAMES
    assert be.is_connected


def test_instantiate_returns_matching_ophyd_object(backend):
    for info in backend.load_metadata():
        obj = backend.instantiate(info)
        assert obj is not None
        assert obj.name == info.name


def test_check_connection_true_for_simulated(backend):
    info = backend.load_metadata()[0]
    obj = backend.instantiate(info)
    assert backend.check_connection(obj, timeout=1.0) is True
