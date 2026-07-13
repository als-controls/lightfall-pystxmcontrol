# pystxmcontrol Remote GUI (spec #4) — Design

**Date:** 2026-07-13
**Status:** Approved design (Ron), pending implementation plan
**Scope:** Spec #4 of the pystxmcontrol program (the "GUI fork" stage; formerly spec #2 of the remote-client program, re-sequenced by the caproto pivot). David Shapiro's pystxmcontrol GUI becomes a thin remote client of Lightfall: control over the spec-#1 NATS contract, motor readbacks over direct CA, data over Tiled. The scan server and acquisition-time NeXus writers are dropped from the app path.

## 1. Context

- **Spec #1** (Remote Control API, merged to lightfall master): capability-channel NATS contract v1 — `commands.plan.*/queue.*/engine.*/device.*`, broadcast `runs.*`/`state.engine`, trust handshake delivering `session_token` + Tiled URL/token. Reference consumer: `lightfall/tests/integration/remote_client.py` (`LightfallRemoteClient`, raw nats-py, no lightfall imports) — the seed for this spec's client.
- **Spec #2/#3** (caproto IOCs; Lightfall EPICS migration, both done): devices are EPICS IOCs; Lightfall runs plans against them and writes to Tiled. The GUI can therefore read motor positions directly over CA like any EPICS client.
- **David's GUI** (fork `als-controls/pystxmcontrol`, branch `headless-install-fixes`): PySide6, ~33 files/~19k LOC under `pystxmcontrol/gui/`; single production seam — `controller/client.py` (`stxm_client`, ZMQ REQ 9999 + SUB 9998) consumed by `gui/controllers/main_controller.py` (plus `gui/legacy/mainwindow.py`, out of scope). Live data arrives as pickled monitor dicts (`motorPositions`, per-DAQ `image` dicts, `rawData` monitor traces, `"scan_complete"`).

## 2. Decisions (locked, Ron 2026-07-13)

1. **Hybrid device path.** Manual moves (`moveMotor`) go through the remote API (`commands.device.put`) so Lightfall's busy/reject arbitration applies; position readbacks come from **direct CA monitors** (caproto threading client) on the motor PVs — no NATS polling.
2. **Scope: scan control + live display.** Main window, motor panel, scan/energy/region definition, live image + monitor plots. Analysis widget / stack viewer / data browser ride along UNCHANGED (HDF5-file based); their Tiled conversion is a later spec ("we'll also do the analysis/browser, but not right now"). `gui/legacy/` is dropped from the fork app path.
3. **v1 scan modes: fly raster + energy stack**, mapped onto the `lightfall-pystxmcontrol` plans (`stxm_fly_raster`, `stxm_energy_stack`). Other modes (spiral, ptychography, point/focus scans) disabled in the UI, not removed.
4. **Contract addition (lightfall-side, additive):** `commands.device.info` reply gains a `pv` field (`DeviceInfo.prefix`) so the GUI can attach CA monitors. Non-breaking; contract_version stays 1; docs updated.

## 3. Architecture

### 3.1 `pystxmcontrol/remote/` (new leaf package in the fork)

- `client.py` — **`LightfallClient`**: productionized `LightfallRemoteClient` (verbatim handshake/call/subscribe semantics; raw `nats-py`; no lightfall imports) + `tiled.client` bootstrap from the handshake's URL/token. Pure asyncio, GUI-free, unit-testable headless.
- `qt_bridge.py` — **`RemoteBackend(QThread)`**: hosts the asyncio loop; exposes the Qt-signal surface `MainController` consumes (config-loaded, motor-positions, engine-state, scan-progress/image, scan-complete, errors). Thread-safe request submission (queue → loop), signals out.
- `ca_monitors.py` — **`MotorMonitorSet`**: caproto threading-client subscriptions on `<pv>.RBV`/`.MOVN` for the motors returned by `device.search`+`device.info(pv)`; emits coalesced `motorPositions` dicts at a bounded rate (~5 Hz) in the same shape `_handle_monitor_message` already consumes.
- `tiled_stream.py` — **`RunStreamer`**: on `runs.new`, opens the run via tiled.client and streams line events into per-DAQ image arrays (read-side patterns ported from the stxm map viz / stxm-live work: array or table nodes only, NEVER scalar column facets); emits image-update payloads shaped like the old monitor `image` dicts; emits scan-complete on `runs.complete`.
- `scan_mapping.py` — pure functions mapping David's scan-definition dict (rasterLine / energy stack shapes from `scanDef.py`/`energyDef.py`) to `{plan_name, params}` for `commands.plan.run`, including unit conventions (dwell in ms end-to-end). Table-driven, exhaustively unit-tested; unsupported modes raise a typed `UnsupportedScanMode`.

### 3.2 GUI refactor (bounded)

`MainController` keeps its structure and models. `stxm_client`/`ControlThread` usage is re-pointed at `RemoteBackend`:
- `get_config()` → assembled from `device.search` + `device.info` (motor list, PVs, categories) + `plan.list` (param metadata/limits for the scan panel) + client-side `remote.json`.
- `moveMotor` → `device.put` (wait=True; busy/limits errors surfaced in the status bar).
- `scan` → `scan_mapping` → `plan.run` (behavior "reject"; busy error → user message). `cancel` → `plan.abort`.
- Monitor pipeline: `MotorMonitorSet` + `RunStreamer` feed the existing `_handle_monitor_message`-shaped payloads where practical, so widget code changes stay minimal.
- Dropped from the app path: scan server usage, acquisition-time NeXus writing, CCD/rpi/ptycho monitors, `setGate`, `move_to_focus`/zone-plate server calls (deferred), motor-config editing via server (`changeMotorConfig` — config now lives with the IOC layer/Lightfall; UI hidden).
- The live in-memory `stxm` object (`utils.writeNX.stxm`) for the stack viewer stays, fed from `RunStreamer` rows.

### 3.3 Entry point + config

Console script **`stxmcontrol-remote`** = `pystxmcontrol.remote.app:main` (builds QApplication + MainWindowMVC with `RemoteBackend`). Config `remote.json` (packaged default + `--config` override): `{nats_url, prefix, app_name}`. Tiled URL/token arrive only via the trust handshake. `pyproject.toml` extra: `remote = ["nats-py", "tiled", "caproto", "netifaces"]`.

### 3.4 Lightfall-side change (small, separate commit in lightfall)

`RemoteControlService._device_info` adds `"pv": device_info.prefix` to the reply; `ipc-client-guide.md` updated; e2e assertion extended. Additive only.

## 4. Failure modes

- Handshake denied/timeout → blocking startup dialog with retry; GUI stays up in disconnected state.
- `plan.run`/`device.put` busy → non-modal status message; UI already locks controls on `state.engine != idle` (first line of defense per spec #1 §5.3).
- NATS drop → `RemoteBackend` reconnect loop with backoff; capability channel death (logout on the Lightfall side) → automatic re-handshake (precedent: xpcs_live session invalidation).
- Tiled stream failure mid-scan → live display freezes with a warning banner; the run itself is unaffected (display-only path).
- CA monitor disconnect → stale-readback indicator on the motor panel (grey-out), auto-resubscribe.

## 5. Testing

- **Unit:** `scan_mapping` table tests (both modes, unit conventions, unsupported-mode errors); `LightfallClient` against a stub NATS request/reply layer; `RunStreamer` against a recorded run structure (golden fixture from the spec-#3 e2e).
- **Contract:** the client's handshake + calls against a live local `RemoteControlService` (local nats-server), reusing spec #1's e2e harness patterns; includes the new `device.info.pv` field.
- **e2e (golden-run bar):** local NATS + sim IOC fleet (spec #2) + headless Lightfall engine with the lightfall-pystxmcontrol plugin + `RemoteBackend` (offscreen Qt): submit a fly raster through the full path, assert the live image assembled from Tiled matches the run's data, motor panel readbacks track a commanded move, busy rejection while a plan runs.
- Qt tests run with `QT_QPA_PLATFORM=offscreen`.

## 6. Non-goals (v1)

Analysis/browser/stack-viewer Tiled conversion (later spec); spiral/ptychography/point-scan modes; CCD/frame streams; device value streaming over NATS; single-operator leases; motor-config editing from the GUI; the old panel slim-down (lightfall-pystxmcontrol panels stay as-is until this ships); changes to David's server (`controller/server.py` untouched — coexistence preserved).
