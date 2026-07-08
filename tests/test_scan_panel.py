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
