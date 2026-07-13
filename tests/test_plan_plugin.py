# tests/test_plan_plugin.py
from lightfall_pystxmcontrol.plan_plugin import StxmFlyRasterPlanPlugin


def test_plan_plugin_identity():
    plugin = StxmFlyRasterPlanPlugin()
    assert plugin.name == "stxm_fly_raster"
    assert plugin.category == "stxm"


def test_plan_info_exposes_expected_parameters():
    plugin = StxmFlyRasterPlanPlugin()
    info = plugin.get_plan_info()
    param_names = {p.name for p in info.parameters}
    assert {"flyer", "y_axis", "y_start", "y_stop", "ny",
            "x_start", "x_stop", "nx", "dwell"} == param_names


# NOTE: test_adapter_delegates_to_pure_plan (RunEngine over live sim devices)
# was removed here — it built PystxmAxis/PystxmLineFlyer sim-only ophyd-async
# devices that no longer exist post-EPICS-migration. Equivalent coverage over
# real EPICS devices (the caproto sim fleet) is restored in Task 5's e2e suite.


def test_flyer_device_class_matches_backend_registration():
    # The plugin's DeviceFilter(device_class=...) MUST byte-match the device_class
    # the backend registers, or the UI device-picker silently shows no flyer.
    from importlib.resources import files

    from lightfall.devices.backends.happi import HappiBackend
    from lightfall_pystxmcontrol.plan_plugin import FLYER_DEVICE_CLASS

    assert FLYER_DEVICE_CLASS == "lightfall_pystxmcontrol.flyer.StxmLineFlyer"
    db = str(files("lightfall_pystxmcontrol").joinpath("pystxm_happi.json"))
    backend = HappiBackend(path=db, instantiate="background")
    backend.connect()
    assert backend.get_device_by_name("STXMLineFlyer").device_class == FLYER_DEVICE_CLASS
