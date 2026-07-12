# pystxmcontrol caproto IOC Layer — Design

**Date:** 2026-07-12
**Status:** Approved design (Ron), pending implementation plan
**Scope:** New spec #2 of the pystxmcontrol program (re-sequenced — see §8). Wraps David Shapiro's pystxmcontrol device drivers as caproto EPICS IOCs so the devices become EPICS-enabled and Lightfall stops hosting hardware drivers in-process.

## 1. Context and motivation

Spec #1 (Remote Control API, merged to lightfall master 2026-07-12) assumed the beamline Lightfall instance hosts David's device drivers in-process via the lightfall-pystxmcontrol ophyd-async wrappers. Reconsidered: in-process hosting (a) puts hardware I/O in the GUI process with potential UI-performance impact, (b) pulls domain-unique driver dependencies into Lightfall, and (c) locks Lightfall into acting as the hardware server. Instead, each pystxmcontrol hardware controller is wrapped as a **caproto IOC**; Lightfall (and anything else: MEDM, caget, David's own stack) talks to the devices as standard EPICS PVs.

**Anticipated objection (David): "EPICS will hurt my scanning performance."** Answer, designed in from the start (§5): the hardware-timed inner loop runs inside the IOC process — the same driver code with the same process locality to hardware his scan server has today. EPICS is the control/reporting plane only; nothing per-point crosses the network. A benchmark task makes this claim falsifiable (§7).

## 2. Decisions (locked)

1. **Hybrid per driver:** fly-capable controllers (E712) get an IOC-side scan loop with a fly PVGroup; simple motors/shutters/DAQs get thin PV mirrors.
2. **v1 driver scope: all motor-controller families + core DAQs.** Detectors (fccd/cin/xspress3/areaDetector) are out — large-array frames over CA is the wrong transport (later: areaDetector/PVA path).
3. **Derived motors wrapped in caproto too** — David's calibration/coordination math (derivedEnergy, slit width/position, derived piezo combos, zone-plate focus) stays his code, exposed with the same motor face.
4. **Deployment: standalone supervisor in the repo** (`stxm-iocs`), reading David's existing `motor.json`/`daq.json`, one process per controller connection. No BCS-infra dependency in v1; CSM-plugin/iocular management is a named follow-up.
5. **Code home: leaf subpackage `pystxmcontrol.iocs`** in the `als-controls/pystxmcontrol` fork (guarded imports, upstreamable to David as one PR).
6. **PV surface: caproto mock motor record + custom fly/DAQ groups** (`record='motor'` fields `.VAL/.RBV/.DMOV/.MOVN/.STOP/.HLM/.LLM/.EGU/.VELO`), so ophyd `EpicsMotor` and standard EPICS tooling work unmodified.
7. **Program re-sequencing:** this IOC layer is spec #2; lightfall-pystxmcontrol device/flyer migration to EPICS is spec #3; the pystxmcontrol GUI fork (formerly spec #2) becomes spec #4. The spec-#1 NATS/Tiled remote contract is unaffected.

## 3. Architecture

### 3.1 Package layout (in the fork)

```
pystxmcontrol/iocs/
  __init__.py          # guarded imports; no hard deps leak into base package
  supervisor.py        # `stxm-iocs` entry point: config → process fleet
  base.py              # MotorRecordGroup (driver-backed mock motor record), common plumbing
  motor_ioc.py         # generic per-controller motor IOC (thin mirror)
  derived_ioc.py       # derived-axis IOCs (in-process or CA-composed)
  e712_ioc.py          # E712 IOC: motor axes + fly PVGroup + IOC-side line loop
  daq_ioc.py           # keysight counters etc.: gated-acquire groups
  shutter_ioc.py       # shutter/gate enum PVs
```

`pyproject.toml` gains console script `stxm-iocs = pystxmcontrol.iocs.supervisor:main` and an optional dependency extra `iocs = ["caproto>=1.1"]`. Nothing in `pystxmcontrol.iocs` is imported by the base package.

### 3.2 Process model

- **One caproto IOC process per hardware controller connection** (per serial port / TCP endpoint). Axis moves, derived math, and DAQ readout on different controllers never share a GIL — this is the multi-instance sharding.
- The **supervisor** parses `motor.json`/`daq.json`, groups devices by controller, spawns one IOC subprocess per group with its config slice, monitors liveness, restarts on crash with backoff, and reports fleet status (stdout table + a small supervisor PVGroup: per-IOC RUNNING/RESTARTS).
- **Hardware single-ownership:** while an IOC owns a controller connection, David's legacy scan server must not open the same port. Coexistence is via EPICS (§6), not shared serial ports.

### 3.3 Naming

PV prefix configurable in the config `epics` block; default pattern `STXM{station}:{controller}:{axis}` (e.g. `STXM7011:E712:X`). Fly and DAQ PVs nest under the controller/axis (e.g. `STXM7011:E712:FLY:GO`, `STXM7011:KEYSIGHT1:COUNTS`).

## 4. PV surface

### 4.1 Motors (all controller families)

Each axis = one caproto `PVGroup` using caproto's records machinery (`record='motor'`), backed by the corresponding `pystxmcontrol.drivers.*Motor` instance:

- `.VAL` (write → `moveTo`, async completion), `.RBV` (poll or driver callback → readback), `.DMOV`/`.MOVN` (motion state), `.STOP` (→ driver stop/abort), `.HLM`/`.LLM` (from `motor.json` limits, enforced IOC-side), `.EGU`, `.VELO` where the driver supports it.
- Readback update: background poll task per axis (period from config, default 100 ms idle / 20 ms while moving) unless the driver offers callbacks.
- ophyd `EpicsMotor` against these fields is the acceptance test.

### 4.2 Derived motors

Same motor-record face. Two composition modes:
- **Co-located** (e.g. derivedPiezo over E712 axes): instantiated inside the owning controller's IOC, calling the underlying driver objects in-process.
- **Cross-controller** (e.g. derivedEnergy over mono + gap + zone plate): its own small IOC composing the underlying axes **via CA** (caproto-client), so composition and physical IOCs restart independently. David's calibration math is imported unchanged.

### 4.3 Fly PVGroup (E712; pattern reusable for future fly controllers)

- Config: `FLY:START`, `FLY:STOP`, `FLY:NPOINTS`, `FLY:DWELL`, `FLY:AXIS` (enum), `FLY:MODE`.
- Control: `FLY:ARM` (validates + uploads trajectory to controller), `FLY:GO` (executes one hardware-timed line), `FLY:ABORT`, `FLY:STATE` (enum IDLE/ARMED/FLYING/ERROR), `FLY:ERROR` (string).
- Data: per attached DAQ a float64 waveform `FLY:DATA:{daq}` (length NPOINTS) plus `FLY:POS` (actual positions waveform) and **`FLY:INDEX`** — a monotonically increasing line counter written *after* the line's waveforms; clients monitor INDEX and then read the waveforms (write-then-increment ordering is the consistency contract).
- The line loop (trigger, gated readout, interpolation to the requested grid) runs inside the IOC using David's existing driver/DAQ code paths.

### 4.4 DAQs (keysight counter family) and shutter/gate

- Counter: `DWELL`, `MODE` (point/gated-line), `ACQUIRE` (busy record semantics: caput-callback completes when the acquisition completes), `COUNTS` (scalar) / `COUNTS:WF` (line waveform when driven by a fly line), `RATE`.
- Shutter/gate: `MODE` enum (OPEN/CLOSED/AUTO) mapping to David's `setGate` semantics; readback of actual state.

### 4.5 Array sizing

Fly line waveforms are ~`NPOINTS × 8 B` (a 1000-point line = 8 KB) — comfortably within CA with a sane `EPICS_CA_MAX_ARRAY_BYTES` (document 1 MB). Detector frames are excluded from this design (Decision 2).

## 5. Performance design (the answer to §1's objection)

- David's driver code executes **unmodified, in the IOC process, on the same host** his scan server runs on today. Identical locality; identical inner loop.
- During a fly line, zero CA traffic occurs between GO and line completion except the final waveform puts (~8-16 KB per line) and INDEX increment. Per-point caput/caget never happens.
- Step scans degrade gracefully: a step move is one `.VAL` put with completion — CA round-trip (sub-ms on the beamline LAN) is noise against mechanical settle times.
- Process-per-controller removes today's shared-process contention between GUI, scan engine, and drivers.

## 6. Coexistence and migration

David's tree already ships `epicsController`/`epicsMotor` drivers. Once the IOCs own the hardware, his **existing scan server and GUI keep working** by re-pointing `motor.json` entries at `epicsMotor` with the new PV names — his stack becomes just another EPICS client. This gives a reversible, incremental migration: wrap one controller, flip its motor.json entry, verify, proceed. No flag-day.

## 7. Testing

- **Unit:** each IOC group against David's `simulation=True` driver paths; caproto test harness for record-field semantics (limits enforcement, DMOV transitions, STOP during move).
- **e2e (sim-backed, CI-able):** spawn a sim IOC; drive it with a real ophyd `EpicsMotor` (move/readback/stop/limits); run a full fly line via the PV interface asserting waveform lengths, INDEX monotonicity, and write-then-increment ordering; ACQUIRE put-callback completion semantics.
- **Benchmark (hardware, with David):** fly-line rate and line-turnaround time, native pystxmcontrol server vs caproto IOC path, same hardware. Acceptance: no measurable line-rate regression (agree the threshold with David; target < 2 % turnaround overhead).

## 8. Program re-sequencing and downstream impact

1. Spec #1 — Remote Control API: **done, unaffected** (NATS/Tiled contract has no device-hosting assumption).
2. **Spec #2 (this): caproto IOC layer** in the pystxmcontrol fork.
3. Spec #3: lightfall-pystxmcontrol migrates `devices.py`/`flyer.py` from in-process ophyd-async wrappers to `EpicsMotor` + a flyer driving the FLY PVGroup; plans/viz/Tiled paths unchanged.
4. Spec #4: pystxmcontrol GUI fork as thin remote client (formerly spec #2; scoping answers from 2026-07-12 — "core + Tiled reads" — carry over).
5. Follow-up (not v1): CSM plugin + iocular supervision for these IOCs; detector transport (areaDetector/PVA); upstream PR to David.

## 9. Non-goals (v1)

Detector/frame transport; PVAccess; CSM/iocular integration; autosave/archiver integration; changes to David's scan server or GUI (coexistence only via §6); changes to the spec-#1 remote contract; Lightfall-side migration (spec #3).
