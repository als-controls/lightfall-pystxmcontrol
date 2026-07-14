# pystxmcontrol Remote GUI (spec #4) — follow-ups

Recorded 2026-07-13 at end of the spec-#4 implementation (branch `feature/remote-gui`, local in `_pystxmcontrol_remote_wt`). None block the v1 deliverable; grouped by theme.

## Remote-GUI capability gaps (v1 scope cuts)
- **Multi-operator / mid-scan-join awareness.** `_on_external_scan_detected` (legacy ZMQ scan-state inference from incoming data) is disabled in backend mode because it raced the explicit run lifecycle. Consequence: if the GUI connects while a scan is already running, or another remote client starts a scan, this GUI does not reflect it. Proper fix: drive scan-state from the `runs.new` / `state.engine` broadcasts (already subscribed), not from image data.
- **Full-window remote rendering.** `mainwindow_mvc.py` has ~14 lazy `self.controller.client.*` reaches (daqConfig/scanConfig/main_config) guarded by `getattr` so construction/first-run works; a polished remote window should source those from the backend config payload instead of the (None) legacy client.
- **Scan modes.** Only fly raster + energy stack in v1; spiral / ptychography / point-scan / focus modes are rejected with `UnsupportedScanMode`. Adding them means new plans on the lightfall side + `scan_mapping` entries.
- **Analysis / browser / stack-viewer → Tiled.** Still read HDF5 files directly (ride along unchanged). Converting them to Tiled reads is its own later spec (deferred deliberately: "we'll also do the analysis/browser, but not right now").

## Lifecycle / robustness polish
- **RemoteBackend.shutdown() can block the GUI thread ~10s worst case** (`_wait_for_loop` 5s + `wait()` 5s) if the loop thread never starts. Fine for a rare quit path; consider running teardown off the GUI thread or showing a "closing…" indicator.
- **shutdown() does not `nc.drain()`** — the NATS connection is torn down by loop close rather than a clean drain. Harmless but abrupt.
- **`abort_scan` carries no run/item id** — forwards an empty `plan.abort`; fine for single-operator, but can't guard a stray abort after a run already completed.
- **RunStreamer** fires `on_image`/`on_progress` every poll tick (throttle if the Qt bridge finds it noisy); a network-stalled `stream.read()` can let one late callback fire after `stop()` (daemon thread, bounded by the 20s watchdog).
- **RunStreamer energy-stack display** shows only the current energy slice (v1 policy); slice navigation is future work.

## Test infra / housekeeping
- **`PYSTXMCONTROL_IOCS_SRC`** defaults to the local spec-#2 fork worktree (`_pystxmcontrol_iocs_wt`); repoint the `hardware`/`remote` extras and drop the env-var default once specs #2/#3 merge/publish.
- **Two-worktree `pystxmcontrol` package collision** handled test-only via `__path__` extension + `cwd=iocs_src` on spawned IOCs (conftest); retire when the layout consolidates.
- **`asyncio_mode = "auto"`** added to pyproject; only affects coroutine tests (David's legacy tests are sync) — watch for collection surprises if that changes.
- **scan_mapping dead default** (`else 1.0` dwell branch is unreachable) — cosmetic cleanup.

## Cross-repo / upstreaming
- **lightfall `device.info` +pv** rides on branch `feature/device-info-pv` (local); merges as part of the spec-#1 line. The remote GUI's contract/e2e tests require it live.
- **Upstream PR to David Shapiro** — the whole remote-client stack (fork `als-controls/pystxmcontrol`, branch `feature/remote-gui`) plus the spec-#2 caproto IOC layer and spec-#3 EPICS migration are Ron's to sequence and push; all branches are LOCAL pending his review.
