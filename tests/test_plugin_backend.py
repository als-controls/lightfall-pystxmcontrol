"""PystxmBackendPlugin vends a HappiBackend over the packaged device DB."""
from lightfall.devices.backends.happi import HappiBackend
from lightfall.plugins.happi_database_plugin import HappiDatabasePlugin

from lightfall_pystxmcontrol.plugin import PystxmBackendPlugin


def test_plugin_is_happi_database_plugin():
    assert issubclass(PystxmBackendPlugin, HappiDatabasePlugin)
    assert PystxmBackendPlugin().name == "pystxmcontrol"


def test_create_backend_points_at_packaged_db():
    plugin = PystxmBackendPlugin()
    assert plugin.database_path().name == "pystxm_happi.json"
    backend = plugin.create_backend()
    assert isinstance(backend, HappiBackend)
    backend.connect()
    names = {d.name for d in backend.list_devices(active_only=False)}
    assert names == {"SampleX", "SampleY", "Counter1", "STXMLineFlyer"}
