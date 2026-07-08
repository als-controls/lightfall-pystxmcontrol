"""Live STXM map: a 2-D image grown line-by-line from Tiled array-data pushes.

Implements ``StxmMapVisualization``, a ``BaseVisualization`` subclass that renders
the STXM fly-scan as a 2-D map updating live by overriding ``on_stream_update``
to blit each pushed Tiled ``array-data`` line into the image.

Node key: ``<run>/primary/STXMLineFlyer``
  The Phase-2b backend names the flyer ``STXMLineFlyer`` (``flyer.py`` sets
  ``self._name``), so the Tiled map node is keyed on that string.  Task 6's
  end-to-end run will definitively confirm this key against a real scan.

LiveArrayData accessors used (confirmed from tiled/client/stream.py + stream_messages.py):
  - ``update.type``          str literal "array-data"
  - ``update.offset``        Optional[tuple[int, ...]] — (row, 0) for a patch,
                              None for the first full-array write
  - ``update.data()``        np.ndarray with shape == update.shape, e.g. (1, nx)
                              for a single-row patch; decoded inline, no refetch

Blitting by offset row is IDEMPOTENT: a replayed/duplicate line lands at the
same row index.  Out-of-bounds rows are silently dropped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from lightfall.plugins.types import PluginType
from lightfall.visualization.base_visualization import BaseVisualization

from .image_render import ImageRenderMixin

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Visualization widget
# ---------------------------------------------------------------------------

_MAP_FIELD = "STXMLineFlyer"


class StxmMapVisualization(ImageRenderMixin, BaseVisualization):
    """Live 2-D STXM map that grows line-by-line via Tiled array-data pushes.

    Lifecycle (called by VisualizationPanel):
        1. ``can_handle(run)`` — scores 95 if the run has a ``STXMLineFlyer`` node
        2. ``set_run(run)`` — caches the run reference
        3. ``get_streams()`` → ["primary"]
        4. ``set_stream(name)`` → ``refresh()`` for initial render
        5. ``get_fields()`` → ["STXMLineFlyer"]
        6. ``set_field(name)`` — stores field selection
        7. ``on_stream_update(update)`` — blits each incoming line (override)
        8. ``refresh()`` — re-reads the full map node (fallback / initial)

    Live path (``on_stream_update``):
        Receives a ``LiveArrayData`` from the StreamBridge.  If ``update.type``
        is "array-data" and ``update.offset`` is not None, extracts the row from
        ``update.offset[0]``, calls ``update.data()`` to get the decoded line
        array (shape ``(1, nx)``), bounds-checks, and blits into ``self._image``.

        When ``offset`` is None (first full-array write) or the type is not
        "array-data", falls back to ``refresh()`` which re-reads the Tiled node.
    """

    viz_name = "stxm_map"
    viz_display_name = "STXM Live Map"
    viz_icon = "image"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._init_render_state()

    # ------------------------------------------------------------------
    # Map lifecycle (called externally to allocate / access the image)
    # ------------------------------------------------------------------

    def begin_map(self, ny: int, nx: int) -> None:
        """Allocate a zero-filled (ny, nx) image and render it."""
        self._image = np.zeros((ny, nx), dtype=float)
        self._render()

    def current_image(self) -> np.ndarray | None:
        """Return the current 2-D image array, or None before begin_map."""
        return self._image

    # ------------------------------------------------------------------
    # Streaming push (override): blit inline line, avoid full re-read
    # ------------------------------------------------------------------

    def on_stream_update(self, update: Any) -> None:
        """Apply a Tiled array-data push by blitting the line into the image.

        Falls back to ``refresh()`` for:
        - non array-data update types (e.g. "table-data")
        - ``offset is None`` (first write delivers the full array; re-read it)
        - no image allocated yet (begin_map not called)

        Args:
            update: A ``LiveArrayData`` (or compatible stub) with:
                - ``.type``    str  — "array-data"
                - ``.offset``  Optional[tuple[int, ...]] — (row, col) patch offset
                - ``.data()``  callable → np.ndarray of shape (1, nx)
        """
        if getattr(update, "type", None) != "array-data":
            self.refresh()
            return

        offset = getattr(update, "offset", None)
        if offset is None:
            # First full-array write — re-read the node to get the whole thing
            self.refresh()
            return

        if self._image is None:
            # Map not yet allocated; refresh will either allocate or no-op
            self.refresh()
            return

        row = offset[0]
        ny, nx = self._image.shape
        if not (0 <= row < ny):
            return  # silently drop out-of-bounds row

        line = np.asarray(update.data()).reshape(-1)
        if line.size != nx:
            return  # silently drop mismatched line length

        self._image[row] = line
        self._render()

    # ------------------------------------------------------------------
    # BaseVisualization abstract interface
    # ------------------------------------------------------------------

    @staticmethod
    def can_handle(run: Any) -> int:
        """Score 0-100 for how well this viz handles the given run.

        The panel passes the TOP-LEVEL BlueskyRun entry.  The fly-scan map array
        lives at ``run["primary"]["STXMLineFlyer"]`` (a child of the primary
        stream), NOT as a direct top-level child — so ``"STXMLineFlyer" in run``
        is unreliable at the top level.  Instead, identify an STXM fly-scan run
        by the most reliable signal first:

        1. **Start-doc plan name** (best): the Phase-2b plan sets
           ``plan_name="stxm_fly_raster"`` in the run metadata
           (``plans.py``), which is reliably present at the top level from
           scan start.  Score 95 on a match.
        2. **Primary-stream probe** (fallback): look for the ``STXMLineFlyer``
           key inside ``run["primary"]`` via ``__contains__``.  Score 95.

        The whole body is wrapped in ``try/except -> 0`` so a missing catalog,
        a partially-formed run, or any container that raises can never crash the
        selector.

        Note: Task 6's end-to-end run definitively confirms it scores +
        auto-selects on a real STXM fly-scan.
        """
        try:
            # 1. Start-doc plan name — the most reliable top-level signal.
            metadata = getattr(run, "metadata", None)
            if metadata is not None:
                start = metadata.get("start", {}) or {}
                if start.get("plan_name") == "stxm_fly_raster":
                    return 95

            # 2. Fallback: probe the primary stream for the flyer key.
            try:
                primary = run["primary"]
            except Exception:
                primary = None
            if primary is not None and _MAP_FIELD in primary:
                return 95

            return 0
        except Exception:
            return 0

    def set_run(self, run: Any) -> None:
        """Bind the BlueskyRun tiled entry."""
        self._run = run

    def get_streams(self) -> list[str]:
        """Return the stream names this viz reads."""
        return ["primary"]

    def set_stream(self, stream_name: str) -> None:
        """Select a stream and do an initial render via refresh()."""
        self._stream_name = stream_name
        self.refresh()

    def get_fields(self) -> list[str]:
        """Return the data fields this viz reads from the selected stream."""
        return [_MAP_FIELD]

    def set_field(self, field_name: str) -> None:
        """Select the active field."""
        self._field_name = field_name

    def refresh(self) -> None:
        """Re-read the full map node from Tiled (initial render and fallback).

        Called on set_stream(), on offset=None pushes, and on non-array-data
        pushes.  Reads the (ny, nx) array from the Tiled node and re-renders.
        No-op if the node is unavailable (e.g., run not yet set).
        """
        node = self._map_node()
        if node is None:
            return
        try:
            arr = np.asarray(node.read())
        except Exception:
            return
        if arr.ndim == 2:
            self._image = arr.astype(float)
            self._render()

    def _map_node(self):
        """Resolve the map ArrayClient from self._run.

        Path: ``<run>/primary/STXMLineFlyer`` — recorded in Task 1 spike
        (``primary/Counter1`` in the spike's manually-built flyer; the real
        Phase-2b flyer uses ``STXMLineFlyer`` as its name).
        """
        if self._run is None:
            return None
        try:
            return self._run["primary"][_MAP_FIELD]
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Visualization plugin wrapper
# ---------------------------------------------------------------------------


class StxmMapVizPlugin(PluginType):
    """Visualization plugin that registers StxmMapVisualization.

    Uses ``type_name="visualization"`` so the loader registers this instance
    with ``VisualizationRegistry`` (not PanelRegistry — StxmMapVisualization
    is a BaseVisualization/QWidget, not a BasePanel).

    The VisualizationPanel's selector picks this viz when ``can_handle`` scores
    highest on a run containing a ``STXMLineFlyer`` node.
    """

    type_name = "visualization"

    @property
    def name(self) -> str:
        return "stxm_map"

    def get_viz_class(self) -> type[StxmMapVisualization]:
        """Return the visualization widget class."""
        return StxmMapVisualization

    def get_introspection_data(self) -> dict:
        data = super().get_introspection_data()
        data["viz_name"] = StxmMapVisualization.viz_name
        data["viz_display_name"] = StxmMapVisualization.viz_display_name
        return data
