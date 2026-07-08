"""STXM Tiled run-layout contract v1 — the normative implementation of spec §4.

Single source of truth for the start-doc ``stxm`` block, the line-ordering
rule (seq_num = iE*ny + iy + 1; array push offset row == seq_num - 1), and
the NaN-fill rule for partial runs. The plan (producer), the stack
visualization (consumer), and the golden-fixture validator all import this
module; nothing else may re-encode these rules.

Spec: docs/superpowers/specs/2026-07-07-stxm-lightfall-option5-design.md §4.
"""
from __future__ import annotations

import numpy as np

CONTRACT_VERSION = 1
PLAN_NAME_ENERGY_STACK = "stxm_energy_stack"


def stxm_start_md(*, energies, ny, nx, dwell_ms, x_extent, y_extent,
                  x_motor, y_motor, energy_motor, data_field) -> dict:
    """Build the full start-document metadata for an energy-stack run (§4.1)."""
    energies = [float(e) for e in energies]
    return {
        "plan_name": PLAN_NAME_ENERGY_STACK,
        "motors": [energy_motor, y_motor],
        "detectors": [data_field],
        "stxm": {
            "contract_version": CONTRACT_VERSION,
            "shape": [len(energies), int(ny), int(nx)],
            "energies": energies,
            "dwell_ms": float(dwell_ms),
            "x_extent": [float(x_extent[0]), float(x_extent[1])],
            "y_extent": [float(y_extent[0]), float(y_extent[1])],
            "x_motor": x_motor,
            "y_motor": y_motor,
            "energy_motor": energy_motor,
            "data_field": data_field,
        },
    }


def decode_line_index(row: int, ny: int) -> tuple[int, int]:
    """Map a 0-based line index (== seq_num - 1 == push offset row) to (iE, iy)."""
    return divmod(int(row), int(ny))


def cube_from_rows(rows, shape) -> np.ndarray:
    """Reshape a (k, nx) line-row array into an (nE, ny, nx) cube, NaN-filling
    unacquired lines (§4.3; lines are atomic per §4.2, so fill is whole-line)."""
    nE, ny, nx = (int(v) for v in shape)
    flat = np.full((nE * ny, nx), np.nan, dtype=float)
    rows = np.asarray(rows, dtype=float)
    if rows.ndim == 2 and rows.shape[1] == nx and rows.shape[0] > 0:
        k = min(rows.shape[0], nE * ny)
        flat[:k] = rows[:k]
    return flat.reshape(nE, ny, nx)


def validate_run_documents(docs: list[tuple[str, dict]]) -> list[str]:
    """Structurally validate a (name, doc) stream against contract v1.

    Returns a list of human-readable violations; empty means valid. This is
    the executable form of spec §4 used by the golden-fixture test and the
    smoke script.
    """
    errors: list[str] = []
    names = [n for n, _ in docs]
    if not names or names[0] != "start":
        return ["first document must be 'start'"]
    start = docs[0][1]
    s = start.get("stxm")
    if not isinstance(s, dict):
        return ["start doc has no 'stxm' block"]
    for key in ("contract_version", "shape", "energies", "dwell_ms", "x_extent",
                "y_extent", "x_motor", "y_motor", "energy_motor", "data_field"):
        if key not in s:
            errors.append(f"stxm block missing '{key}'")
    if errors:
        return errors
    if s["contract_version"] != CONTRACT_VERSION:
        errors.append(f"contract_version {s['contract_version']} != {CONTRACT_VERSION}")
    shape = s["shape"]
    if (not isinstance(shape, (list, tuple)) or len(shape) != 3
            or not all(isinstance(v, int) for v in shape)):
        errors.append(f"stxm block 'shape' must be a 3-int sequence, got {shape!r}")
        return errors
    nE, ny, nx = shape
    if len(s["energies"]) != nE:
        errors.append(f"len(energies)={len(s['energies'])} != nE={nE}")
    if start.get("plan_name") != PLAN_NAME_ENERGY_STACK:
        errors.append(f"plan_name {start.get('plan_name')!r} != {PLAN_NAME_ENERGY_STACK!r}")

    field = s["data_field"]
    seq = 0
    for name, doc in docs[1:]:
        if name not in ("event", "event_page"):
            continue
        data = doc.get("data")
        if not isinstance(data, dict):
            errors.append(f"{name} doc missing 'data'")
            continue
        seqs = doc["seq_num"] if isinstance(doc.get("seq_num"), list) else [doc.get("seq_num")]
        rows = data.get(field)
        if rows is None:
            errors.append(f"event data missing field {field!r}")
            continue
        if not isinstance(rows, list):  # bare event: single array
            rows = [rows]
        for sn, line in zip(seqs, rows):
            seq += 1
            if sn != seq:
                errors.append(f"seq_num {sn} out of order (expected {seq})")
            if len(line) != nx:
                errors.append(f"line {sn} length {len(line)} != nx={nx} (atomic lines, §4.2)")
    # A missing stop doc is a valid partial run (spec §4.3): treat it like a
    # non-success partial. The success-line-count check only applies when a
    # stop doc with exit_status == "success" is present; the capacity check
    # always applies.
    stops = [d for n, d in docs if n == "stop"]
    if stops:
        status = stops[0].get("exit_status")
        if status == "success" and seq != nE * ny:
            errors.append(f"success run has {seq} lines, expected {nE * ny}")
    if seq > nE * ny:
        errors.append(f"{seq} lines exceeds shape capacity {nE * ny}")
    return errors
