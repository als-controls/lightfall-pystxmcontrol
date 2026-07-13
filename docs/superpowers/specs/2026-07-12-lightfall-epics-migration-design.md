# Lightfall EPICS Migration (spec #3) — Design

**Date:** 2026-07-12
**Status:** Approved design (Ron), pending implementation plan
**Scope:** Spec #3 of the pystxmcontrol program. lightfall-pystxmcontrol migrates its device layer from in-process pystxmcontrol driver wrappers to EPICS clients of the spec-#2 caproto IOC layer. Plans, viz, Tiled paths, and the run-layout contract are unchanged.

## 1. Context

Spec #2 (implemented 2026-07-12, branch `feature/caproto-iocs` in the als-controls fork worktree `_pystxmcontrol_iocs_wt`, local) wraps David's drivers as caproto IOCs: motor records with **.VAL put-completion = move done**, a FLY PVGroup (`ARM/GO/ABORT/STATE/ERROR`, `DATA:{daq}/POS/INDEX` with the write-then-increment contract, **GO put-completion = line done**), a DAQ group (**ACQUIRE put-completion = acquisition done**), and the `stxm-iocs` supervisor. This spec makes lightfall-pystxmcontrol a pure EPICS client of that surface.

## 2. Decisions (locked, Ron 2026-07-12)

1. **Classic ophyd throughout.** Axes = stock `ophyd.EpicsMotor` (no wrapper class). Counter = a small `ophyd.Device` of plain `EpicsSignal`s. Flyer = a standard ophyd `Device` with `EpicsSignal`s driving the FLY PVGroup — no async client (the IOC's put-completion semantics make client-side async unnecessary).
2. **Transport:** `OPHYD_CONTROL_LAYER=caproto` (proven by spec #2's e2e; pyepics not installed). Set defensively (`os.environ.setdefault` + `ophyd.set_cl` fallback) at plugin import, before any ophyd import. **`netifaces` is required** — it is an optional caproto dep but things break without it (installed in the lightfall venv 2026-07-12).
3. **EPICS-only; sim = stxm-iocs.** The in-process sim wrappers (`config.make_sim_motor/make_sim_counter`, the old `PystxmAxis`/`PystxmCounter` and the in-process flyer internals) are deleted. Sim mode = run the spec-#2 supervisor with sim-backed IOCs; the plugin talks CA either way. One code path.
4. **Contract v1 untouched.** The new flyer emits the identical one-event-per-line `describe_collect`/`collect` output (`X_DATA_KEY="SampleX"` positions array, `Y_DATA_KEY="SampleY"` scalar, counts under the flyer name), so `contract.py`, `plans.py`, viz plugins, and Tiled layout are unchanged.

## 3. Device layer

### 3.1 Axes — `ophyd.EpicsMotor`

Happi entries carry `device_class: "ophyd.EpicsMotor"` and `prefix` = the IOC motor-record PV (e.g. `STXMSIM:E712:SampleX`). No plugin code. `category="motor"` metadata preserved so `plan_plugin`'s `DeviceFilter(category="motor")` (y_axis, energy_axis w/ `name_pattern="energy"`) keeps matching.

### 3.2 Counter — `StxmCounter(ophyd.Device)`

`EpicsSignal` components against the spec-#2 DAQ group: `dwell` (`:DWELL`), `acquire` (`:ACQUIRE`, `put_complete=True` → `trigger()` returns a status that completes when the acquisition finishes), `counts` (`:COUNTS`, hinted read field), `rate` (`:RATE`, read-only). `read()`/`describe()` come from stock ophyd.

### 3.3 Flyer — `StxmLineFlyer(ophyd.Device)`

Signals: `start/stop_pos/npoints/dwell/axis/arm/go/abort/state/error/index/pos/data_<daq>` mapped to the FLY PVGroup.

- `prepare(*, y, x_start, x_stop, nx, dwell)` — writes the config PVs, puts `ARM` (wait=True), then verifies `STATE == ARMED`; on failure raises with the `:ERROR` string. Stashes `y` for collect.
- `kickoff()` — launches the `GO` put (`put_complete=True`) on a background thread; returns a Status completed when `STATE` reaches FLYING (or the put finishes first, for very short lines).
- `complete()` — Status tied to the GO put finishing; verifies `INDEX` incremented by exactly one for the row and `STATE` returned to ARMED (ERROR → raise with `:ERROR` text).
- `collect()` — reads `FLY:DATA:{daq}` and `FLY:POS` (safe: INDEX ordering contract guarantees freshness once the GO put completed) and yields the same event dict as today. `describe_collect()` unchanged in shape.
- `FLYER_DEVICE_CLASS` in `plan_plugin.py` derives from the class object, so the plan DeviceFilter follows the new class automatically; the happi entry's `device_class` string is regenerated to match.

Enum writes (`AXIS`, DAQ `MODE`) use integer indices or `data_type=STRING` — caproto's threading client cannot write bare native enum strings (spec-#2 verified gotcha). ophyd EpicsSignal enum handling to be pinned during implementation; fall back to integer puts.

## 4. Config and happi generation

- The plugin ships `config/sim_motor.json` + `config/sim_daq.json` in David's format: `SampleX`/`SampleY` as sim `E712Motor` axes on one sim `E712Controller`, an `Energy` sim axis (matches `name_pattern="energy"`), and the default keysight counter. The MCL-dependent shipped config is deliberately avoided (its vendor `.so` cannot load on Windows; the sim fleet's derived SampleX/SampleY crash-loop there).
- `scripts/build_pystxm_happi_db.py` is rewritten to call **spec #2's `pystxmcontrol.iocs.config.load_fleet`** on those JSONs and emit happi entries whose `prefix` comes from `fleet.motor_pv` — PV naming cannot drift between the IOCs and the plugin. `--station` flag, default `SIM`. Counter and flyer prefixes come from the same fleet model (DAQ prefix, `STXM{station}:{E712 label}:FLY`).
- `pystxm_happi.json` is regenerated and committed; `plugin.py` unchanged.

## 5. Sim / dev workflow

```
stxm-iocs --station SIM \
  --motor-config <plugin>/config/sim_motor.json \
  --daq-config   <plugin>/config/sim_daq.json
```
then start Lightfall; the backend connects over CA (per-IOC ports: source the supervisor's printed `EPICS_CA_ADDR_LIST` / addr-list file). README and scan-panel docs updated accordingly.

## 6. Testing

- **Unit:** flyer state machine against a locally spawned FLY IOC (per-test random CA ports, same fixture pattern as spec #2's suite): prepare→ARMED, ARM validation failure surfaces `:ERROR`, kickoff/complete/collect happy path, ERROR state raises.
- **e2e:** spawn the sim fleet from the plugin's sim JSONs, build the happi DB, run `stxm_fly_raster` (and an abbreviated `stxm_energy_stack`) under a bluesky `RunEngine`, and assert the emitted documents pass `contract.validate_run_documents`. The existing golden-fixture test continues to guard the contract.
- **Dependency on the unmerged IOC layer:** tests import/spawn `pystxmcontrol.iocs` from the fork worktree via env var `PYSTXMCONTROL_IOCS_SRC` (default: this repo's `_pystxmcontrol_iocs_wt`). Tests FAIL loudly if it is missing — no silent skips. When spec #2 merges/publishes, repoint the `hardware` extra and drop the env var.
- Env facts that bind: `netifaces` installed; `EPICS_CA_ADDR_LIST`/`EPICS_CA_SERVER_PORT` client vars + `EPICS_CAS_SERVER_PORT` server var per test; `OPHYD_CONTROL_LAYER=caproto` before ophyd import.

## 7. Non-goals

Scan panel/viz changes beyond doc updates; spec #1 remote contract; hardware (7011) happi DB and deployment config — follow-up when the IOCs meet hardware; pyepics support; changes to the spec-#2 IOC layer (bugs found there are fixed on its branch, documented).
