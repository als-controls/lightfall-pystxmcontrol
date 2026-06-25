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
    assert len(be.list_devices()) == 4


def test_grid_scan_via_backend_devices():
    from bluesky import RunEngine

    from lightfall_pystxmcontrol.plugin import PystxmBackendPlugin

    be = PystxmBackendPlugin().create_backend()
    be.connect()
    x = be.get_device_by_name("SampleX")._ophyd_device
    y = be.get_device_by_name("SampleY")._ophyd_device
    det = be.get_device_by_name("Counter1")._ophyd_device

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
