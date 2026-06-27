"""Tests for StxmMapVisualization and StxmMapVizPlugin.

TDD Task 5 — Phase-2c pystxmcontrol→Lightfall.
"""
import numpy as np
import pytest


def _qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_array_data(row, line, offset_none=False):
    """Minimal stand-in matching the real LiveArrayData (tiled/client/stream.py).

    LiveArrayData inherits ArrayData which has:
      - type: Literal["array-data"]
      - offset: Optional[tuple[int, ...]]   — (row, col) for a patch, None for
                                              the first write of the full array
      - shape: tuple[int, ...]              — shape of this payload (e.g. (1, nx))
      - data(): decoded np.ndarray with shape == self.shape

    The spike recorded offset=(row, 0) for each row patch.
    data() returns shape (1, nx) for a single-row patch.
    """

    class _FakeLiveArrayData:
        type = "array-data"

        def __init__(self, row, line, offset_none):
            self.offset = None if offset_none else (row, 0)
            self._line = np.asarray(line)
            self.shape = (1, len(self._line))

        def data(self):
            return self._line.reshape(1, -1)

    return _FakeLiveArrayData(row, line, offset_none)


# ---------------------------------------------------------------------------
# StxmMapVisualization — unit tests
# ---------------------------------------------------------------------------


class TestStxmMapVisualization:
    def test_on_stream_update_blits_line_into_map(self):
        """Core test: a pushed array-data line lands at the right row."""
        _qapp()
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        viz = StxmMapVisualization()
        viz.begin_map(ny=4, nx=8)

        line = np.arange(8, dtype=float) + 1.0
        viz.on_stream_update(_make_array_data(row=2, line=line))

        img = viz.current_image()
        assert img is not None
        assert np.array_equal(img[2], line), f"Row 2 should be {line}, got {img[2]}"
        assert (img[0] == 0).all(), "Untouched row 0 should stay zero"
        assert (img[1] == 0).all(), "Untouched row 1 should stay zero"
        assert (img[3] == 0).all(), "Untouched row 3 should stay zero"

    def test_on_stream_update_idempotent(self):
        """Blitting the same row twice is idempotent (same data, same row)."""
        _qapp()
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        viz = StxmMapVisualization()
        viz.begin_map(ny=3, nx=5)
        line = np.ones(5, dtype=float) * 7.0
        update = _make_array_data(row=1, line=line)
        viz.on_stream_update(update)
        viz.on_stream_update(update)  # second apply must not corrupt
        img = viz.current_image()
        assert np.array_equal(img[1], line)

    def test_on_stream_update_row_bounds_guard(self):
        """Out-of-bounds row is silently dropped — no crash, image unchanged."""
        _qapp()
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        viz = StxmMapVisualization()
        viz.begin_map(ny=2, nx=4)
        line = np.ones(4, dtype=float)
        # Row 5 is out of bounds for ny=2
        viz.on_stream_update(_make_array_data(row=5, line=line))
        img = viz.current_image()
        assert (img == 0).all(), "Image must stay zero after out-of-bounds row"

    def test_on_stream_update_wrong_type_falls_back_to_refresh(self):
        """Non array-data update triggers refresh() (the default fallback)."""
        _qapp()
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        viz = StxmMapVisualization()
        viz.begin_map(ny=2, nx=4)

        refresh_called = []
        viz.refresh = lambda: refresh_called.append(1)

        class _OtherUpdate:
            type = "table-data"

        viz.on_stream_update(_OtherUpdate())
        assert refresh_called, "refresh() should be called for non array-data updates"

    def test_on_stream_update_none_offset_falls_back_to_refresh(self):
        """offset=None (initial full-array write) triggers refresh()."""
        _qapp()
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        viz = StxmMapVisualization()
        viz.begin_map(ny=2, nx=4)

        refresh_called = []
        viz.refresh = lambda: refresh_called.append(1)

        line = np.ones(4, dtype=float)
        viz.on_stream_update(_make_array_data(row=0, line=line, offset_none=True))
        assert refresh_called, "refresh() should be called when offset is None"

    def test_begin_map_allocates_zero_image(self):
        """begin_map allocates a zero-filled (ny, nx) array."""
        _qapp()
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        viz = StxmMapVisualization()
        viz.begin_map(ny=3, nx=6)
        img = viz.current_image()
        assert img is not None
        assert img.shape == (3, 6)
        assert (img == 0).all()

    def test_current_image_none_before_begin_map(self):
        """current_image() returns None before begin_map is called."""
        _qapp()
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        viz = StxmMapVisualization()
        assert viz.current_image() is None

    def test_can_handle_high_score_on_start_plan_name(self):
        """can_handle scores high on start-doc plan_name == stxm_fly_raster.

        This is the real top-level signal: the panel passes the BlueskyRun
        entry whose metadata["start"]["plan_name"] identifies the plan.
        """
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        class _FakeRun:
            metadata = {"start": {"plan_name": "stxm_fly_raster"}}

        assert StxmMapVisualization.can_handle(_FakeRun()) >= 95

    def test_can_handle_high_score_on_primary_probe(self):
        """can_handle falls back to probing run['primary'] for the flyer key."""
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        class _Primary:
            def __contains__(self, key):
                return key == "STXMLineFlyer"

        class _FakeRun:
            # No useful start metadata -> exercise the primary-probe fallback.
            metadata = {"start": {"plan_name": "some_other_plan"}}

            def __getitem__(self, key):
                if key == "primary":
                    return _Primary()
                raise KeyError(key)

        assert StxmMapVisualization.can_handle(_FakeRun()) >= 95

    def test_can_handle_returns_zero_for_other_run(self):
        """can_handle returns 0 for a non-STXM run (wrong plan, no flyer)."""
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        class _Primary:
            def __contains__(self, key):
                return False

        class _FakeRun:
            metadata = {"start": {"plan_name": "grid_scan"}}

            def __getitem__(self, key):
                if key == "primary":
                    return _Primary()
                raise KeyError(key)

        assert StxmMapVisualization.can_handle(_FakeRun()) == 0

    def test_can_handle_returns_zero_on_exception(self):
        """can_handle is robust: returns 0 if the run raises on access."""
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        class _BrokenRun:
            @property
            def metadata(self):
                raise RuntimeError("no catalog")

            def __getitem__(self, key):
                raise RuntimeError("no catalog")

        assert StxmMapVisualization.can_handle(_BrokenRun()) == 0

    def test_can_handle_returns_zero_on_missing_metadata(self):
        """can_handle returns 0 when run has no metadata and no primary."""
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        class _BareRun:
            # No metadata attribute; __getitem__ raises (no primary stream yet).
            def __getitem__(self, key):
                raise KeyError(key)

        assert StxmMapVisualization.can_handle(_BareRun()) == 0

    def test_viz_name(self):
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        assert StxmMapVisualization.viz_name == "stxm_map"


# ---------------------------------------------------------------------------
# StxmMapVisualization — auto-LUT (auto levels) tests
# ---------------------------------------------------------------------------


class TestStxmMapAutoLut:
    def test_auto_levels_default_tracks_data_range(self):
        """By default, levels auto-scale to the image's finite min/max."""
        _qapp()
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        viz = StxmMapVisualization()
        viz.begin_map(ny=4, nx=8)
        line = np.arange(8, dtype=float) + 1.0  # 1..8
        viz.on_stream_update(_make_array_data(row=2, line=line))

        # Whole-array finite range: unfilled rows are 0 -> min 0, max 8.
        lo, hi = viz._image_view.getLevels()
        assert lo == pytest.approx(0.0)
        assert hi == pytest.approx(8.0)
        assert viz._auto_levels is True, "auto must stay on after an auto render"

    def test_auto_levels_follow_growing_max(self):
        """Each blit re-scales levels while auto is on."""
        _qapp()
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        viz = StxmMapVisualization()
        viz.begin_map(ny=3, nx=4)

        viz.on_stream_update(_make_array_data(row=0, line=np.full(4, 8.0)))
        _, hi = viz._image_view.getLevels()
        assert hi == pytest.approx(8.0)

        viz.on_stream_update(_make_array_data(row=1, line=np.full(4, 50.0)))
        _, hi = viz._image_view.getLevels()
        assert hi == pytest.approx(50.0)

    def test_manual_level_change_disables_auto(self):
        """A manual histogram adjustment freezes levels; later blits don't rescale."""
        _qapp()
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        viz = StxmMapVisualization()
        viz.begin_map(ny=3, nx=4)
        viz.on_stream_update(_make_array_data(row=0, line=np.full(4, 8.0)))

        # Simulate the user dragging the histogram region (happens outside
        # _render, so the auto-apply guard is not active).
        viz._image_view.getHistogramWidget().setLevels(2.0, 5.0)
        assert viz._auto_levels is False, "manual adjustment must disable auto"

        # A subsequent line with a much larger value must NOT rescale.
        viz.on_stream_update(_make_array_data(row=1, line=np.full(4, 999.0)))
        lo, hi = viz._image_view.getLevels()
        assert lo == pytest.approx(2.0)
        assert hi == pytest.approx(5.0)

    def test_live_update_uses_image_item_not_imageview_setimage(self):
        """Live blits go through ImageItem.updateImage, not ImageView.setImage."""
        _qapp()
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

        viz = StxmMapVisualization()
        viz.begin_map(ny=3, nx=4)  # builds the view

        iv_setimage_calls = []
        item_update_calls = []
        viz._image_view.setImage = lambda *a, **k: iv_setimage_calls.append((a, k))
        item = viz._image_view.getImageItem()
        orig_update = item.updateImage
        item.updateImage = lambda *a, **k: (item_update_calls.append((a, k)), orig_update(*a, **k))[1]

        viz.on_stream_update(_make_array_data(row=1, line=np.full(4, 3.0)))

        assert item_update_calls, "live update must call ImageItem.updateImage"
        assert not iv_setimage_calls, "live update must NOT call ImageView.setImage"


# ---------------------------------------------------------------------------
# StxmMapVizPlugin — unit tests
# ---------------------------------------------------------------------------


class TestStxmMapVizPlugin:
    def test_plugin_name(self):
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVizPlugin

        plugin = StxmMapVizPlugin()
        assert plugin.name == "stxm_map"

    def test_plugin_get_viz_class(self):
        from lightfall_pystxmcontrol.stxm_map_viz import (
            StxmMapVisualization,
            StxmMapVizPlugin,
        )

        plugin = StxmMapVizPlugin()
        assert plugin.get_viz_class() is StxmMapVisualization

    def test_plugin_type_name(self):
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVizPlugin

        assert StxmMapVizPlugin.type_name == "visualization"
