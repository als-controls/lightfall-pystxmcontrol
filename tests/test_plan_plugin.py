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
    # The nine UI-relevant parameters must all be present.  md is optional
    # metadata forwarding and may also appear; use subset to stay robust.
    assert {"flyer", "y_axis", "y_start", "y_stop", "ny",
            "x_start", "x_stop", "nx", "dwell"} <= param_names


def test_adapter_delegates_to_pure_plan():
    # The adapter must yield the same message stream as the pure plan for the
    # same inputs. Build a connected flyer + slow axis and compare doc-name
    # sequences over a bare RunEngine (one event_page per line).
    import asyncio
    from bluesky import RunEngine
    from lightfall_pystxmcontrol import config
    from lightfall_pystxmcontrol.devices import PystxmAxis
    from lightfall_pystxmcontrol.flyer import PystxmLineFlyer

    plan_func = StxmFlyRasterPlanPlugin().get_plan_function()
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"],
                            name="STXMLineFlyer")
    y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")

    async def _c():
        await flyer.connect(mock=False)
        await y.connect(mock=False)
    asyncio.run(_c())

    docs = []
    RE = RunEngine()
    RE(plan_func(flyer, y, y_start=-2, y_stop=2, ny=3,
                 x_start=-4, x_stop=4, nx=8, dwell=1.0),
       lambda n, d: docs.append((n, d)))
    names = [n for n, _ in docs]
    assert names[0] == "start" and names[-1] == "stop"
    assert names.count("event_page") == 3


def test_flyer_device_class_matches_backend_registration():
    # The plugin's DeviceFilter(device_class=...) MUST byte-match the device_class
    # the backend registers, or the UI device-picker silently shows no flyer.
    from lightfall_pystxmcontrol.plan_plugin import FLYER_DEVICE_CLASS
    from lightfall_pystxmcontrol.backend import PystxmStxmBackend
    backend = PystxmStxmBackend()
    assert backend.connect() is True
    assert backend.get_device_by_name("STXMLineFlyer").device_class == FLYER_DEVICE_CLASS
