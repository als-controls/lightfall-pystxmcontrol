"""Live 3-D STXM energy-stack visualization (spec §3.4).

Consumes the contract (§4): allocates an (nE, ny, nx) cube from the start-doc
``stxm`` block (NEW machinery — the 2-D map has no production allocation
path), blits per-line array-data pushes at (iE, iy) = divmod(offset_row, ny),
and falls back to a full Tiled re-read (refresh) otherwise. The Tiled node is
a growing (k, nx) 2-D array; the cube view of it is contract.cube_from_rows.

Displays one energy frame at a time. Live-follow: the displayed frame tracks
the energy being acquired; user slider interaction suspends follow until the
Follow toggle re-enables it (the slider + Follow widgets live in this viz).
"""
from __future__ import annotations

from typing import Any

import numpy as np
from lightfall.plugins.types import PluginType
from lightfall.visualization.base_visualization import BaseVisualization

from . import contract
from .image_render import ImageRenderMixin


class StxmStackVisualization(ImageRenderMixin, BaseVisualization):
    viz_name = "stxm_stack"
    viz_display_name = "STXM Energy Stack"
    viz_icon = "layers-triple"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._init_render_state()
        self._cube: np.ndarray | None = None
        self._stxm: dict | None = None
        self._frame: int = 0
        self._follow_live: bool = True
        self._latest_frame: int = 0

    # ---------------- cube state ----------------

    def current_cube(self) -> np.ndarray | None:
        return self._cube

    def current_frame_index(self) -> int:
        return self._frame

    @property
    def follow_live(self) -> bool:
        return self._follow_live

    def set_frame_index(self, i: int) -> None:
        """Programmatic frame selection (the frame slider calls this)."""
        if self._cube is None:
            return
        self._frame = int(np.clip(i, 0, self._cube.shape[0] - 1))
        self._show_frame()

    def _show_frame(self) -> None:
        self._ensure_controls()
        if self._cube is None:
            return
        self._image = self._cube[self._frame]
        self._render()
        self._sync_controls()

    # ---------------- controls ----------------

    def _ensure_controls(self) -> None:
        """Lazily build slider + follow checkbox below the image view."""
        if getattr(self, "_slider", None) is not None:
            return
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QSlider

        self._ensure_view()  # ImageRenderMixin: builds the ImageView + layout
        self._slider = QSlider(Qt.Horizontal, self)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        self._follow_box = QCheckBox("Follow", self)
        self._follow_box.setChecked(self._follow_live)
        self._follow_box.toggled.connect(self._on_follow_toggled)
        self._energy_label = QLabel("", self)
        row = QHBoxLayout()
        row.addWidget(self._slider, 1)
        row.addWidget(self._energy_label, 0)
        row.addWidget(self._follow_box, 0)
        self.layout().addLayout(row)
        self._sync_controls()

    def _on_slider_moved(self, value: int) -> None:
        """USER slider interaction suspends live-follow (spec §3.4)."""
        self._follow_live = False
        if getattr(self, "_follow_box", None) is not None:
            self._follow_box.setChecked(False)
        self.set_frame_index(value)

    def _on_follow_toggled(self, checked: bool) -> None:
        self._follow_live = bool(checked)
        if checked:
            self.set_frame_index(self._latest_frame)

    def _sync_controls(self) -> None:
        if getattr(self, "_slider", None) is None or self._cube is None:
            return
        self._slider.setMaximum(self._cube.shape[0] - 1)
        self._slider.blockSignals(True)
        self._slider.setValue(self._frame)
        self._slider.blockSignals(False)
        if self._stxm:
            e = self._stxm["energies"][self._frame]
            self._energy_label.setText(f"{e:g} eV [{self._frame + 1}/{self._cube.shape[0]}]")

    # ---------------- streaming ----------------

    def on_stream_update(self, update: Any) -> None:
        if getattr(update, "type", None) != "array-data":
            self.refresh()
            return
        offset = getattr(update, "offset", None)
        if offset is None or self._cube is None or self._stxm is None:
            self.refresh()
            return
        nE, ny, nx = self._stxm["shape"]
        row = offset[0]
        if not (0 <= row < nE * ny):
            return
        line = np.asarray(update.data()).reshape(-1)
        if line.size != nx:
            return
        iE, iy = contract.decode_line_index(row, ny)
        self._cube[iE, iy] = line
        self._latest_frame = iE
        if self._follow_live:
            self._frame = iE
        if iE == self._frame:
            self._show_frame()

    # ---------------- BaseVisualization ----------------

    @staticmethod
    def can_handle(run: Any) -> int:
        """96: must outscore the 2-D map viz (95), whose primary-probe fallback
        also matches stack runs (they contain the same flyer key)."""
        try:
            start = (getattr(run, "metadata", None) or {}).get("start", {}) or {}
            if start.get("plan_name") == contract.PLAN_NAME_ENERGY_STACK:
                return 96
            return 0
        except Exception:
            return 0

    def set_run(self, run: Any) -> None:
        self._run = run
        try:
            self._stxm = run.metadata["start"]["stxm"]
        except Exception:
            self._stxm = None
        self._cube = None
        self._frame = 0

    def get_streams(self) -> list[str]:
        return ["primary"]

    def set_stream(self, stream_name: str) -> None:
        self._stream_name = stream_name
        self.refresh()

    def get_fields(self) -> list[str]:
        return [self._stxm["data_field"]] if self._stxm else []

    def set_field(self, field_name: str) -> None:
        self._field_name = field_name

    def refresh(self) -> None:
        """Re-read the (k, nx) rows node and rebuild the NaN-filled cube."""
        if self._stxm is None:
            return
        rows = np.empty((0, self._stxm["shape"][2]))
        node = self._rows_node()
        if node is not None:
            try:
                arr = np.asarray(node.read())
                if arr.ndim == 2:
                    rows = arr
            except Exception:
                pass
        self._cube = contract.cube_from_rows(rows, self._stxm["shape"])
        self._show_frame()

    def _rows_node(self):
        if self._run is None or self._stxm is None:
            return None
        try:
            return self._run["primary"][self._stxm["data_field"]]
        except Exception:
            return None


class StxmStackVizPlugin(PluginType):
    """Registers StxmStackVisualization with the VisualizationRegistry."""

    type_name = "visualization"

    @property
    def name(self) -> str:
        return "stxm_stack"

    def get_viz_class(self) -> type[StxmStackVisualization]:
        return StxmStackVisualization

    def get_introspection_data(self) -> dict:
        data = super().get_introspection_data()
        data["viz_name"] = StxmStackVisualization.viz_name
        data["viz_display_name"] = StxmStackVisualization.viz_display_name
        return data
