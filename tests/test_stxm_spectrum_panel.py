from unittest.mock import MagicMock

import numpy as np
import pytest

from lightfall_pystxmcontrol.manifest import manifest
from lightfall_pystxmcontrol.stxm_analysis_client import StxmAnalysisClient
from lightfall_pystxmcontrol.stxm_spectrum_panel import (
    StxmSpectrumPanel, StxmSpectrumPanelPlugin)


@pytest.fixture
def panel(qtbot, fake_ipc):
    client = StxmAnalysisClient(ipc=fake_ipc)
    binder = MagicMock()
    binder.enabled = False
    p = StxmSpectrumPanel(client=client, binder=binder)
    qtbot.addWidget(p)
    p.test_ipc = fake_ipc
    p.test_binder = binder
    return p


def test_metadata(panel):
    md = panel.panel_metadata
    assert md.id == "lightfall_pystxmcontrol.panels.stxm_spectrum"
    assert md.default_area != "center"


def test_spectrum_event_updates_curve(panel):
    panel.test_ipc.emit("stxm.spectrum.updated", {
        "run_uid": "u", "energies": [500.0, 510.0],
        "intensity": [2.0, None], "energies_done": 1, "seq": 1})
    x, y = panel._curve.getData()
    assert list(x) == [500.0, 510.0]
    assert y[0] == 2.0 and np.isnan(y[1])


def test_toggle_drives_binder(panel):
    panel._enable_toggle.setChecked(True)
    panel.test_binder.enable.assert_called_once()
    panel._enable_toggle.setChecked(False)
    panel.test_binder.disable.assert_called_once()


def test_toggle_rollback_on_error(panel):
    panel.test_binder.enable.side_effect = RuntimeError("no ipc")
    panel._enable_toggle.setChecked(True)
    assert panel._enable_toggle.isChecked() is False


def test_status_and_error_labels(panel):
    panel.test_ipc.emit("stxm.status", {
        "run_uid": "u", "state": "reducing", "energies_done": 1, "total": 2})
    assert "reducing" in panel._status_label.text()
    panel.test_ipc.emit("stxm.error", {"run_uid": "u", "error": "boom"})
    assert "boom" in panel._status_label.text()


def test_close_disables_binder(panel):
    panel._on_closing()
    panel.test_binder.disable.assert_called()


def test_plugin_and_manifest():
    plugin = StxmSpectrumPanelPlugin()
    assert plugin.name == "stxm_spectrum"
    cls = plugin.get_panel_class()
    assert cls.panel_metadata.id == "lightfall_pystxmcontrol.panels.stxm_spectrum"
    entries = [p for p in manifest.plugins
               if p.type_name == "panel" and p.name == "stxm_spectrum"]
    assert len(entries) == 1
