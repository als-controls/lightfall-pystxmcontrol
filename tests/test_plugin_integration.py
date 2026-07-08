"""Integration tests for the Lightfall plugin + manifest + entry point.

TDD: written before plugin.py / manifest.py exist.
Expected RED state: ModuleNotFoundError on PystxmBackendPlugin import.
"""

import importlib.metadata

import bluesky.plans as bp


def test_plugin_creates_backend():
    from lightfall_pystxmcontrol.plugin import PystxmBackendPlugin

    plugin = PystxmBackendPlugin()
    assert plugin.name == "pystxmcontrol"
    be = plugin.create_backend()
    be.connect()
    assert len(be.list_devices()) == 5


def test_grid_scan_via_backend_devices():
    import asyncio

    from bluesky import RunEngine

    from lightfall_pystxmcontrol.plugin import PystxmBackendPlugin

    be = PystxmBackendPlugin().create_backend()
    be.connect()
    # HappiBackend with instantiate="background" defers ophyd construction
    # until the Qt DeviceConnectionManager fires. In tests without a Qt event
    # loop, call be.instantiate() explicitly then connect() so _motor/_daq are
    # initialised before the RunEngine drives the plan.
    x = be.instantiate(be.get_device_by_name("SampleX"))
    y = be.instantiate(be.get_device_by_name("SampleY"))
    det = be.instantiate(be.get_device_by_name("Counter1"))
    asyncio.run(x.connect())
    asyncio.run(y.connect())
    asyncio.run(det.connect())

    docs = []
    RunEngine()(bp.grid_scan([det], x, -1, 1, 2, y, -1, 1, 2),
                lambda n, d: docs.append(n))
    assert docs.count("event") == 4


def test_entry_point_registered():
    """Verify the lightfall.plugins entry point is registered after pip install -e."""
    from lightfall.plugins import PluginEntry, PluginManifest

    eps = importlib.metadata.entry_points(group="lightfall.plugins")
    names = [ep.name for ep in eps]
    assert "pystxmcontrol" in names, (
        f"Entry point 'pystxmcontrol' not found in lightfall.plugins; found: {names}"
    )

    ep = next(e for e in eps if e.name == "pystxmcontrol")
    loaded = ep.load()
    assert isinstance(loaded, PluginManifest), (
        f"Expected PluginManifest, got {type(loaded)}"
    )
    assert any(
        isinstance(p, PluginEntry)
        and p.type_name == "device_backend"
        and p.name == "pystxmcontrol"
        for p in loaded.plugins
    ), f"No matching PluginEntry found in manifest.plugins: {loaded.plugins}"
