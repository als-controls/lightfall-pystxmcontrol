"""Lightfall HappiDatabasePlugin for pystxmcontrol simulated STXM devices."""
from lightfall.plugins.happi_database_plugin import HappiDatabasePlugin


class PystxmBackendPlugin(HappiDatabasePlugin):
    """Exposes simulated pystxmcontrol STXM devices from a packaged happi DB.

    Registered as a ``device_backend`` plugin under the ``lightfall.plugins``
    entry-point group. The device set ships as ``pystxm_happi.json`` inside this
    package and is loaded by Lightfall's built-in HappiBackend.
    """

    database_resource = ("lightfall_pystxmcontrol", "pystxm_happi.json")
    instantiate = "background"

    @property
    def name(self) -> str:
        return "pystxmcontrol"

    @property
    def description(self) -> str:
        return "Simulated pystxmcontrol STXM devices (motors + counter)"
