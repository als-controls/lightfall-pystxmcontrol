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


def test_instantiate_builds_expected_classes():
    from lightfall_pystxmcontrol.devices import PystxmAxis, PystxmCounter
    from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
    be = HappiBackend(path=_db_path(), instantiate="background")
    be.connect()
    by_name = {d.name: d for d in be.list_devices(active_only=False)}
    assert isinstance(be.instantiate(by_name["SampleX"]), PystxmAxis)
    assert isinstance(be.instantiate(by_name["Counter1"]), PystxmCounter)
    assert isinstance(be.instantiate(by_name["STXMLineFlyer"]), PystxmLineFlyer)
