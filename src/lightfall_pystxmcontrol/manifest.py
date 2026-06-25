"""Lightfall plugin manifest for lightfall-pystxmcontrol."""

from lightfall.plugins import PluginEntry, PluginManifest

manifest = PluginManifest(
    name="lightfall-pystxmcontrol",
    plugins=[
        PluginEntry(
            "device_backend",
            "pystxmcontrol",
            "lightfall_pystxmcontrol.plugin:PystxmBackendPlugin",
        ),
        PluginEntry(
            "plan",
            "stxm_fly_raster",
            "lightfall_pystxmcontrol.plan_plugin:StxmFlyRasterPlanPlugin",
        ),
    ],
)
