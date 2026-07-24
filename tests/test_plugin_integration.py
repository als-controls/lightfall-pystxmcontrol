"""Integration tests for the Lightfall plugin + manifest + entry point.

TDD: written before plugin.py / manifest.py exist.
Expected RED state: ModuleNotFoundError on PystxmBackendPlugin import.
"""

import importlib.metadata


def test_plugin_creates_backend():
    from lightfall_pystxmcontrol.plugin import PystxmBackendPlugin

    plugin = PystxmBackendPlugin()
    assert plugin.name == "pystxmcontrol"
    be = plugin.create_backend()
    be.connect()
    assert len(be.list_devices()) == 5


# NOTE: test_grid_scan_via_backend_devices was removed here — it called
# asyncio.run(x.connect()) on backend-instantiated devices, assuming the
# ophyd-async sim device API (PystxmAxis/PystxmCounter). The post-migration
# devices are classic ophyd (ophyd.EpicsMotor, StxmCounter) requiring a live
# EPICS IOC to connect, so this needs the caproto sim fleet fixture, not a
# bare RunEngine. Equivalent coverage over the real fleet is restored in
# Task 5's e2e suite.


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
    # The sim device_backend entry is intentionally disabled in the manifest
    # (integration testing runs against real hardware); make sure it stays out.
    assert not any(
        isinstance(p, PluginEntry) and p.type_name == "device_backend"
        for p in loaded.plugins
    ), f"Sim device_backend should be disabled, found: {loaded.plugins}"
    assert any(
        isinstance(p, PluginEntry)
        and p.type_name == "plan"
        and p.name == "stxm_fly_raster"
        for p in loaded.plugins
    ), f"No stxm_fly_raster PluginEntry found in manifest.plugins: {loaded.plugins}"
