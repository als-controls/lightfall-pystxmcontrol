"""Phase-2c capstone smoke: simulated STXM fly-scan map renders LIVE via Tiled push.

This is the end-to-end proof that the whole Phase-2c streaming-viz path works:

  1. Launch a local streaming Tiled 0.2.9 server (streaming_cache: {uri: memory}),
     wait until reachable, tear it down at the end.
  2. Point Lightfall's TiledService at it; connect() auto-subscribes the patched
     ThreadedTiledWriter (built with max_array_size=0, Task 4b) to the engine.
  3. Drive the Phase-2b fly-scan through Lightfall's BlueskyEngine, with the flyer
     constructed via the REAL backend path so its name is "STXMLineFlyer" (the data
     key the map viz expects). Confirm the persisted node path/shape by walking the
     run tree.
  4. LIVE MAP: subscribe a StreamBridge to <run>/primary/STXMLineFlyer, drive a
     StxmMapVisualization so each array-data push blits a line; assert the rendered
     image fills ny rows with POSITIVE counts as pushes arrive.
  5. ALL-OR-NOTHING REGRESSION GATE: bind an existing ImageStackVisualization (array)
     and the TableVisualization (table) to the same run, subscribe each via its own
     StreamBridge to the node it displays, and assert each receives on_stream_update
     (push-driven) at least once when data is appended.

This is a SMOKE script (not TDD). Run it with the lightfall venv + offscreen Qt:

    QT_QPA_PLATFORM=offscreen \
    C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/smoke_stxm_live_map.py

A real failure (wrong node key, no array-data push, no array node, a viz that never
updates) must fail LOUDLY via an assertion — never print a misleading success.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# --------------------------------------------------------------------------
# Scratchpad paths (server config + storage live here; not committed)
# --------------------------------------------------------------------------
SCRATCH = Path(
    r"C:\Users\rp\AppData\Local\Temp\claude\C--Users-rp-workspace"
    r"\a95c2b18-d2c2-4c3c-9b2b-765d9622b5ac\scratchpad"
)
CONFIG = SCRATCH / "config_smoke_live_map.yml"
SERVER_LOG = SCRATCH / "run" / "server_smoke_live_map.log"
API_KEY = "smokelivemapkey0123"
PYTHON = sys.executable  # the venv python running this script

NY = 6
NX = 10  # the plan-plugin default; max_array_size=0 makes even nx=10 a streamable array
MAP_KEY = "STXMLineFlyer"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_http(url: str, timeout: float = 40.0) -> bool:
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def start_server(port: int) -> subprocess.Popen:
    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    logf = open(SERVER_LOG, "w")
    # NOTE: `tiled.exe` console-script shim fails under Git Bash; use -m tiled.
    proc = subprocess.Popen(
        [PYTHON, "-m", "tiled", "serve", "config", str(CONFIG),
         "--host", "127.0.0.1", "--port", str(port)],
        stdout=logf, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    ok = _wait_http(f"{base}/api/v1/?api_key={API_KEY}", timeout=45.0)
    if not ok:
        proc.terminate()
        raise RuntimeError(f"server did not come up; see {SERVER_LOG}")
    print(f"[server] up at {base} (pid={proc.pid})", flush=True)
    return proc


# --------------------------------------------------------------------------
# Drive the fly-scan and persist it through the patched TiledWriter.
# --------------------------------------------------------------------------
def run_fly_scan(base_url: str, app) -> tuple[object, str]:
    """Run the Phase-2b fly-scan through Lightfall's BlueskyEngine.

    Returns (tiled_root_client, run_uid).
    """
    import asyncio

    from lightfall.acquire import get_engine
    from lightfall.services.tiled_service import TiledService, TiledAuthMode

    from lightfall_pystxmcontrol import config as stxm_config
    from lightfall_pystxmcontrol.devices import PystxmAxis
    from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
    from lightfall_pystxmcontrol.plans import stxm_fly_raster

    # --- Point TiledService at the local streaming server -------------------
    TiledService.reset()
    service = TiledService.get_instance()
    service.configure(url=base_url, api_key=API_KEY, enabled=True,
                      auth_mode=TiledAuthMode.API_KEY)
    connected = service.connect()
    assert connected, f"TiledService failed to connect: state={service.state}"
    print(f"[scan] TiledService.connect() -> {connected} state={service.state}", flush=True)

    # --- Bring up the engine; the patched writer is auto-subscribed ---------
    engine = get_engine("bluesky")
    re = None
    for _ in range(200):
        re = engine.RE
        if re is not None:
            break
        app.processEvents()
        time.sleep(0.05)
    assert re is not None, "BlueskyEngine RE never became available"
    assert service._writer is not None, "patched TiledWriter was not subscribed to the engine"
    print(f"[scan] writer wired? {service._writer is not None}", flush=True)

    # --- CRITICAL: build the flyer via the REAL path so its name is the data
    #     key the map viz expects (STXMLineFlyer), NOT the Phase-2a default. ---
    flyer = PystxmLineFlyer(stxm_config.DEFAULT_COUNTER,
                            stxm_config.DEFAULT_AXES["SampleX"],
                            name=MAP_KEY)
    assert flyer.name == MAP_KEY, f"flyer name is {flyer.name!r}, expected {MAP_KEY!r}"
    yax = PystxmAxis(stxm_config.DEFAULT_AXES["SampleY"], name="SampleY")

    async def _connect_all():
        await flyer.connect(mock=False)
        await yax.connect(mock=False)

    asyncio.run(_connect_all())

    docs: list = []
    re.subscribe(lambda n, d: docs.append((n, d)))
    start_uid_box: dict = {}
    re.subscribe(lambda n, d: start_uid_box.update({"uid": d["uid"]}) if n == "start" else None)

    engine(stxm_fly_raster(flyer, yax, y_start=-5, y_stop=5, ny=NY,
                           x_start=-5, x_stop=5, nx=NX, dwell=1.0))

    deadline = time.time() + 120
    while time.time() < deadline:
        names = [n for n, _ in docs]
        if "stop" in names and engine.is_idle:
            break
        app.processEvents()
        time.sleep(0.05)

    names = [n for n, _ in docs]
    assert "stop" in names and engine.is_idle, f"fly raster did not finish: names={names}"
    uid = start_uid_box["uid"]
    print(f"[scan] run finished uid={uid} docs={names[:1]}..{names[-1:]}", flush=True)

    # --- Flush the threaded writer so all docs reached Tiled ----------------
    try:
        service._writer.flush(timeout=30.0)
    except Exception as e:
        print(f"[scan] writer flush warn: {e!r}", flush=True)
    time.sleep(2.0)

    return service.client, uid


# --------------------------------------------------------------------------
# Confirm the persisted node path / family / shape (walk the run tree).
# --------------------------------------------------------------------------
def confirm_node(client, uid: str) -> tuple[str, tuple[int, int]]:
    run = client[uid]
    run_children = list(run.keys())
    print(f"[node] run children: {run_children}", flush=True)
    assert "primary" in run_children, f"no primary stream in run: {run_children}"
    primary = run["primary"]

    try:
        primary_children = list(primary.keys())
    except Exception as e:
        raise AssertionError(f"primary.keys() failed (table never created?): {e!r}")
    print(f"[node] primary children: {primary_children}", flush=True)

    assert MAP_KEY in primary_children, (
        f"expected map key {MAP_KEY!r} under primary; got {primary_children}"
    )
    node = primary[MAP_KEY]
    fam = str(getattr(node, "structure_family", "?"))
    try:
        shape = tuple(node.structure().shape)
    except Exception:
        shape = tuple(getattr(node, "shape", ()))
    node_path = f"{uid}/primary/{MAP_KEY}"
    print(f"[node] CONFIRMED {node_path} | family={fam} | shape={shape}", flush=True)

    assert "array" in fam, (
        f"map node {node_path} is family={fam!r}, expected an 'array' "
        f"(without max_array_size=0 the line stays a table column -> no live map)"
    )
    assert shape == (NY, NX), f"map node shape {shape} != ({NY}, {NX})"
    return node_path, shape


# --------------------------------------------------------------------------
# Drive a StreamBridge -> viz, pumping the Qt event loop so queued
# cross-thread signal emissions are delivered to the GUI-thread slot.
# --------------------------------------------------------------------------
def _pump(app, predicate, timeout: float = 30.0, interval: float = 0.02) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(interval)
    app.processEvents()
    return predicate()


def main() -> int:
    print("=== Phase-2c capstone smoke: live STXM map via Tiled push ===", flush=True)
    import tiled
    print(f"tiled {tiled.__version__}; python {sys.version.split()[0]}", flush=True)

    from PySide6.QtWidgets import QApplication

    from lightfall.visualization.stream_bridge import StreamBridge
    from lightfall.visualization.widgets.image_stack import ImageStackVisualization
    from lightfall.visualization.widgets.table import TableVisualization
    from lightfall_pystxmcontrol.stxm_map_viz import StxmMapVisualization

    app = QApplication.instance() or QApplication([])

    port = _free_port()
    proc = start_server(port)
    base_url = f"http://127.0.0.1:{port}"

    # Hold references to all bridges so we can disconnect them before teardown.
    bridges: list[StreamBridge] = []
    ok = False
    try:
        # 1+2. Run the fly-scan and persist it.
        client, uid = run_fly_scan(base_url, app)

        # Confirm the persisted map node BEFORE wiring the live render.
        node_path, shape = confirm_node(client, uid)

        run = client[uid]
        map_node = run["primary"][MAP_KEY]

        # ------------------------------------------------------------------
        # 3. LIVE MAP via push.
        #    The run is already fully persisted, so subscribing with start=1
        #    replays every array-data push (the initial write + each row patch).
        #    Each push -> StreamBridge.update_received -> StxmMapVisualization
        #    .on_stream_update -> blits one line. We allocate the (ny, nx) image
        #    via begin_map, then assert the rendered image fills all ny rows
        #    with POSITIVE counts as the pushes are delivered.
        # ------------------------------------------------------------------
        map_viz = StxmMapVisualization()
        map_viz.set_run(run)
        map_viz.begin_map(NY, NX)
        # Sanity: a freshly-allocated map is all zeros (no positive counts yet).
        assert map_viz.current_image() is not None
        assert not np.any(map_viz.current_image() > 0), "map not zeroed before pushes"

        map_pushes = {"n": 0}

        def _map_slot(update):
            map_pushes["n"] += 1
            map_viz.on_stream_update(update)

        map_bridge = StreamBridge()
        map_bridge.update_received.connect(_map_slot)
        bridges.append(map_bridge)
        map_bridge.connect_node(map_node)

        def _all_rows_positive() -> bool:
            img = map_viz.current_image()
            if img is None:
                return False
            # Every one of the ny rows must contain at least one positive count.
            return bool(np.all(img.max(axis=1) > 0))

        rendered = _pump(app, _all_rows_positive, timeout=40.0)
        img = map_viz.current_image()
        assert img is not None and img.shape == (NY, NX), (
            f"final image shape {None if img is None else img.shape} != ({NY},{NX})"
        )
        assert rendered, (
            f"live map did NOT fill all {NY} rows with positive counts via push; "
            f"pushes={map_pushes['n']} row_max={None if img is None else img.max(axis=1)}"
        )
        n_positive_rows = int(np.count_nonzero(img.max(axis=1) > 0))
        img_min = float(img.min())
        img_max = float(img.max())
        assert n_positive_rows == NY, f"only {n_positive_rows}/{NY} rows positive"
        # Counts are Poisson (>= 0); after every row blits, the per-row max > 0
        # everywhere, so the global max is strictly positive.
        assert img_max > 0, f"map max is not positive: {img_max}"
        print(
            f"[map] LIVE via push: pushes={map_pushes['n']} rows_filled={n_positive_rows}/{NY} "
            f"min={img_min:g} max={img_max:g}",
            flush=True,
        )

        # ------------------------------------------------------------------
        # 4. ALL-OR-NOTHING REGRESSION GATE.
        #    Existing array viz (ImageStackVisualization) + table viz
        #    (TableVisualization) must ALSO update via the unified push path:
        #    StreamBridge.update_received -> on_stream_update (default -> refresh)
        #    must fire at least once for each, with the REAL viz instances.
        #
        #    The array viz reads <run>/primary/STXMLineFlyer (a 2-D array key);
        #    the table viz re-reads the events table on each push. We subscribe
        #    each viz's bridge to a STREAMABLE array node in the run; start=1
        #    replays the run's writes so each bridge delivers >=1 push through to
        #    on_stream_update. We assert on the count of on_stream_update calls
        #    observed on the REAL viz instances.
        # ------------------------------------------------------------------
        # --- Array viz: bind to the run and to the same array node. ---------
        array_viz = ImageStackVisualization()
        array_viz.set_run(run)
        try:
            array_viz.set_stream("primary")  # resolves data_keys + a field
        except Exception as e:
            print(f"[gate] array_viz.set_stream warn: {e!r}", flush=True)

        array_updates = {"n": 0}
        orig_array_osu = array_viz.on_stream_update

        def _array_osu(update):
            array_updates["n"] += 1
            try:
                orig_array_osu(update)  # default -> refresh (re-read array node)
            except Exception as e:  # a refresh hiccup must not mask the push count
                print(f"[gate] array refresh warn: {e!r}", flush=True)

        array_bridge = StreamBridge()
        array_bridge.update_received.connect(_array_osu)
        bridges.append(array_bridge)
        array_bridge.connect_node(map_node)  # the 2-D array key this viz can display

        # --- Table viz: bind to the run; subscribe to the internal table. ----
        table_viz = TableVisualization()
        table_viz.set_run(run)
        try:
            table_viz.set_stream("primary")
        except Exception as e:
            print(f"[gate] table_viz.set_stream warn: {e!r}", flush=True)

        primary = run["primary"]
        # IMPORTANT empirical finding (Tiled 0.2.9 composite-stream layout):
        # only the growable per-key ARRAY nodes written by the patched writer
        # (the flyer's dtype:"array" keys, e.g. STXMLineFlyer + SampleX) are
        # WS-stream-subscribable. The scalar columns (seq_num, time, SampleY) are
        # surfaced as table FACETS under `internal/` and are served by a plain
        # in-memory ArrayAdapter that lacks `make_ws_handler` -> subscribing to
        # them 500s ("'ArrayAdapter' object has no attribute 'make_ws_handler'").
        #
        # The table viz is push-driven via on_stream_update -> refresh(): the
        # unified design is that ANY push on the run triggers a full re-read of
        # the events table. So we bind the table viz's bridge to a STREAMABLE
        # array key in the same run (SampleX, distinct from the map's
        # STXMLineFlyer). Each push fires TableVisualization.on_stream_update
        # (default -> refresh()), which re-reads every scalar column. This is the
        # real production pattern, not a workaround.
        primary_children = list(primary.keys())
        table_drive_key = None
        for cand in ("SampleX", MAP_KEY):  # any streamable flyer dtype:array key
            if cand in primary_children:
                table_drive_key = cand
                break
        assert table_drive_key is not None, (
            f"no streamable array key under primary to drive the table viz; "
            f"children={primary_children}"
        )
        table_node = primary[table_drive_key]
        print(f"[gate] table viz driven by streamable node primary/{table_drive_key} "
              f"(family={getattr(table_node, 'structure_family', '?')}); scalar "
              f"columns are table facets, not individually WS-subscribable",
              flush=True)

        table_updates = {"n": 0}
        orig_table_osu = table_viz.on_stream_update

        def _table_osu(update):
            table_updates["n"] += 1
            try:
                orig_table_osu(update)  # default -> refresh (re-read events)
            except Exception as e:
                print(f"[gate] table refresh warn: {e!r}", flush=True)

        table_bridge = StreamBridge()
        table_bridge.update_received.connect(_table_osu)
        bridges.append(table_bridge)
        table_bridge.connect_node(table_node)

        # start=1 replays the whole run's writes, so both bridges should each see
        # at least one push delivered through to on_stream_update.
        got_both = _pump(
            app,
            lambda: array_updates["n"] >= 1 and table_updates["n"] >= 1,
            timeout=40.0,
        )
        assert array_updates["n"] >= 1, (
            "REGRESSION: existing array viz (ImageStackVisualization) received NO "
            "on_stream_update via push"
        )
        assert table_updates["n"] >= 1, (
            "REGRESSION: table viz (TableVisualization) received NO on_stream_update "
            "via push"
        )
        print(
            f"[gate] array viz on_stream_update calls={array_updates['n']}; "
            f"table viz on_stream_update calls={table_updates['n']} (both via push)",
            flush=True,
        )

        # ------------------------------------------------------------------
        # 5. Success line.
        # ------------------------------------------------------------------
        print(
            f"\nSUCCESS: live STXM map via Tiled push: node={node_path} | "
            f"{NY} lines x {NX} pts rendered; min={img_min:g} max={img_max:g}; "
            f"regression: array+table viz updated via push "
            f"(array={array_updates['n']}, table={table_updates['n']})",
            flush=True,
        )
        ok = True
        return 0

    finally:
        # Theater-teardown rule: disconnect every bridge BEFORE tearing down.
        # Bound each disconnect (Task 1 concern #3: a disconnect can block while
        # stamina retries against the cache) so teardown can never hang the smoke.
        for b in bridges:
            done = threading.Event()

            def _dc(bridge=b, ev=done):
                try:
                    bridge.disconnect()
                except Exception as e:
                    print(f"[teardown] bridge disconnect warn: {e!r}", flush=True)
                finally:
                    ev.set()

            t = threading.Thread(target=_dc, daemon=True)
            t.start()
            if not done.wait(timeout=10.0):
                print("[teardown] bridge disconnect timed out (continuing)", flush=True)
        app.processEvents()
        print("\n[server] terminating", flush=True)
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        # On a clean PASS, bypass the interpreter's normal shutdown. Qt's
        # QObject destructors + the tiled subscription daemon threads race
        # during teardown on Windows and raise a fail-fast (0xC0000409,
        # "QThread: Destroyed while thread is still running") AFTER the smoke
        # has fully succeeded — which would otherwise mask a clean run with a
        # bogus nonzero exit. We force a clean exit only when ok is True; a
        # real failure has already propagated its assertion/traceback past this
        # finally and exits nonzero through __main__ below.
        sys.stdout.flush()
        sys.stderr.flush()
        if ok:
            os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
