# tests/test_backend_flyer.py — updated to use HappiBackend (PystxmStxmBackend retired)
from importlib.resources import files

import happi.loader
from lightfall.devices.backends.happi import HappiBackend
from lightfall.devices.model import DeviceCategory
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer


def _backend():
    db = str(files("lightfall_pystxmcontrol").joinpath("pystxm_happi.json"))
    be = HappiBackend(path=db, instantiate="background")
    be.connect()
    return be


def test_backend_registers_flyer_device():
    backend = _backend()

    flyer_info = backend.get_device_by_name("STXMLineFlyer")
    assert flyer_info is not None
    # PystxmLineFlyer implements bluesky.protocols.Flyable → DETECTOR via MRO map
    assert flyer_info.category == DeviceCategory.DETECTOR
    assert flyer_info.device_class == "lightfall_pystxmcontrol.flyer.PystxmLineFlyer"
    # Clear happi's process-global object cache so we always get a freshly-constructed
    # object regardless of test-execution order.  happi.loader.cache is keyed by device
    # name; removing the entry forces from_container() to call __init__ again.
    happi.loader.cache.pop("STXMLineFlyer", None)
    # instantiate builds the object (daq not yet connected — that happens in check_connection)
    obj = backend.instantiate(flyer_info)
    assert isinstance(obj, PystxmLineFlyer)
    assert obj._daq is None  # sim daq built lazily in connect()


def test_backend_still_registers_phase1_devices():
    backend = _backend()
    names = {d.name for d in backend.list_devices(active_only=False)}
    assert {"SampleX", "SampleY", "Counter1", "STXMLineFlyer"} <= names
    # HappiBackend's _guess_category maps bluesky protocol subclasses via MRO:
    # Movable→MOTOR, Triggerable/Flyable→DETECTOR.  All four devices must be present.
    assert backend.get_device_by_name("Counter1") is not None
