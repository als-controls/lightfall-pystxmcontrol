"""The packaged pystxm_happi.json loads 5 devices through HappiBackend."""
from importlib.resources import files

from lightfall.devices.backends.happi import HappiBackend


def _db_path():
    return str(files("lightfall_pystxmcontrol").joinpath("pystxm_happi.json"))


def test_backend_loads_five_devices():
    be = HappiBackend(path=_db_path(), instantiate="background")
    be.connect()
    names = {d.name for d in be.list_devices(active_only=False)}
    assert names == {"SampleX", "SampleY", "Counter1", "STXMLineFlyer", "energy"}


def test_device_classes_match_epics_devices():
    be = HappiBackend(path=_db_path(), instantiate="background")
    be.connect()
    by_name = {d.name: d for d in be.list_devices(active_only=False)}
    assert by_name["SampleX"].device_class == "ophyd.EpicsMotor"
    assert by_name["SampleY"].device_class == "ophyd.EpicsMotor"
    assert by_name["energy"].device_class == "ophyd.EpicsMotor"
    assert (by_name["Counter1"].device_class
            == "lightfall_pystxmcontrol.devices.StxmCounter")
    assert (by_name["STXMLineFlyer"].device_class
            == "lightfall_pystxmcontrol.flyer.StxmLineFlyer")
