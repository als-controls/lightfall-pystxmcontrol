# EPICS migration follow-ups (post s3 whole-branch review)

- Flyer `Preparable` protocol: run `prepare()` as a `Status` via `bps.prepare` —
  blocking CA puts currently execute on the RE thread, degrading pause/abort
  responsiveness. Do before hardware.
- Bounded `complete()` timeout derived from `nx * dwell`, plus a
  STATE/ERROR-subscription failure path — fleet death mid-scan currently hangs
  the scan indefinitely.
- `_DAQ_KEY` hardcode in `flyer.py` -> promote to a happi kwarg.
- `stxm_fleet` fixture: replace the flat 3s startup sleep with a sentinel-PV
  connect poll (one flake seen where 3s wasn't enough).
- Repo-relative default for `PYSTXMCONTROL_IOCS_SRC` instead of the hardcoded
  absolute path in `tests/conftest.py`.
- caproto `Context` cleanup in tests (no explicit teardown currently).
- `complete()`-after-failed-`prepare()` message wording pass.
- Hardware (7011) happi DB + station configs — not yet in this repo.
- Repoint the hardware extra when spec #2 (pystxmcontrol caproto IOCs) merges.
- Supervisor SIGTERM does not reap child processes on Windows — orphan sweep
  needed; observed during smoke testing.
