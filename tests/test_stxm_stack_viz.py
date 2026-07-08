"""Tasks 9-10: StxmStackVisualization — allocation, blit, refresh, NaN, slider."""
import warnings

import numpy as np


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


STXM_BLOCK = {
    "contract_version": 1, "shape": [2, 3, 4],
    "energies": [500.0, 510.0], "dwell_ms": 1.0,
    "x_extent": [-4.0, 4.0], "y_extent": [-2.0, 2.0],
    "x_motor": "SampleX", "y_motor": "SampleY", "energy_motor": "energy",
    "data_field": "STXMLineFlyer",
}


class _FakeNode:
    def __init__(self, rows):
        self._rows = np.asarray(rows, dtype=float)

    def read(self):
        return self._rows


class _FakeRun:
    def __init__(self, rows=None, stxm=STXM_BLOCK, plan_name="stxm_energy_stack"):
        self.metadata = {"start": {"plan_name": plan_name, **({"stxm": stxm} if stxm else {})}}
        self._rows = rows

    def __getitem__(self, key):
        if key == "primary" and self._rows is not None:
            return {STXM_BLOCK["data_field"]: _FakeNode(self._rows)}
        raise KeyError(key)


def _make_array_data(row, line, offset_none=False):
    class _Fake:
        type = "array-data"

        def __init__(self):
            self.offset = None if offset_none else (row, 0)
            self.shape = (1, len(line))

        def data(self):
            return np.asarray(line).reshape(1, -1)
    return _Fake()


def _viz(run=None):
    from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization
    _qapp()
    v = StxmStackVisualization()
    if run is not None:
        v.set_run(run)
        v.set_stream("primary")
    return v


class TestCanHandle:
    def test_scores_96_on_plan_name(self):
        from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization
        assert StxmStackVisualization.can_handle(_FakeRun()) == 96

    def test_outscores_map_viz_on_stack_runs(self):
        from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization
        from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization
        run = _FakeRun(rows=np.ones((1, 4)))
        assert StxmStackVisualization.can_handle(run) > StxmMapVisualization.can_handle(run)

    def test_zero_on_other_plan(self):
        from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization
        assert StxmStackVisualization.can_handle(_FakeRun(plan_name="grid_scan", stxm=None)) == 0

    def test_zero_on_broken_run(self):
        from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization

        class _Broken:
            @property
            def metadata(self):
                raise RuntimeError("no catalog")
        assert StxmStackVisualization.can_handle(_Broken()) == 0


class TestAllocationAndBlit:
    def test_allocates_from_start_doc(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        cube = v.current_cube()
        assert cube is not None and cube.shape == (2, 3, 4)
        assert np.isnan(cube).all()

    def test_blit_decodes_iE_iy_from_offset(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        line = np.arange(4, dtype=float) + 1.0
        v.on_stream_update(_make_array_data(row=4, line=line))  # (iE, iy) = divmod(4, 3) = (1, 1)
        cube = v.current_cube()
        assert np.array_equal(cube[1, 1], line)
        assert np.isnan(cube[0, 0]).all()

    def test_follow_live_tracks_current_energy(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        assert v.follow_live is True
        v.on_stream_update(_make_array_data(row=4, line=np.ones(4)))
        assert v.current_frame_index() == 1  # follows iE of the last blit

    def test_out_of_bounds_row_dropped(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        v.on_stream_update(_make_array_data(row=99, line=np.ones(4)))
        assert np.isnan(v.current_cube()).all()

    def test_offset_none_falls_back_to_refresh(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        calls = []
        v.refresh = lambda: calls.append(1)
        v.on_stream_update(_make_array_data(row=0, line=np.ones(4), offset_none=True))
        assert calls

    def test_all_nan_frame_renders_without_warnings(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            _viz(_FakeRun(rows=np.empty((0, 4))))


class TestRefresh:
    def test_refresh_reads_rows_and_nan_fills(self):
        rows = np.ones((4, 4))  # 4 of 6 lines
        v = _viz(_FakeRun(rows=rows))
        cube = v.current_cube()
        assert not np.isnan(cube[0]).any()
        assert np.isnan(cube[1, 1]).all() and np.isnan(cube[1, 2]).all()

    def test_get_fields_from_start_doc(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        assert v.get_fields() == ["STXMLineFlyer"]

    def test_no_stxm_block_is_safe(self):
        v = _viz()
        v.set_run(_FakeRun(plan_name="stxm_energy_stack", stxm=None))
        v.set_stream("primary")  # must not raise
        assert v.current_cube() is None


class TestSliderAndFollow:
    def test_slider_updates_frame_and_suspends_follow(self):
        v = _viz(_FakeRun(rows=np.ones((6, 4))))
        v._ensure_controls()
        v._slider.setValue(1)
        v._on_slider_moved(1)  # simulate user drag (sliderMoved is user-only)
        assert v.current_frame_index() == 1
        assert v.follow_live is False

    def test_follow_checkbox_reenables_and_jumps_to_latest(self):
        v = _viz(_FakeRun(rows=np.empty((0, 4))))
        v._ensure_controls()
        v._on_slider_moved(0)
        assert v.follow_live is False
        v.on_stream_update(_make_array_data(row=4, line=np.ones(4)))  # iE=1 acquired
        assert v.current_frame_index() == 0  # follow suspended — stays put
        v._follow_box.setChecked(True)
        assert v.follow_live is True
        assert v.current_frame_index() == 1  # jumped to latest acquired energy

    def test_slider_range_matches_nE(self):
        v = _viz(_FakeRun(rows=np.ones((6, 4))))
        v._ensure_controls()
        assert (v._slider.minimum(), v._slider.maximum()) == (0, 1)


class TestStackVizPlugin:
    def test_plugin_identity(self):
        from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVizPlugin
        p = StxmStackVizPlugin()
        assert p.name == "stxm_stack"
        assert StxmStackVizPlugin.type_name == "visualization"

    def test_manifest_has_entry(self):
        from lightfall_pystxmcontrol.manifest import manifest
        entries = {(e.type_name, e.name) for e in manifest.plugins}
        assert ("visualization", "stxm_stack") in entries
