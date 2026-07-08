"""Phase-A capstone smoke: an energy-stack run travels end-to-end.

This is the end-to-end proof of the option-5 vertical slice:

  1. Launch a local streaming Tiled 0.2.9 server. The server config is written
     by THIS script into the session scratchpad (sqlite catalog + writable
     storage + streaming_cache: {uri: memory}); nothing external is referenced.
  2. Point Lightfall's TiledService at it; connect() auto-subscribes the patched
     ThreadedTiledWriter (max_array_size=0) to the engine.
  3. Drive the ``stxm_energy_stack`` plan (NE energies x NY lines x NX points)
     through Lightfall's BlueskyEngine. The flyer's default name is the map key
     (STXMLineFlyer == the contract data_field).
  4. CONTRACT: validate the whole (name, doc) stream with
     ``contract.validate_run_documents`` -> must be empty. Confirm the persisted
     rows node is the growing (NE*NY, NX) 2-D array at <run>/primary/STXMLineFlyer.
  5. LIVE STACK: bind a StxmStackVisualization to the run, subscribe a
     StreamBridge to the array node (NEVER a scalar column facet), and assert the
     (NE, NY, NX) cube fills LIVE via push (start=1 replays every write/patch)
     with positive counts. The cube is re-armed to all-NaN before subscribing so
     a broken push path fails LOUDLY (a timeout) instead of passing on the
     refresh that set_stream() performs against the already-persisted node.

SMOKE script (not TDD). Run it with the lightfall venv + offscreen Qt:

    QT_QPA_PLATFORM=offscreen PYTHONPATH=src \
    C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/smoke_energy_stack.py

Every failure path asserts LOUDLY; a real failure never prints SUCCESS.
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
# Scratchpad paths (server config + storage live here; not committed). This
# script WRITES its own config -- it references no external scratch file.
# --------------------------------------------------------------------------
SCRATCH = Path(
    r"C:\Users\rp\AppData\Local\Temp\claude\C--Users-rp-workspace"
    r"\45c8e89c-81c2-4e8b-9cf2-9d5808b1e344\scratchpad"
)
CONFIG = SCRATCH / "config_energy_stack.yml"
CATALOG_DB = SCRATCH / "energy_stack_catalog.db"
STORAGE_DIR = SCRATCH / "energy_stack_storage"
TABLES_DB = SCRATCH / "energy_stack_tables.db"
SERVER_LOG = SCRATCH / "run" / "server_energy_stack.log"
API_KEY = "energystackkey0123"
PYTHON = sys.executable  # the venv python running this script

# Energy-stack dimensions (spec §3.2): NE energies, each a (NY, NX) fly image.
NE, NY, NX = 2, 3, 4
ENERGIES = [500.0, 510.0]
MAP_KEY = "STXMLineFlyer"  # flyer default name == contract data_field


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_http(url: str, timeout: float = 45.0) -> bool:
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


def write_config() -> None:
    """Write a self-sufficient streaming Tiled server config into scratchpad.

    - sqlite catalog with ``init_if_not_exists`` (no separate `tiled catalog
      init` needed);
    - dual writable_storage: a ``file://`` tree for zarr arrays AND a
      ``sqlite:///`` tree for the appendable events table (three slashes; four
      would mangle the Windows drive path);
    - ``streaming_cache: {uri: memory}`` -- the hard dependency that makes
      array patches deliver as WS ``array-data`` pushes (Phase-2c proven form).
    """
    SCRATCH.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(
        "authentication:\n"
        "  allow_anonymous_access: true\n"
        f"  single_user_api_key: \"{API_KEY}\"\n"
        "catalog:\n"
        f"  uri: \"sqlite+aiosqlite:///{CATALOG_DB.as_posix()}\"\n"
        "  writable_storage:\n"
        f"    - \"file://localhost/{STORAGE_DIR.as_posix()}\"\n"
        f"    - \"sqlite:///{TABLES_DB.as_posix()}\"\n"
        "  init_if_not_exists: true\n"
        "streaming_cache:\n"
        "  uri: \"memory\"\n"
    )


def start_server(port: int) -> subprocess.Popen:
    write_config()
    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    logf = open(SERVER_LOG, "w")
    # NOTE: `tiled.exe` console-script shim fails under Git Bash; use -m tiled.
    # Belt-and-suspenders: also set TILED_STREAMING_CACHE_URI in the server env
    # (the config `streaming_cache` key is the proven mechanism; this is harmless
    # reinforcement in case a build honours only the env var).
    env = dict(os.environ)
    env.setdefault("TILED_STREAMING_CACHE_URI", "memory://")
    proc = subprocess.Popen(
        [PYTHON, "-m", "tiled", "serve", "config", str(CONFIG),
         "--host", "127.0.0.1", "--port", str(port)],
        stdout=logf, stderr=subprocess.STDOUT, env=env,
    )
    base = f"http://127.0.0.1:{port}"
    ok = _wait_http(f"{base}/api/v1/?api_key={API_KEY}", timeout=45.0)
    if not ok:
        proc.terminate()
        raise RuntimeError(f"server did not come up; see {SERVER_LOG}")
    print(f"[server] up at {base} (pid={proc.pid})", flush=True)
    return proc


# --------------------------------------------------------------------------
# Drive the energy stack and persist it through the patched TiledWriter.
# --------------------------------------------------------------------------
def run_energy_stack(base_url: str, app) -> tuple[object, str, list]:
    """Run ``stxm_energy_stack`` through Lightfall's BlueskyEngine.

    Returns (tiled_root_client, run_uid, docs) where ``docs`` is the captured
    (name, doc) stream for the contract validator.
    """
    import asyncio

    from lightfall.acquire import get_engine
    from lightfall.services.tiled_service import TiledService, TiledAuthMode

    from lightfall_pystxmcontrol import config as stxm_config
    from lightfall_pystxmcontrol.devices import PystxmAxis
    from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
    from lightfall_pystxmcontrol.plans import stxm_energy_stack

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

    # --- Build the three devices. The flyer's DEFAULT name is the map key
    #     (== the contract data_field). ---------------------------------------
    flyer = PystxmLineFlyer(stxm_config.DEFAULT_COUNTER,
                            stxm_config.DEFAULT_AXES["SampleX"])
    assert flyer.name == MAP_KEY, f"flyer name is {flyer.name!r}, expected {MAP_KEY!r}"
    yax = PystxmAxis(stxm_config.DEFAULT_AXES["SampleY"], name="SampleY")
    en = PystxmAxis(stxm_config.DEFAULT_AXES["energy"], name="energy")

    async def _connect_all():
        await flyer.connect(mock=False)
        await yax.connect(mock=False)
        await en.connect(mock=False)

    asyncio.run(_connect_all())

    docs: list = []
    re.subscribe(lambda n, d: docs.append((n, d)))
    start_uid_box: dict = {}
    re.subscribe(lambda n, d: start_uid_box.update({"uid": d["uid"]}) if n == "start" else None)

    engine(stxm_energy_stack(flyer, en, yax, energies=ENERGIES,
                             y_start=-5, y_stop=5, ny=NY,
                             x_start=-5, x_stop=5, nx=NX, dwell_ms=1.0))

    deadline = time.time() + 120
    while time.time() < deadline:
        names = [n for n, _ in docs]
        if "stop" in names and engine.is_idle:
            break
        app.processEvents()
        time.sleep(0.05)

    names = [n for n, _ in docs]
    assert "stop" in names and engine.is_idle, f"energy stack did not finish: names={names}"
    uid = start_uid_box["uid"]
    print(f"[scan] run finished uid={uid} docs={names[:1]}..{names[-1:]} n={len(docs)}", flush=True)

    # --- Flush the threaded writer so all docs reached Tiled ----------------
    try:
        service._writer.flush(timeout=30.0)
    except Exception as e:
        print(f"[scan] writer flush warn: {e!r}", flush=True)
    time.sleep(2.0)

    return service.client, uid, docs


# --------------------------------------------------------------------------
# Confirm the persisted rows node: family=array, shape=(NE*NY, NX).
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
        f"expected rows key {MAP_KEY!r} under primary; got {primary_children}"
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
        f"rows node {node_path} is family={fam!r}, expected an 'array' "
        f"(without max_array_size=0 the line stays a table column -> no live stack)"
    )
    assert shape == (NE * NY, NX), f"rows node shape {shape} != ({NE * NY}, {NX})"
    return node_path, shape


# --------------------------------------------------------------------------
# Pump the Qt event loop so queued cross-thread signal emissions are delivered.
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
    print("=== Phase-A capstone smoke: energy stack e2e via Tiled push ===", flush=True)
    import tiled
    print(f"tiled {tiled.__version__}; python {sys.version.split()[0]}", flush=True)

    from PySide6.QtWidgets import QApplication

    from lightfall.visualization.stream_bridge import StreamBridge

    from lightfall_pystxmcontrol import contract
    from lightfall_pystxmcontrol.stxm_stack_viz import StxmStackVisualization

    app = QApplication.instance() or QApplication([])

    port = _free_port()
    proc = start_server(port)
    base_url = f"http://127.0.0.1:{port}"

    bridges: list[StreamBridge] = []
    ok = False
    try:
        # 1+2+3. Run the energy stack and persist it.
        client, uid, docs = run_energy_stack(base_url, app)

        # 4a. CONTRACT: the whole document stream must validate clean.
        errors = contract.validate_run_documents(docs)
        assert errors == [], f"contract violations: {errors}"
        print(f"[contract] validate_run_documents -> [] ({len(docs)} docs valid)", flush=True)

        # 4b. Confirm the persisted rows node BEFORE wiring the live render.
        node_path, shape = confirm_node(client, uid)

        run = client[uid]

        # ------------------------------------------------------------------
        # 5. LIVE STACK via push.
        #    set_run reads the start-doc `stxm` block; set_stream("primary")
        #    also refresh()es the cube from the already-persisted node. That
        #    pre-fill would make the live assertion trivially pass, so we
        #    RE-ARM the cube to all-NaN afterward: only genuine bridge pushes
        #    (start=1 replays every write/patch) delivered to on_stream_update
        #    can refill it. A broken push path then fails LOUDLY (timeout),
        #    mirroring the map smoke's begin_map zeroing.
        # ------------------------------------------------------------------
        stack_viz = StxmStackVisualization()
        stack_viz.set_run(run)
        stack_viz.set_stream("primary")  # allocates + refreshes (NE, NY, NX) cube

        stxm = stack_viz._stxm
        assert stxm is not None, "stack viz has no stxm block (start doc lost the contract md)"
        cube_shape = tuple(stxm["shape"])
        assert cube_shape == (NE, NY, NX), f"start-doc shape {cube_shape} != ({NE}, {NY}, {NX})"

        # Re-arm: replace with a fresh all-NaN cube (contract allocation from an
        # empty rows array). Now the cube can ONLY fill via delivered pushes.
        stack_viz._cube = contract.cube_from_rows(np.empty((0, NX)), cube_shape)
        assert stack_viz.current_cube() is not None
        assert np.isnan(stack_viz.current_cube()).all(), "re-armed cube must be all-NaN before pushes"

        pushes = {"array_data": 0, "total": 0}
        orig_osu = stack_viz.on_stream_update

        def _slot(update):
            pushes["total"] += 1
            if getattr(update, "type", None) == "array-data":
                pushes["array_data"] += 1
            orig_osu(update)

        bridge = StreamBridge()
        bridge.update_received.connect(_slot)
        bridges.append(bridge)
        bridge.connect_node(run["primary"][MAP_KEY])  # array node -- never a column facet

        def _cube_full() -> bool:
            cube = stack_viz.current_cube()
            return cube is not None and not np.isnan(cube).any() and (np.nanmax(cube) > 0)

        filled = _pump(app, _cube_full, timeout=40.0)
        cube = stack_viz.current_cube()
        assert filled, (
            f"stack cube did not fill via push; pushes={pushes} "
            f"cube_nan_lines={None if cube is None else int(np.isnan(cube).any(axis=2).sum())}"
        )
        assert pushes["array_data"] > 0, (
            f"no array-data pushes delivered through the bridge: pushes={pushes}"
        )
        assert cube is not None and cube.shape == (NE, NY, NX), (
            f"final cube shape {None if cube is None else cube.shape} != ({NE}, {NY}, {NX})"
        )
        assert not np.isnan(cube).any(), "cube still has unfilled (NaN) lines after push"
        cmin = float(np.nanmin(cube))
        cmax = float(np.nanmax(cube))
        assert cmax > 0, f"cube max is not positive: {cmax}"
        print(
            f"[stack] LIVE via push: array-data pushes={pushes['array_data']} "
            f"(total={pushes['total']}); cube filled {cube.shape} "
            f"min={cmin:g} max={cmax:g}",
            flush=True,
        )

        # ------------------------------------------------------------------
        # Success line.
        # ------------------------------------------------------------------
        print(
            f"\nSUCCESS: energy stack {cube.shape} filled live; "
            f"min={cmin:g} max={cmax:g}; contract valid",
            flush=True,
        )
        ok = True
        return 0

    finally:
        # Theater-teardown rule: disconnect every bridge BEFORE teardown, each
        # bounded so a stamina-retry disconnect can never hang the smoke.
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
        # On a clean PASS, bypass normal interpreter shutdown: Qt QObject
        # destructors + the tiled subscription daemon threads race on Windows
        # teardown and can raise a fail-fast (0xC0000409) AFTER a fully
        # successful smoke, masking a green run with a bogus nonzero exit. A
        # real failure has already propagated its assertion/traceback past this
        # finally and exits nonzero through __main__ below.
        sys.stdout.flush()
        sys.stderr.flush()
        if ok:
            os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
