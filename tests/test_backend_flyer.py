# tests/test_backend_flyer.py
from lightfall.devices.model import DeviceCategory

from lightfall_pystxmcontrol.backend import PystxmStxmBackend
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer


def test_backend_registers_flyer_device():
    backend = PystxmStxmBackend()
    assert backend.connect() is True

    flyer_info = backend.get_device_by_name("STXMLineFlyer")
    assert flyer_info is not None
    assert flyer_info.category == DeviceCategory.DETECTOR
    assert flyer_info.device_class == "lightfall_pystxmcontrol.flyer:PystxmLineFlyer"
    assert isinstance(flyer_info._ophyd_device, PystxmLineFlyer)
    # connected flyer: prepared row not required, but the daq must be built
    assert flyer_info._ophyd_device._daq is not None


def test_backend_still_registers_phase1_devices():
    backend = PystxmStxmBackend()
    assert backend.connect() is True
    names = {d.name for d in backend.list_devices()}
    assert {"SampleX", "SampleY", "Counter1", "STXMLineFlyer"} <= names
    assert backend.get_device_by_name("Counter1").category == DeviceCategory.DETECTOR
