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

from lightfall.plugins.panel_plugin import PanelPlugin
from lightfall.ui.panels.base import BasePanel, PanelMetadata

from .energy_ranges import EnergyRangesEditor

import logging

logger = logging.getLogger(__name__)


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
        last_btn = QPushButton("Load last run", self)
        last_btn.clicked.connect(self.load_last_run)
        self._status_label = QLabel("", self)
        top = QHBoxLayout()
        top.addWidget(self._uid_edit, 1)
        top.addWidget(load_btn, 0)
        top.addWidget(last_btn, 0)

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
        self._setup_submit_ui()  # builds device pickers, error label, Launch button

    def _setup_submit_ui(self) -> None:
        from PySide6.QtWidgets import QComboBox

        # Device pickers (Phase A: flyer selection IS the channel selection,
        # spec §3.3; its name lands in the contract as data_field).
        self._flyer_name = "STXMLineFlyer"
        self._energy_name = "energy"
        self._y_name = "SampleY"

        dev_row = QHBoxLayout()
        self._device_combos: dict[str, Any] = {}
        for label, attr, names in (
            ("Detector:", "_flyer_name", ["STXMLineFlyer"]),
            ("Energy:", "_energy_name", ["energy"]),
            ("Y axis:", "_y_name", ["SampleY", "SampleX"]),
        ):
            dev_row.addWidget(QLabel(label, self))
            combo = QComboBox(self)
            combo.addItems(names)
            combo.currentTextChanged.connect(
                lambda text, a=attr: setattr(self, a, text))
            self._device_combos[attr] = combo
            dev_row.addWidget(combo)

        self._errors_label = QLabel("", self)
        self._errors_label.setWordWrap(True)
        self._launch_btn = QPushButton("Launch energy stack", self)
        self._launch_btn.clicked.connect(self.launch)

        self._layout.addLayout(dev_row)
        self._layout.addWidget(self._errors_label)
        self._layout.addWidget(self._launch_btn)

    # ---------------- validation + submit ----------------

    def _axis_limits(self, device_name: str) -> tuple[float, float] | None:
        """Soft limits for an axis.

        Post-EPICS-migration the axes are stock ``ophyd.EpicsMotor``, which
        exposes soft limits directly (``.limits`` == (LLM, HLM)); read them
        from the live device when it is connected. Legacy sim happi entries
        embedded the limits in the entry kwargs (``axis_config``), so fall
        back to that for old DBs; None if neither source is available.
        """
        catalog = self._catalog()
        try:
            lo, hi = catalog.get_ophyd_device(device_name).limits
            lo, hi = float(lo), float(hi)
            if lo < hi:  # EpicsMotor convention: (0, 0) == limits disabled
                return lo, hi
        except Exception:
            pass
        info = catalog.get_device_by_name(device_name)
        try:
            cfg = info.metadata["kwargs"]["axis_config"]
            return float(cfg["minValue"]), float(cfg["maxValue"])
        except Exception:
            logger.debug(
                "no soft limits available for axis %r (neither live device "
                "nor legacy axis_config); skipping validation for this axis",
                device_name)
            return None

    def _x_axis_limits(self) -> tuple[float, float] | None:
        """Soft limits for the flyer's fast (X) axis.

        The fast axis is a real motor now: resolve its device name from the
        live flyer's ``X_DATA_KEY`` and reuse :meth:`_axis_limits`. Legacy sim
        DBs embedded an ``x_axis_config`` dict in the flyer's happi kwargs.
        """
        catalog = self._catalog()
        try:
            x_name = str(catalog.get_ophyd_device(self._flyer_name).X_DATA_KEY)
        except Exception:
            x_name = None
        if x_name:
            lim = self._axis_limits(x_name)
            if lim:
                return lim
        info = catalog.get_device_by_name(self._flyer_name)
        try:
            cfg = info.metadata["kwargs"]["x_axis_config"]
            return float(cfg["minValue"]), float(cfg["maxValue"])
        except Exception:
            return None

    def validate_scan(self) -> list[str]:
        errors: list[str] = []
        try:
            energies = self._energy_editor.energies()
        except ValueError as e:
            return [str(e)]
        if not energies:
            errors.append("no energies defined")
        region = self.region_kwargs()
        if self._nx.value() < 1 or self._ny.value() < 1:
            errors.append("nx and ny must be >= 1")
        lim = self._axis_limits(self._energy_name)
        if lim and energies:
            lo, hi = lim
            bad = [e for e in energies if not (lo <= e <= hi)]
            if bad:
                errors.append(f"energies outside soft limits [{lo}, {hi}]: {bad[:3]}")
        lim = self._axis_limits(self._y_name)
        if lim:
            lo, hi = lim
            if not (lo <= region["y_start"] and region["y_stop"] <= hi):
                errors.append(f"region Y outside soft limits [{lo}, {hi}]")
        lim = self._x_axis_limits()
        if lim:
            lo, hi = lim
            if not (lo <= region["x_start"] and region["x_stop"] <= hi):
                errors.append(f"region X outside soft limits [{lo}, {hi}]")
        return errors

    def launch(self) -> str | None:
        """Validate, build the plan generator, submit. Returns procedure id."""
        errors = self.validate_scan()
        self._errors_label.setText("; ".join(errors))
        if errors:
            return None
        catalog = self._catalog()
        flyer = catalog.get_ophyd_device(self._flyer_name)
        energy = catalog.get_ophyd_device(self._energy_name)
        y = catalog.get_ophyd_device(self._y_name)
        if not all((flyer, energy, y)):
            self._errors_label.setText("devices not connected")
            return None
        from .plans import stxm_energy_stack
        plan = stxm_energy_stack(
            flyer, energy, y,
            energies=self._energy_editor.energies(),
            ny=self._ny.value(), nx=self._nx.value(),
            dwell_ms=self._dwell.value(),
            **self.region_kwargs(),
        )
        pid = self._engine().submit(plan, name="stxm_energy_stack")
        self._status_label.setText(f"submitted: {pid}")
        return pid

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

    def _latest_run_uid(self, client: Any) -> str | None:
        """uid of the most-recent run via a single bounded request.

        Delegates to lightfall.plugins.agents.engine_tools._recent_runs so the
        newest-run selection (backend-portable sort-key detection, no catalog
        walk) lives in exactly one place. An earlier copy here sorted on a bare
        ``time`` key, which silently no-ops on modern Tiled and made "Load last
        run" pick the oldest run.
        """
        try:
            from lightfall.plugins.agents.engine_tools import _recent_runs
            runs = _recent_runs(client, 1)
        except Exception:
            return None
        if not runs:
            return None
        try:
            return runs[0].metadata["start"]["uid"]
        except Exception:
            return None

    def load_last_run(self) -> None:
        """Load the most-recent run in the Tiled catalog as the context image.

        Convenience over ``load_run``: finds the newest run's uid (bounded
        request, no catalog walk) and delegates to ``load_run`` so there is a
        single rendering path. Never raises; failures land in the status label.
        """
        client = self._tiled_client()
        if client is None:
            self._status_label.setText("Tiled not connected")
            return
        uid = self._latest_run_uid(client)
        if uid is None:
            self._status_label.setText("no runs found")
            return
        self.load_run(uid)

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


class StxmScanPanelPlugin(PanelPlugin):
    """Contributes the STXM scan-definition panel."""

    @property
    def name(self) -> str:
        return "stxm_scan"

    def get_panel_class(self) -> type[BasePanel]:
        return STXMScanPanel
