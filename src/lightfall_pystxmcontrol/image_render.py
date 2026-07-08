"""Shared pyqtgraph image rendering: ImageItem.updateImage + auto-LUT.

Extracted verbatim from StxmMapVisualization (Phase 2c) so the 2-D map and
the 3-D stack visualizations render identically. Host classes provide
``self._image`` (2-D ndarray | None) and inherit QWidget.
"""
from __future__ import annotations

import numpy as np


class ImageRenderMixin:
    """Mixin: lazy pg.ImageView + lightweight updateImage + auto-LUT levels."""

    def _init_render_state(self) -> None:
        self._image: np.ndarray | None = None
        self._image_view = None  # pyqtgraph ImageView, built lazily
        # Auto-LUT: levels track the data min/max automatically until the user
        # manually adjusts the histogram, at which point they're frozen.
        self._auto_levels: bool = True
        # Guard set True while we apply auto levels ourselves, so the histogram
        # level-change signal (emitted synchronously by setLevels) is not
        # mistaken for a manual user adjustment.
        self._applying_auto_levels: bool = False

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        """Push the current image to the pyqtgraph ImageView.

        Uses ``ImageItem.updateImage`` (the lightweight per-frame path) rather
        than ``ImageView.setImage`` (which re-runs view auto-ranging, the
        timeline, and histogram-range resets every call).  When auto-LUT is
        enabled, the display levels are re-scaled to the data's finite min/max
        afterwards; once the user adjusts the histogram, that re-scaling stops.

        The whole body runs under the ``_applying_auto_levels`` guard so that
        the level-change signals emitted *synchronously* by ``updateImage`` /
        ``setLevels`` are not mistaken for a manual user adjustment.
        """
        if self._image is None:
            return
        # An all-NaN frame has nothing to display, and pyqtgraph's level
        # computation would emit All-NaN RuntimeWarnings; unfilled stack
        # frames hit this before their first blit.
        if not np.isfinite(self._image).any():
            return
        self._ensure_view()
        self._applying_auto_levels = True
        try:
            self._image_view.getImageItem().updateImage(self._image)
            if self._auto_levels:
                rng = self._auto_level_range()
                if rng is not None:
                    self._image_view.setLevels(*rng)
        finally:
            self._applying_auto_levels = False

    def _auto_level_range(self) -> tuple[float, float] | None:
        """Return ``(lo, hi)`` from the image's finite values, or None.

        Computed over the whole image (unfilled rows read as the zero fill,
        which is the natural floor for non-negative STXM counts).  Returns a
        slightly widened range when the data is flat to avoid a zero-width LUT.
        """
        if self._image is None:
            return None
        finite = self._image[np.isfinite(self._image)]
        if finite.size == 0:
            return None
        lo = float(finite.min())
        hi = float(finite.max())
        if hi <= lo:
            hi = lo + 1.0
        return lo, hi

    def _ensure_view(self) -> None:
        """Lazily build the ImageView widget on first render."""
        if self._image_view is None:
            import pyqtgraph as pg
            from PySide6.QtWidgets import QVBoxLayout

            self._image_view = pg.ImageView(self)
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self._image_view)
            # Detect a manual histogram adjustment so we can stop auto-scaling.
            self._image_view.getHistogramWidget().sigLevelChangeFinished.connect(
                self._on_levels_changed
            )

    def _on_levels_changed(self, *_args) -> None:
        """Disable auto-LUT when the user adjusts the histogram levels.

        Ignored while we apply auto levels ourselves (``_applying_auto_levels``
        is True): those signals are programmatic, not a user interaction.
        """
        if self._applying_auto_levels:
            return
        self._auto_levels = False
