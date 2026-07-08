# src/lightfall_pystxmcontrol/scan_panel.py
"""STXM scan-definition panel (spec §3.3).

Absorbs the FUNCTION of pystxmcontrol's scanDef/regionDef/energyDef GUI on
Lightfall idioms: draw a region on a prior image (loaded THROUGH TILED, in
motor coordinates), define energy ranges, pick devices, submit the
stxm_energy_stack plan via get_engine().submit(). No pystxmcontrol imports.

Injectable deps (catalog=, engine=, tiled_client=) follow the XPCS panel's
testability pattern; None means "resolve the Lightfall singleton lazily".
"""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import (
    QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QWidget,
)

from lightfall.ui.panels.base import BasePanel, PanelMetadata

from .energy_ranges import EnergyRangesEditor


def region_to_plan_kwargs(pos: tuple[float, float], size: tuple[float, float]) -> dict:
    """Map a RectROI (pos, size) in motor coords to plan geometry kwargs.

    pyqtgraph RectROI pos is the rect origin (min-x, min-y) and size is
    positive, so start < stop always; scan direction is the plan's business.
    """
    x0, y0 = float(pos[0]), float(pos[1])
    w, h = float(size[0]), float(size[1])
    return {"x_start": x0, "x_stop": x0 + w, "y_start": y0, "y_stop": y0 + h}


class STXMScanPanel(BasePanel):
    panel_metadata: ClassVar[PanelMetadata] = PanelMetadata(
        id="lightfall_pystxmcontrol.panels.stxm_scan",
        name="STXM Scan",
        description="Define and launch STXM energy-stack scans.",
        icon="microscope",
        category="Acquisition",
        default_area="left",
        proactive_init=False,
    )

    def __init__(self, parent: QWidget | None = None, *,
                 catalog: Any = None, engine: Any = None,
                 tiled_client: Any = None) -> None:
        # Injectables BEFORE super().__init__ — BasePanel calls _setup_ui() there.
        self._catalog_override = catalog
        self._engine_override = engine
        self._tiled_client_override = tiled_client
        self._extents: tuple[float, float, float, float] | None = None
        super().__init__(parent)

    # ---------------- dependency resolution ----------------

    def _catalog(self) -> Any:
        if self._catalog_override is not None:
            return self._catalog_override
        from lightfall.devices import DeviceCatalog
        return DeviceCatalog.get_instance()

    def _engine(self) -> Any:
        if self._engine_override is not None:
            return self._engine_override
        from lightfall.acquire.engine import get_engine
        return get_engine()

    def _tiled_client(self) -> Any:
        if self._tiled_client_override is not None:
            return self._tiled_client_override
        from lightfall.services.tiled_service import TiledService
        svc = TiledService.get_instance()
        return svc.client if svc.is_connected else None

    # ---------------- UI ----------------

    def _setup_ui(self) -> None:
        import pyqtgraph as pg

        # Context image row: uid + load, manual extents
        self._uid_edit = QLineEdit(self)
        self._uid_edit.setPlaceholderText("prior run uid")
        load_btn = QPushButton("Load run", self)
        load_btn.clicked.connect(lambda: self.load_run(self._uid_edit.text().strip()))
        self._status_label = QLabel("", self)
        top = QHBoxLayout()
        top.addWidget(self._uid_edit, 1)
        top.addWidget(load_btn, 0)

        # Manual extents (used when no prior run is loaded)
        self._ext_boxes = []
        ext_row = QHBoxLayout()
        ext_row.addWidget(QLabel("Extents x0,x1,y0,y1:", self))
        for default in (-10.0, 10.0, -10.0, 10.0):
            b = QDoubleSpinBox(self)
            b.setRange(-1e6, 1e6)
            b.setValue(default)
            self._ext_boxes.append(b)
            ext_row.addWidget(b)
        apply_ext = QPushButton("Apply", self)
        apply_ext.clicked.connect(
            lambda: self.set_manual_extents(*(b.value() for b in self._ext_boxes)))
        ext_row.addWidget(apply_ext)

        # Image + region ROI (motor coordinates via ImageItem.setRect)
        self._plot = pg.PlotWidget(self)
        self._plot.setAspectLocked(False)
        self._image_item = pg.ImageItem()
        self._image_item.setOpts(axisOrder="row-major")  # data[iy, ix], iy vertical
        self._plot.addItem(self._image_item)
        self._roi = pg.RectROI(pos=(-5.0, -5.0), size=(10.0, 10.0), pen="y")
        self._plot.addItem(self._roi)

        # Pixels
        pix_row = QHBoxLayout()
        pix_row.addWidget(QLabel("nx:", self))
        self._nx = QSpinBox(self); self._nx.setRange(1, 10000); self._nx.setValue(10)
        pix_row.addWidget(self._nx)
        pix_row.addWidget(QLabel("ny:", self))
        self._ny = QSpinBox(self); self._ny.setRange(1, 10000); self._ny.setValue(6)
        pix_row.addWidget(self._ny)
        pix_row.addWidget(QLabel("dwell (ms):", self))
        self._dwell = QDoubleSpinBox(self); self._dwell.setRange(0.01, 60000.0); self._dwell.setValue(1.0)
        pix_row.addWidget(self._dwell)

        # Energy ranges
        self._energy_editor = EnergyRangesEditor(self)

        self._layout.addLayout(top)
        self._layout.addWidget(self._status_label)
        self._layout.addLayout(ext_row)
        self._layout.addWidget(self._plot)
        self._layout.addLayout(pix_row)
        self._layout.addWidget(self._energy_editor)
        self._setup_submit_ui()  # Task 13 (no-op placeholder until then)

    def _setup_submit_ui(self) -> None:
        """Extended in Task 13 with device pickers, validation, and Launch."""

    # ---------------- context image ----------------

    def load_run(self, uid: str) -> None:
        """Load a prior run's map through Tiled and place it in motor coords.

        Follows core VisualizationPanel._resolve_entry: disconnected -> None,
        KeyError -> not found. Never raises; failures land in the status label.
        """
        client = self._tiled_client()
        if client is None:
            self._status_label.setText("Tiled not connected")
            return
        try:
            entry = client[uid]
        except KeyError:
            self._status_label.setText(f"run {uid!r} not found")
            return
        except Exception as e:
            self._status_label.setText(f"load failed: {e}")
            return
        try:
            start = entry.metadata["start"]
            field = (start.get("stxm") or {}).get("data_field") \
                or (start.get("detectors") or [None])[0]
            arr = np.asarray(entry["primary"][field].read(), dtype=float)
            x_extent = start.get("x_extent") or (start.get("stxm") or {}).get("x_extent")
            y_extent = start.get("y_extent") or (start.get("stxm") or {}).get("y_extent")
        except Exception as e:
            self._status_label.setText(f"unreadable run: {e}")
            return
        if arr.ndim == 3:  # stack cube rows already reshaped upstream — take frame 0
            arr = arr[0]
        if arr.ndim != 2 or x_extent is None or y_extent is None:
            self._status_label.setText("run has no 2-D map with extents")
            return
        self._show_image(arr, tuple(x_extent), tuple(y_extent))
        self._status_label.setText(f"loaded {uid[:8]}… shape={arr.shape}")

    def set_manual_extents(self, x0: float, x1: float, y0: float, y1: float) -> None:
        self._show_image(None, (x0, x1), (y0, y1))

    def _show_image(self, arr: np.ndarray | None,
                    x_extent: tuple[float, float], y_extent: tuple[float, float]) -> None:
        self._extents = (float(x_extent[0]), float(x_extent[1]),
                         float(y_extent[0]), float(y_extent[1]))
        # Normalize for display; descending extents are legal (spec §4.1).
        x_lo, x_hi = sorted((self._extents[0], self._extents[1]))
        y_lo, y_hi = sorted((self._extents[2], self._extents[3]))
        if arr is not None:
            self._image_item.setImage(arr)
            self._image_item.setRect(QRectF(x_lo, y_lo, x_hi - x_lo, y_hi - y_lo))
        self._roi.setPos((x_lo + (x_hi - x_lo) * 0.25, y_lo + (y_hi - y_lo) * 0.25))
        self._roi.setSize(((x_hi - x_lo) * 0.5, (y_hi - y_lo) * 0.5))
        self._plot.setRange(xRange=(x_lo, x_hi), yRange=(y_lo, y_hi))

    def current_extents(self) -> tuple[float, float, float, float] | None:
        return self._extents

    def region_kwargs(self) -> dict:
        pos = self._roi.pos()
        size = self._roi.size()
        return region_to_plan_kwargs((pos.x(), pos.y()), (size.x(), size.y()))
