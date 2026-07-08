# tests/test_scan_panel.py
"""Tasks 12-13: STXM scan-definition panel (spec §3.3)."""
import numpy as np
import pytest
from unittest.mock import MagicMock


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _FakeNode:
    def __init__(self, arr):
        self._arr = np.asarray(arr, dtype=float)

    def read(self):
        return self._arr


class _FakeEntry:
    """Duck-type of a Tiled BlueskyRun entry for a completed fly-raster run."""
    def __init__(self, arr, x_extent=(-4.0, 4.0), y_extent=(-2.0, 2.0),
                 plan="stxm_fly_raster", detectors=("STXMLineFlyer",)):
        self.metadata = {"start": {
            "plan_name": plan, "detectors": list(detectors),
            "x_extent": list(x_extent), "y_extent": list(y_extent),
        }}
        self._arr = arr

    def __getitem__(self, key):
        if key == "primary":
            return {"STXMLineFlyer": _FakeNode(self._arr)}
        raise KeyError(key)


class _FakeTiledClient(dict):
    pass


def _panel(qtbot, client=None, catalog=None, engine=None):
    from lightfall_pystxmcontrol.scan_panel import STXMScanPanel
    _qapp()
    p = STXMScanPanel(catalog=catalog or MagicMock(), engine=engine or MagicMock(),
                      tiled_client=client if client is not None else _FakeTiledClient())
    qtbot.addWidget(p)
    return p


class TestRegionMapping:
    def test_region_to_plan_kwargs(self):
        from lightfall_pystxmcontrol.scan_panel import region_to_plan_kwargs
        kw = region_to_plan_kwargs(pos=(-3.0, -1.0), size=(2.0, 3.0))
        assert kw == {"x_start": -3.0, "x_stop": -1.0, "y_start": -1.0, "y_stop": 2.0}


class TestContextImage:
    def test_load_run_positions_image_in_motor_coords(self, qtbot):
        client = _FakeTiledClient()
        client["u1"] = _FakeEntry(np.ones((3, 5)))
        p = _panel(qtbot, client=client)
        p.load_run("u1")
        assert p.current_extents() == (-4.0, 4.0, -2.0, 2.0)
        # boundingRect() is local/pixel space in pyqtgraph; mapRectToView reflects the setRect placement in motor coords.
        r = p._image_item.mapRectToView(p._image_item.boundingRect())
        assert (r.left(), r.top(), r.width(), r.height()) == (-4.0, -2.0, 8.0, 4.0)

    def test_load_run_missing_uid_sets_error_not_raise(self, qtbot):
        p = _panel(qtbot, client=_FakeTiledClient())
        p.load_run("nope")  # must not raise
        assert "nope" in p._status_label.text()

    def test_manual_extents_without_run(self, qtbot):
        p = _panel(qtbot, client=_FakeTiledClient())
        p.set_manual_extents(-10.0, 10.0, -5.0, 5.0)
        assert p.current_extents() == (-10.0, 10.0, -5.0, 5.0)

    def test_descending_extents_normalized_for_display(self, qtbot):
        client = _FakeTiledClient()
        client["u1"] = _FakeEntry(np.ones((3, 5)), x_extent=(4.0, -4.0))
        p = _panel(qtbot, client=client)
        p.load_run("u1")  # spec §4.1: descending extents are legal
        # boundingRect() is local/pixel space in pyqtgraph; mapRectToView reflects the setRect placement in motor coords.
        r = p._image_item.mapRectToView(p._image_item.boundingRect())
        assert (r.left(), r.width()) == (-4.0, 8.0)


class TestRegionRoi:
    def test_region_kwargs_from_roi_state(self, qtbot):
        p = _panel(qtbot)
        p.set_manual_extents(-10.0, 10.0, -5.0, 5.0)
        p._roi.setPos((-3.0, -1.0))
        p._roi.setSize((2.0, 3.0))
        kw = p.region_kwargs()
        assert kw == {"x_start": -3.0, "x_stop": -1.0, "y_start": -1.0, "y_stop": 2.0}


class _FakeDeviceInfo:
    def __init__(self, name, min_v=-100.0, max_v=100.0, extra_kwargs: dict | None = None):
        self.name = name
        kwargs = {"axis_config": {"minValue": min_v, "maxValue": max_v}}
        if extra_kwargs:
            kwargs.update(extra_kwargs)
        self.metadata = {"kwargs": kwargs}


class _FakeCatalog:
    """Duck-type of DeviceCatalog for the pystxm sim device set."""
    def __init__(self):
        self._infos = {
            "SampleY": _FakeDeviceInfo("SampleY"),
            "energy": _FakeDeviceInfo("energy", 250.0, 2500.0),
            "STXMLineFlyer": _FakeDeviceInfo(
                "STXMLineFlyer",
                extra_kwargs={"x_axis_config": {"minValue": -100.0, "maxValue": 100.0}},
            ),
        }
        self._ophyd = {k: MagicMock(name=k) for k in self._infos}
        for k, m in self._ophyd.items():
            m.name = k
        # flyer needs the contract attrs the plan reads
        self._ophyd["STXMLineFlyer"].X_DATA_KEY = "SampleX"

    def get_device_by_name(self, name):
        return self._infos.get(name)

    def get_ophyd_device(self, name):
        return self._ophyd.get(name)


class TestValidationAndSubmit:
    def _ready_panel(self, qtbot, engine=None):
        p = _panel(qtbot, catalog=_FakeCatalog(), engine=engine or MagicMock())
        p.set_manual_extents(-10.0, 10.0, -5.0, 5.0)
        p._flyer_name = "STXMLineFlyer"
        p._energy_name = "energy"
        p._y_name = "SampleY"
        p._energy_editor.add_range(500.0, 510.0, 2)
        return p

    def test_valid_scan_has_no_errors(self, qtbot):
        p = self._ready_panel(qtbot)
        assert p.validate_scan() == []

    def test_empty_energies_rejected(self, qtbot):
        p = self._ready_panel(qtbot)
        p._energy_editor._table.setRowCount(0)
        assert any("energ" in e.lower() for e in p.validate_scan())

    def test_energy_outside_soft_limits_rejected(self, qtbot):
        p = self._ready_panel(qtbot)
        p._energy_editor.add_range(3000.0, 3000.0, 1)  # > maxValue 2500
        assert any("limit" in e.lower() for e in p.validate_scan())

    def test_region_outside_y_limits_rejected(self, qtbot):
        p = self._ready_panel(qtbot)
        p._roi.setPos((-3.0, -200.0))  # y below SampleY minValue -100
        p._roi.setSize((2.0, 3.0))
        assert any("limit" in e.lower() for e in p.validate_scan())

    def test_region_outside_x_limits_rejected(self, qtbot):
        p = self._ready_panel(qtbot)
        p._roi.setPos((-200.0, -1.0))  # x below flyer x_axis_config minValue -100
        p._roi.setSize((2.0, 3.0))
        assert any("limit" in e.lower() for e in p.validate_scan())

    def test_launch_submits_plan_with_name(self, qtbot):
        engine = MagicMock()
        engine.submit.return_value = "proc-1"
        p = self._ready_panel(qtbot, engine=engine)
        assert p.launch() == "proc-1"
        assert engine.submit.call_count == 1
        _, kwargs = engine.submit.call_args
        assert kwargs.get("name") == "stxm_energy_stack"

    def test_launch_blocked_when_invalid(self, qtbot):
        engine = MagicMock()
        p = self._ready_panel(qtbot, engine=engine)
        p._energy_editor._table.setRowCount(0)
        assert p.launch() is None
        engine.submit.assert_not_called()


class TestPanelPlugin:
    def test_plugin_identity_and_panel_class(self):
        from lightfall_pystxmcontrol.scan_panel import StxmScanPanelPlugin, STXMScanPanel
        p = StxmScanPanelPlugin()
        assert p.name == "stxm_scan"
        assert p.get_panel_class() is STXMScanPanel
        assert p.panel_id == "lightfall_pystxmcontrol.panels.stxm_scan"

    def test_manifest_has_preloaded_panel_entry(self):
        from lightfall_pystxmcontrol.manifest import manifest
        entry = next(e for e in manifest.plugins if e.type_name == "panel")
        assert entry.name == "stxm_scan"
        assert entry.preload is True
