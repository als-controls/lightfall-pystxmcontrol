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
        PluginEntry(
            "plan",
            "stxm_energy_stack",
            "lightfall_pystxmcontrol.plan_plugin:StxmEnergyStackPlanPlugin",
        ),
        PluginEntry(
            "visualization",
            "stxm_map",
            "lightfall_pystxmcontrol.stxm_map_viz:StxmMapVizPlugin",
        ),
        PluginEntry(
            "visualization",
            "stxm_stack",
            "lightfall_pystxmcontrol.stxm_stack_viz:StxmStackVizPlugin",
        ),
        PluginEntry(
            "panel",
            "stxm_scan",
            "lightfall_pystxmcontrol.scan_panel:StxmScanPanelPlugin",
            preload=True,
        ),
        PluginEntry("panel", "stxm_spectrum",
                    "lightfall_pystxmcontrol.stxm_spectrum_panel:StxmSpectrumPanelPlugin",
                    preload=True),
        PluginEntry(
            "agent",
            "stxm_scan_setup",
            "lightfall_pystxmcontrol.agents.stxm_scan_setup:StxmScanSetupAgent",
        ),
    ],
)
