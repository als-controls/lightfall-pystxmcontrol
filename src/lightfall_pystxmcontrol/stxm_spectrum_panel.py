"""Live I(E) spectrum panel fed by the external stxm-live service (XPCS panel shape)."""
from __future__ import annotations

from typing import ClassVar

import numpy as np
import pyqtgraph as pg
from loguru import logger
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget

from lightfall.plugins.panel_plugin import PanelPlugin
from lightfall.ui.panels.base import BasePanel, PanelMetadata

from lightfall_pystxmcontrol.stxm_analysis_client import StxmAnalysisClient
from lightfall_pystxmcontrol.stxm_binder import StxmRunBinder


class StxmSpectrumPanel(BasePanel):
    panel_metadata: ClassVar[PanelMetadata] = PanelMetadata(
        id="lightfall_pystxmcontrol.panels.stxm_spectrum",
        name="STXM Spectrum",
        description="Live I(E) spectrum from the external stxm-live analysis service",
        icon="mdi6.chart-bell-curve",
        category="Analysis",
        singleton=True,
        closable=True,
        keywords=["stxm", "spectrum", "analysis", "live"],
        default_area="bottom",
        sidebar_group="top",
    )

    def __init__(self, parent: QWidget | None = None,
                 client: StxmAnalysisClient | None = None,
                 binder: StxmRunBinder | None = None) -> None:
        # attrs before super().__init__: BasePanel.__init__ calls _setup_ui()
        self._client = client or StxmAnalysisClient()
        self._binder = binder or StxmRunBinder(client=self._client)
        super().__init__(parent)
        self._client.spectrumUpdated.connect(self._on_spectrum)
        self._client.statusChanged.connect(self._on_status)
        self._client.errorReceived.connect(self._on_error)
        self._client.reductionComplete.connect(self._on_complete)

    def _setup_ui(self) -> None:
        self._enable_toggle = self.add_title_bar_button(
            "mdi6.play-pause", "Enable analysis", checkable=True)
        self._enable_toggle.toggled.connect(self._on_enable_toggled)
        content = QWidget(self)
        layout = QVBoxLayout(content)
        self._plot = pg.PlotWidget()
        self._plot.setLabel("bottom", "Energy", units="eV")
        self._plot.setLabel("left", "I(E)")
        self._curve = self._plot.plot([], [], pen=pg.mkPen(width=2),
                                      symbol="o", symbolSize=5)
        self._status_label = QLabel("idle")
        layout.addWidget(self._plot)
        layout.addWidget(self._status_label)
        self._layout.addWidget(content)

    def _on_enable_toggled(self, checked: bool) -> None:
        try:
            if checked:
                self._binder.enable()
            else:
                self._binder.disable()
        except Exception as ex:
            logger.exception(ex)
            self._status_label.setText(str(ex))
            self._enable_toggle.setChecked(self._binder.enabled)

    def _on_spectrum(self, data: dict) -> None:
        energies = np.asarray(data.get("energies", []), dtype=float)
        intensity = np.asarray(
            [np.nan if v is None else v for v in data.get("intensity", [])],
            dtype=float)
        if energies.size and energies.size == intensity.size:
            self._curve.setData(energies, intensity, connect="finite")

    def _on_status(self, data: dict) -> None:
        self._status_label.setText(
            f"{data.get('state', '?')} — {data.get('energies_done', 0)}/{data.get('total', 0)}")

    def _on_error(self, data: dict) -> None:
        self._status_label.setText(f"error: {data.get('error', '')}")

    def _on_complete(self, data: dict) -> None:
        self._status_label.setText(
            f"reduction complete: {', '.join(data.get('products', []))}")

    def _on_closing(self) -> None:
        try:
            self._binder.disable()
        except Exception as ex:
            logger.exception(ex)
        super()._on_closing()


class StxmSpectrumPanelPlugin(PanelPlugin):
    @property
    def name(self) -> str:
        return "stxm_spectrum"

    @property
    def description(self) -> str:
        return "Live I(E) spectrum panel for the stxm-live analysis service"

    def get_panel_class(self):
        from lightfall_pystxmcontrol.stxm_spectrum_panel import StxmSpectrumPanel
        return StxmSpectrumPanel
