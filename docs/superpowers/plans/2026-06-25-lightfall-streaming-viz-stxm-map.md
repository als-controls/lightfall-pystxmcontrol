# Unified Tiled-Streaming Visualization Updates + STXM Live Map (Phase 2c) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `VisualizationPanel`'s 2-second poll with Tiled WebSocket push as the update path for ALL Lightfall visualizations (streaming-only, no fallback), and add an STXM fly-scan live map that rides it.

**Architecture:** A `StreamBridge` (lightfall-core) subscribes to the active run's Tiled node and marshals each push from Tiled's background thread to the Qt GUI thread via a signal; the panel routes it to the active viz's new `on_stream_update(update)` (default impl calls `refresh()`, so every existing viz becomes push-driven untouched). The STXM map viz (lightfall-pystxmcontrol) overrides `on_stream_update` to blit each pushed line into a growing 2-D image. Persistence reuses the existing patched `TiledWriter`. Cross-repo: core mechanism in `~/PycharmProjects/ncs/lightfall`, STXM consumer in `~/PycharmProjects/ncs/lightfall-pystxmcontrol`.

**Tech Stack:** Python 3.14, Lightfall (`VisualizationPanel`, `BaseVisualization`, `TiledService`), Tiled 0.2.9 client streaming (`tiled.client.stream`), PySide6 (Qt signals/threads), bluesky, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-25-lightfall-streaming-viz-stxm-map-design.md`

## Global Constraints

- **Streaming-only, NO fallback:** the 2-second `QTimer` poll in `VisualizationPanel` is REMOVED. Updates come only from Tiled WebSocket push. There is no poll fallback. The connected Tiled server MUST have `streaming_cache` enabled (als-tiled confirmed; the spike's local server uses `streaming_cache: {uri: "memory"}`).
- **All-or-nothing acceptance gate:** every shipped viz must update via push with no regression. Verified for the current set — all read array (`array-data`) or table (`table-data`) structures, both streamable in 0.2.9. A future viz reading a non-streamable structure (sparse/awkward/xarray) is out of scope until Tiled streams it.
- **`BaseVisualization.on_stream_update(update)`** is added with a **default body `self.refresh()`** (NOT abstract — existing subclasses must keep working unchanged). A viz may override it to apply the inline payload efficiently.
- **Threading:** Tiled's subscription callback runs on a background daemon thread (`start_in_thread`). It MUST NOT touch any Qt widget. Marshal to the GUI thread via a Qt signal; only the GUI-thread slot calls viz methods.
- **Lifecycle:** one subscription per active run; disconnect the prior subscription before subscribing to a new run; disconnect on teardown BEFORE hiding/removing the widget (theater-teardown ordering).
- **Run-completion detection** currently lives in `_on_refresh_tick` (the stop-doc check). Since the timer is removed, rehome it onto the existing engine doc-stream subscription (which already sees `start`/`stop`) — do not lose "live run completed" handling.
- **Reuse, don't reinvent:** the authenticated Tiled client comes from `TiledService.get_instance().client`; persistence reuses the existing patched `TiledWriter` (no new writer unless Task 1 proves it mis-shapes the map). The SOCKS-proxy patch already installed on `tiled.client.stream` is reused as-is.
- **Spike-pinned unknowns (Task 1):** (a) the Tiled 0.2.9 **container/run-level** subscription API + how child `array-data`/`table-data` route to the right viz (the prior spike proved per-array `ArrayClient.subscribe()`); (b) whether the existing patched `TiledWriter` persists the fly-scan as a streamable 2-D `(ny, nx)` map array.
- **Interpreter / tests:** run in **Lightfall's 3.14 venv** via `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest` — never bare `pytest`. The local streaming Tiled server (for integration tests/smoke) is launched with the spike-proven config; the venv already has the server deps installed (`zarr 2.18.7`, `redis`, `openpyxl`, `canonicaljson`).
- **No `git add -A`:** stage explicit paths only. Two repos — commit core changes in `~/PycharmProjects/ncs/lightfall`, STXM changes in `~/PycharmProjects/ncs/lightfall-pystxmcontrol`. **Do not commit lightfall-core changes on `master` without confirming the working branch; check `git status` first.**
- **Commit trailers** (every commit, both repos):
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo
  ```

## File structure

| Repo | File | Responsibility |
|---|---|---|
| lightfall | `scripts/spike_stream_viz.py` (new) | Task 1 spike: pin container-subscription API + writer persistence + integration points |
| lightfall | `src/lightfall/visualization/stream_bridge.py` (new) | `StreamBridge` QObject: subscribe to a Tiled node, marshal pushes bg-thread→Qt signal |
| lightfall | `src/lightfall/visualization/base_visualization.py` (modify) | add `on_stream_update(update)` default→`refresh()` |
| lightfall | `src/lightfall/ui/panels/visualization_panel.py` (modify) | remove 2s timer; wire `StreamBridge` on activate; route push→`on_stream_update`; rehome stop-doc detection; disconnect on teardown |
| lightfall-pystxmcontrol | `src/lightfall_pystxmcontrol/stxm_map_viz.py` (new) | `StxmMapVisualization(BaseVisualization)`: blit pushed lines into a 2-D image |
| lightfall-pystxmcontrol | `src/lightfall_pystxmcontrol/manifest.py` (modify) | add a `panel` PluginEntry for the map viz |
| lightfall-pystxmcontrol | `scripts/smoke_stxm_live_map.py` (new) | Task 6 end-to-end: fly-scan → Tiled (streaming) → live map render |

---

### Task 1: Spike — pin the container-subscription API + writer persistence + integration points

Empirically de-risk the two version-sensitive unknowns and record the exact lightfall-core integration points for Tasks 2-4, **before** any core change. **Spike, not TDD.** Reuse the prior STXM streaming spike's harness (`C:\Users\rp\AppData\Local\Temp\...\scratchpad\spike.py`, `config_streaming.yml`) as a starting point — but this spike lives in the lightfall repo and is committed.

**Files:**
- Create: `scripts/spike_stream_viz.py` (in the lightfall repo)
- Modify: `NOTES.md` or create `docs/superpowers/notes/2026-06-25-streaming-viz-spike.md` (record findings)

**Interfaces:**
- Produces, recorded for Tasks 2-6: the working container/run-level subscription call (or the per-array form + how to subscribe to each child); how `array-data`/`table-data`/`container-child-created` messages identify their source node (so the panel can route to the right viz); the exact `LiveArrayData`/`LiveTableData` payload-decode call; whether the patched `TiledWriter` writes the fly-scan as a streamable `(ny, nx)` array (and if not, the minimal fix); and the exact current `VisualizationPanel` regions to change (timer wiring, the `_entry`/`_current_widget`/`_is_live` state, the engine doc-stream subscription where stop-doc detection moves).

- [ ] **Step 1: Read the integration surface (record exact locations)**

Read (do not modify): `src/lightfall/visualization/base_visualization.py`; `src/lightfall/ui/panels/visualization_panel.py` (esp. `_start_refresh`/`_stop_refresh`/`_on_refresh_tick`/`_on_activated`/`_update_refresh`, the engine doc-stream subscription `_connect_engine`, and the `_entry`/`_current_widget`/`_is_live` state); `src/lightfall/services/tiled_service.py` (the `client` property ~172 and the `_install_tiled_stream_ws_proxy_patch` ~973-1037); `src/lightfall/visualization/widgets/image_stack.py` (`set_run`/`set_stream`/`refresh` as the array-viz model) and `widgets/table.py` (the table-viz model); and Tiled's `client/stream.py` (the subscription API: `subscribe`, `ArraySubscription`, container subscription if present, `start_in_thread`, `new_data`, `LiveArrayData.data`).

- [ ] **Step 2: Write `scripts/spike_stream_viz.py`**

Probe, against a local streaming Tiled 0.2.9 (config: `streaming_cache: {uri: "memory"}`, served with `python -m tiled serve config <yaml> --host 127.0.0.1 --port <P>`):
(a) Create a run-like container with a child array and a child table. Subscribe at the **container/run** level (find the API in `client/stream.py`; if no container-level subscribe exists, subscribe per-child and record that). Append to the array via `patch(line, offset=(row,0), extend=True)` and append rows to the table; confirm the subscriber receives `array-data` / `table-data` / `container-child-created`, and record **how each message identifies its source child** (path/key/segments) so the panel can route it.
(b) Decode each payload inline (`LiveArrayData.data()` etc.) and confirm it matches what was written.
(c) Drive the actual Phase-2b fly-scan through Lightfall's `BlueskyEngine` with `TiledService` pointed at this local streaming server; inspect what the patched `TiledWriter` wrote — is the `STXMLineFlyer` data a growing 2-D `(ny, nx)` **array** node (streamable), or a 1-D-per-event table column? Record the node path + structure family + shape.

- [ ] **Step 3: Run the spike**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/spike_stream_viz.py`
Expected: prints the working subscription call; per-message source-identification; inline-decoded payloads matching writes; and the fly-scan's persisted node path/structure/shape. If container-level subscription is unavailable, the per-child form is the recorded result.

- [ ] **Step 4: Record findings**

Write the findings doc with, copy-pasteable for Tasks 2-6: the subscription API (container or per-child) + message→source routing; the payload-decode calls; the fly-scan persistence verdict (streamable 2-D array? path? or the minimal fix needed); and the exact `VisualizationPanel`/`TiledService` symbols + line regions Tasks 2-4 will touch.

- [ ] **Step 5: Commit** (in the lightfall repo — confirm branch first with `git status`)

```bash
cd ~/PycharmProjects/ncs/lightfall
git add scripts/spike_stream_viz.py docs/superpowers/notes/2026-06-25-streaming-viz-spike.md
git commit -m "spike: pin Tiled container-subscription API + fly-scan writer persistence + viz-panel integration points

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

### Task 2: `StreamBridge` — subscribe to a Tiled node, marshal pushes to the GUI thread

**Files:**
- Create: `src/lightfall/visualization/stream_bridge.py` (lightfall repo)
- Test: `tests/visualization/test_stream_bridge.py` (lightfall repo)

**Interfaces:**
- Consumes: `TiledService.get_instance().client`; the subscription API recorded in Task 1.
- Produces: `class StreamBridge(QObject)` with a Qt signal `update_received = Signal(object)`, `connect_node(node) -> None` (opens the Tiled subscription, registers a bg-thread callback that emits `update_received`), and `disconnect() -> None` (idempotent, bounded). The bg-thread callback only emits the signal — it never touches widgets.

- [ ] **Step 1: Write the failing test**

```python
# tests/visualization/test_stream_bridge.py
from PySide6.QtCore import QObject
from lightfall.visualization.stream_bridge import StreamBridge


class _FakeSub:
    """Stand-in for a Tiled subscription: lets the test fire a callback."""
    def __init__(self):
        self._cb = None
        self.disconnected = False
    def add_callback(self, cb):
        self._cb = cb
    def start_in_thread(self, **kw):
        pass
    def disconnect(self):
        self.disconnected = True
    def fire(self, update):
        self._cb(update)


class _FakeNode:
    def __init__(self, sub):
        self._sub = sub
    def subscribe(self):
        return self._sub


def test_bridge_emits_signal_on_update(qtbot):
    sub = _FakeSub()
    bridge = StreamBridge()
    received = []
    bridge.update_received.connect(received.append)
    bridge.connect_node(_FakeNode(sub))
    sub.fire({"type": "array-data", "row": 0})
    # signal delivery may be queued; process events
    qtbot.wait(50)
    assert received == [{"type": "array-data", "row": 0}]


def test_bridge_disconnect_is_idempotent():
    sub = _FakeSub()
    bridge = StreamBridge()
    bridge.connect_node(_FakeNode(sub))
    bridge.disconnect()
    bridge.disconnect()  # second call must not raise
    assert sub.disconnected is True
```

(If `qtbot` (pytest-qt) is unavailable in the venv, drive the Qt event loop with `QApplication.processEvents()` after constructing `QApplication.instance() or QApplication([])`, mirroring the Phase-2b smoke pattern.)

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/visualization/test_stream_bridge.py -v`
Expected: FAIL (`ImportError: cannot import name 'StreamBridge'`).

- [ ] **Step 3: Implement `stream_bridge.py`**

```python
# src/lightfall/visualization/stream_bridge.py
"""Bridges a Tiled streaming subscription to the Qt GUI thread.

The Tiled subscription callback fires on a background daemon thread; this
QObject re-emits each update as a Qt signal so GUI-thread slots can update
widgets safely. Only emit here — never touch widgets on the callback thread.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal
from loguru import logger


class StreamBridge(QObject):
    update_received = Signal(object)  # emitted on the GUI thread (queued)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sub: Any | None = None

    def connect_node(self, node: Any) -> None:
        """Subscribe to a Tiled node's stream; emit update_received per push."""
        self.disconnect()
        # Subscription API per Task 1's recorded form (container-level if available,
        # else per-child). The prior spike proved: sub = node.subscribe();
        # sub.new_data.add_callback(cb); sub.start_in_thread(start=1).
        sub = node.subscribe()
        sub_new_data = getattr(sub, "new_data", None)
        if sub_new_data is not None:           # tiled ArraySubscription style
            sub_new_data.add_callback(self._on_update)
        else:                                   # _FakeSub / alt style
            sub.add_callback(self._on_update)
        sub.start_in_thread(start=1)
        self._sub = sub

    def _on_update(self, update: Any) -> None:
        # BACKGROUND THREAD. Do not touch widgets. Signal is queued to GUI thread.
        self.update_received.emit(update)

    def disconnect(self) -> None:
        if self._sub is not None:
            try:
                self._sub.disconnect()
            except Exception as e:
                logger.warning("StreamBridge disconnect error: {}", e)
            self._sub = None
```

Match Task 1's recorded subscription API exactly (the `new_data`-vs-`add_callback` shape and `start_in_thread` args); the contract (emit `update_received` on the GUI thread per push, idempotent bounded `disconnect`) is fixed.

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/visualization/test_stream_bridge.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit** (lightfall repo)

```bash
git add src/lightfall/visualization/stream_bridge.py tests/visualization/test_stream_bridge.py
git commit -m "feat: StreamBridge — marshal Tiled streaming pushes to the Qt GUI thread

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

### Task 3: `BaseVisualization.on_stream_update` — default to `refresh()`

**Files:**
- Modify: `src/lightfall/visualization/base_visualization.py` (lightfall repo)
- Test: `tests/visualization/test_base_visualization_update.py` (lightfall repo)

**Interfaces:**
- Produces: `BaseVisualization.on_stream_update(self, update: Any) -> None` — a NON-abstract method whose default body calls `self.refresh()`. Existing subclasses inherit it unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/visualization/test_base_visualization_update.py
from typing import Any
from lightfall.visualization.base_visualization import BaseVisualization


class _StubViz(BaseVisualization):
    viz_name = "stub"
    viz_display_name = "Stub"
    def __init__(self):
        super().__init__()
        self.refresh_calls = 0
    @staticmethod
    def can_handle(run): return 0
    def set_run(self, run): ...
    def get_streams(self): return []
    def set_stream(self, name): ...
    def get_fields(self): return []
    def set_field(self, name): ...
    def refresh(self): self.refresh_calls += 1


def test_on_stream_update_defaults_to_refresh(qapp):
    viz = _StubViz()
    viz.on_stream_update({"type": "array-data"})
    assert viz.refresh_calls == 1
```

(`qapp` = a session `QApplication` fixture; `_StubViz` is a `QWidget`, so a `QApplication` must exist. Use `QApplication.instance() or QApplication([])` if no fixture.)

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/visualization/test_base_visualization_update.py -v`
Expected: FAIL (`AttributeError: 'BaseVisualization' object has no attribute 'on_stream_update'`).

- [ ] **Step 3: Add the method to `base_visualization.py`**

After the abstract `refresh` method (currently the last method, lines 72-74), add:

```python
    def on_stream_update(self, update: Any) -> None:
        """Apply a Tiled streaming push. Default: re-read via refresh().

        The VisualizationPanel calls this on the GUI thread for each Tiled
        stream push affecting this viz's data. Subclasses may override to
        apply the inline payload directly (avoiding a full re-read).
        """
        self.refresh()
```

(Do not make it abstract; existing subclasses must inherit it. `Any` is already imported.)

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/visualization/test_base_visualization_update.py -v`
Expected: PASS. Then run the existing visualization tests to confirm no regression: `... -m pytest tests/visualization/ -q`.

- [ ] **Step 5: Commit** (lightfall repo)

```bash
git add src/lightfall/visualization/base_visualization.py tests/visualization/test_base_visualization_update.py
git commit -m "feat: BaseVisualization.on_stream_update (default re-reads via refresh)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

### Task 4: `VisualizationPanel` — replace the poll with streaming

**Files:**
- Modify: `src/lightfall/ui/panels/visualization_panel.py` (lightfall repo)
- Test: `tests/ui/panels/test_visualization_panel_streaming.py` (lightfall repo)

**Interfaces:**
- Consumes: `StreamBridge` (Task 2); `BaseVisualization.on_stream_update` (Task 3); the active Tiled node (`self._entry`), `self._current_widget`, `self._is_live`, and the engine doc-stream subscription — exact symbols per Task 1.
- Produces: a panel that, on run activation, points a `StreamBridge` at the active node and connects `bridge.update_received → self._current_widget.on_stream_update`; removes the 2s `QTimer`; rehomes stop-doc detection to the engine doc-stream subscription; disconnects the bridge before teardown/run-switch.

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/panels/test_visualization_panel_streaming.py
# Verify: (1) no QTimer-based polling remains; (2) a push routed through the
# panel reaches the active viz's on_stream_update on the GUI thread.
from lightfall.ui.panels import visualization_panel as vp_mod


def test_no_poll_timer_symbols():
    src = (vp_mod.__file__)
    text = open(src, encoding="utf-8").read()
    # The 2s poll is removed: no QTimer.start(2000) and no _on_refresh_tick.
    assert "_on_refresh_tick" not in text
    assert ".start(2000)" not in text


def test_push_routes_to_active_viz_on_stream_update(qapp, monkeypatch):
    # Construct the panel with a stub active viz; emit a StreamBridge update;
    # assert the viz received on_stream_update with the payload.
    # (Exact construction per Task 1's recorded panel API; the contract is:
    #  panel wires bridge.update_received -> current_widget.on_stream_update.)
    ...
```

The second test's exact construction depends on Task 1's recorded `VisualizationPanel` API (how a viz becomes `_current_widget`, how a run is activated). Write it to drive a real `StreamBridge.update_received.emit(payload)` and assert the stub `_current_widget.on_stream_update` received `payload`. If full panel construction is too heavy in a unit test, assert the wiring at the method level (the activation method connects the signal and the routing slot calls `_current_widget.on_stream_update`).

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ui/panels/test_visualization_panel_streaming.py -v`
Expected: FAIL (`_on_refresh_tick`/`.start(2000)` still present; routing not wired).

- [ ] **Step 3: Rewire the panel (per Task 1's recorded regions)**

Make these changes in `visualization_panel.py`:
1. **Remove** `_start_refresh`, `_stop_refresh`, `_on_refresh_tick`, the `_refresh_timer` attribute, and the `QTimer` import if now unused.
2. Add a `StreamBridge` member (created lazily). In the run-activation path (currently `_on_activated`/`_update_refresh`/`_sync_to_live_run`): when a live run + `_current_widget` are present, call `bridge.connect_node(self._entry)` (or the per-child nodes per Task 1) and connect `bridge.update_received` to a new slot `self._on_stream_update(update)` that does `self._current_widget.on_stream_update(update)` (guarded for `None`). Do one initial `self._current_widget.refresh()` (initial render).
3. **Rehome stop-doc detection:** the `_on_refresh_tick` stop-doc check (`self._entry.metadata.get("stop")`) moves to the existing engine doc-stream subscription — on a `stop` document for the active run, set `self._is_live = False` and `bridge.disconnect()`.
4. On `_on_deactivated`/run-switch/teardown: `bridge.disconnect()` BEFORE the widget is hidden/removed.

(Provide the concrete diff against the exact lines Task 1 recorded; the contract — no poll timer, push routed to `on_stream_update`, stop-doc handled on the doc stream, bridge disconnected before teardown — is fixed.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ui/panels/test_visualization_panel_streaming.py -v`
Expected: PASS. Then the full viz + panel suites: `... -m pytest tests/visualization/ tests/ui/ -q` → no regression.

- [ ] **Step 5: Commit** (lightfall repo)

```bash
git add src/lightfall/ui/panels/visualization_panel.py tests/ui/panels/test_visualization_panel_streaming.py
git commit -m "feat: VisualizationPanel updates via Tiled streaming push (remove 2s poll)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

### Task 5: `StxmMapVisualization` — live 2-D map via inline-payload blitting

**Files:**
- Create: `src/lightfall_pystxmcontrol/stxm_map_viz.py` (lightfall-pystxmcontrol repo)
- Modify: `src/lightfall_pystxmcontrol/manifest.py` (add a `panel` entry)
- Test: `tests/test_stxm_map_viz.py` (lightfall-pystxmcontrol repo)

**Interfaces:**
- Consumes: `lightfall.visualization.base_visualization.BaseVisualization` (with `on_stream_update`, Task 3); the fly-scan map node (per Task 1's persistence finding); the Tiled `array-data` update payload (decoded line + its `offset` row).
- Produces: `class StxmMapVisualization(BaseVisualization)` (`viz_name="stxm_map"`) whose `on_stream_update` blits each pushed line into a growing 2-D image; a `StxmMapPanelPlugin(PanelPlugin)` + manifest `panel` entry.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stxm_map_viz.py
import numpy as np
from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_on_stream_update_blits_line_into_map():
    _qapp()
    viz = StxmMapVisualization()
    viz.begin_map(ny=4, nx=8)                       # allocate the 2-D image
    line = np.arange(8, dtype=float) + 1.0
    # Update payload shape per Task 1's recorded array-data form: a line + its row.
    viz.on_stream_update(_make_array_data(row=2, line=line))
    img = viz.current_image()
    assert np.array_equal(img[2], line)
    assert (img[0] == 0).all()                      # untouched rows stay zero


def _make_array_data(row, line):
    # Minimal stand-in matching the decoded LiveArrayData contract from Task 1:
    # an object exposing the row offset and an inline-decoded line array.
    class _U:
        type = "array-data"
        def __init__(self, row, line):
            self.offset = (row, 0)
            self._line = line
        def data(self):
            return self._line.reshape(1, -1)
    return _U(row, line)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_stxm_map_viz.py -v`
Expected: FAIL (`ImportError: cannot import name 'StxmMapVisualization'`).

- [ ] **Step 3: Implement `stxm_map_viz.py`**

```python
# src/lightfall_pystxmcontrol/stxm_map_viz.py
"""Live STXM map: a 2-D image grown line-by-line from Tiled array-data pushes."""
from __future__ import annotations

from typing import Any

import numpy as np
from lightfall.visualization.base_visualization import BaseVisualization


class StxmMapVisualization(BaseVisualization):
    viz_name = "stxm_map"
    viz_display_name = "STXM Live Map"
    viz_icon = "image"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._image: np.ndarray | None = None
        self._image_view = None  # pyqtgraph ImageView, built lazily in _ensure_view()

    # --- map lifecycle ---
    def begin_map(self, ny: int, nx: int) -> None:
        self._image = np.zeros((ny, nx), dtype=float)
        self._render()

    def current_image(self) -> np.ndarray | None:
        return self._image

    # --- streaming push (override: blit the inline line, no re-read) ---
    def on_stream_update(self, update: Any) -> None:
        if getattr(update, "type", None) != "array-data" or self._image is None:
            return self.refresh()  # non-array / no map yet → fall back to re-read
        row = update.offset[0]
        line = np.asarray(update.data()).reshape(-1)
        if 0 <= row < self._image.shape[0] and line.size == self._image.shape[1]:
            self._image[row] = line
            self._render()

    def _render(self) -> None:
        if self._image is None:
            return
        self._ensure_view()
        self._image_view.setImage(self._image, autoLevels=False)

    def _ensure_view(self) -> None:
        if self._image_view is None:
            import pyqtgraph as pg
            from PySide6.QtWidgets import QVBoxLayout
            self._image_view = pg.ImageView(self)
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self._image_view)

    # --- BaseVisualization plumbing (bind to the Tiled map node) ---
    @staticmethod
    def can_handle(run: Any) -> int:
        try:
            return 95 if "STXMLineFlyer" in run else 0   # map node name per Task 1
        except Exception:
            return 0

    def set_run(self, run: Any) -> None:
        self._run = run

    def get_streams(self) -> list[str]:
        return ["primary"]

    def set_stream(self, stream_name: str) -> None:
        self._stream_name = stream_name
        # Open the map node + size the image from its current shape (per Task 1's path).
        self.refresh()

    def get_fields(self) -> list[str]:
        return ["STXMLineFlyer"]

    def set_field(self, field_name: str) -> None:
        self._field_name = field_name

    def refresh(self) -> None:
        """Re-read the map node from Tiled (initial render + fallback)."""
        node = self._map_node()
        if node is None:
            return
        arr = np.asarray(node.read())
        if arr.ndim == 2:
            self._image = arr.astype(float)
            self._render()

    def _map_node(self):
        # Resolve the (ny,nx) map ArrayClient from self._run per Task 1's recorded path.
        if self._run is None:
            return None
        try:
            return self._run["primary"]["STXMLineFlyer"]   # confirm path in Task 1
        except Exception:
            return None
```

Match Task 1's recorded form for: the `array-data` payload (`offset`/`.data()` shape), the map node path, and the node name `can_handle` keys on. The contract (override `on_stream_update` to blit the line; `refresh()` re-reads as fallback/initial) is fixed.

- [ ] **Step 4: Add the manifest `panel` entry**

In `src/lightfall_pystxmcontrol/manifest.py`, add a `StxmMapPanelPlugin` and a `PluginEntry("panel", "stxm_map", "lightfall_pystxmcontrol.stxm_map_viz:StxmMapPanelPlugin")`. Add the plugin class to `stxm_map_viz.py`:

```python
from lightfall.plugins.panel_plugin import PanelPlugin

class StxmMapPanelPlugin(PanelPlugin):
    @property
    def name(self) -> str:
        return "stxm_map"
    def get_panel_class(self):
        return StxmMapVisualization
```

(Confirm `PanelPlugin`'s exact required methods — `get_panel_class` vs other — against `lightfall/plugins/panel_plugin.py`; match it.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/test_stxm_map_viz.py -v`
Expected: PASS. Then the full package suite: `... -m pytest tests/ -q` → all prior 21 + these pass.

- [ ] **Step 6: Commit** (lightfall-pystxmcontrol repo)

```bash
cd ~/PycharmProjects/ncs/lightfall-pystxmcontrol
git add src/lightfall_pystxmcontrol/stxm_map_viz.py src/lightfall_pystxmcontrol/manifest.py tests/test_stxm_map_viz.py
git commit -m "feat: StxmMapVisualization — live 2-D STXM map via Tiled array-data pushes

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

### Task 6: End-to-end proof — fly-scan → streaming Tiled → live map (Phase 2c done)

**Files:**
- Create: `scripts/smoke_stxm_live_map.py` (lightfall-pystxmcontrol repo)

**Interfaces:**
- Consumes: the fly-scan plan + flyer (Phase 2b); `TiledService` → a local streaming Tiled; `StreamBridge` (Task 2); `StxmMapVisualization` (Task 5). **Done = the STXM fly-scan map renders live via Tiled push, AND an existing array + table viz still update via push (regression gate).**

- [ ] **Step 1: Write the smoke (headless, real streaming server)**

A headless script that: launches/uses a local streaming Tiled 0.2.9 (spike config), configures `TiledService` to it, runs the Phase-2b fly-scan through Lightfall's `BlueskyEngine` (so the patched `TiledWriter` persists the map), points a `StreamBridge` at the run node, drives a `StxmMapVisualization` via the bridge, and asserts the rendered `current_image()` fills in `ny` rows with positive counts as pushes arrive. Then, with an existing array viz (`ImageStackVisualization`) and the `TableVisualization` bound to the same run, assert each receives `on_stream_update` (push-driven) — the all-or-nothing regression gate. Use offscreen Qt (`QT_QPA_PLATFORM=offscreen`) + the Phase-2b poll-and-process pattern. Use the exact subscription + node paths recorded in Task 1.

- [ ] **Step 2: Run the smoke**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/smoke_stxm_live_map.py`
Expected: a line like `STXM live map: 6 lines x 10 pts rendered via Tiled push; existing array+table viz updated via push`. If a push path fails for any viz, capture the exact error (all-or-nothing — that is a real failure to surface).

- [ ] **Step 3: Run both suites once more**

Run: `C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python -m pytest tests/ -q` (in lightfall-pystxmcontrol) and `... -m pytest tests/visualization/ tests/ui/ -q` (in lightfall).
Expected: all pass.

- [ ] **Step 4: Commit (Phase 2c done)** (lightfall-pystxmcontrol repo)

```bash
git add scripts/smoke_stxm_live_map.py
git commit -m "feat: live STXM map renders via Tiled streaming push end-to-end (Phase 2c done)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E5rHNPQgibARJ7jgUjzCpo"
```

---

## Self-Review

**Spec coverage:**
- Streaming-only update path replacing the 2s poll for ALL viz → Task 4 (panel rewire) + Task 3 (on_stream_update default makes all viz push-driven). ✓
- No fallback (timer removed) → Task 4 Step 3 + the `test_no_poll_timer_symbols` gate. ✓
- `BaseVisualization.on_stream_update` default→refresh, non-abstract → Task 3. ✓
- GUI-thread marshaling via Qt signal → Task 2 (`StreamBridge`). ✓
- Subscription lifecycle (one per run, disconnect before teardown/switch) → Task 4 Step 3. ✓
- Rehome stop-doc/run-completion detection off the removed timer → Task 4 Step 3. ✓
- STXM map viz overriding on_stream_update to blit inline lines → Task 5. ✓
- Reuse `TiledService` client + existing patched `TiledWriter`; verify persistence → Task 1 (verify) + Tasks 5/6 (consume). ✓
- All-or-nothing regression gate (array + table viz update via push) → Task 6 Step 1. ✓
- Container-subscription API + writer persistence are spike-pinned → Task 1. ✓
- Cross-repo, no `git add -A`, branch check, trailers → Global Constraints + each Task's commit. ✓
- Out-of-scope (HDF5, non-streamable structures, viz-internal rewrites) → not planned. ✓

**Placeholder scan:** Task 1 is a spike whose job is pinning the empirical unknowns (container-subscription API, writer persistence shape, exact core integration points) — its "record the working form" notes are spike-pinning, not placeholders. The "per Task 1's recorded form" notes in Tasks 2/4/5 are confined to the genuinely version/code-sensitive bits (subscription API shape, panel line regions, the array-data payload/node path); the contracts (StreamBridge emits on the GUI thread; on_stream_update default refresh; panel routes push→on_stream_update with no timer; map viz blits the line) are concrete with complete code. Task 4 Step 1's second test and Step 3's diff are specified against Task 1's recorded panel API because the exact current panel construction/lines are what the spike records — the required behavior is fully stated.

**Type consistency:** `StreamBridge.update_received: Signal(object)` + `connect_node(node)` + `disconnect()`; `BaseVisualization.on_stream_update(update)`; `StxmMapVisualization` (`viz_name="stxm_map"`, `begin_map(ny,nx)`, `current_image()`, `on_stream_update` blitting `update.offset[0]`/`update.data()`); the map node named `STXMLineFlyer` (matching the Phase-2b flyer device name + event data key); and the `panel` PluginEntry are used consistently across Tasks 2-6.
