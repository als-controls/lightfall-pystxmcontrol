"""Lightfall DeviceBackendPlugin for pystxmcontrol simulated STXM devices."""

from lightfall.plugins.device_backend_plugin import DeviceBackendPlugin

from .backend import PystxmStxmBackend


class PystxmBackendPlugin(DeviceBackendPlugin):
    """Lightfall plugin that exposes simulated pystxmcontrol STXM devices.

    Registered as a ``device_backend`` plugin under the ``lightfall.plugins``
    entry-point group.  Calling :meth:`create_backend` returns a fresh
    :class:`~lightfall_pystxmcontrol.backend.PystxmStxmBackend` instance
    ready to be connected.
    """

    @property
    def name(self) -> str:
        """Return the plugin / backend identifier."""
        return "pystxmcontrol"

    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Simulated pystxmcontrol STXM devices (motors + counter)"

    def create_backend(self) -> PystxmStxmBackend:
        """Instantiate and return a new PystxmStxmBackend."""
        return PystxmStxmBackend()
