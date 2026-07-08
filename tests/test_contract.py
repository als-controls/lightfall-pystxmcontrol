"""Task 4: the normative Tiled run-layout contract (spec §4)."""
import numpy as np

from lightfall_pystxmcontrol import contract


def _md(nE=2, ny=3, nx=4):
    return contract.stxm_start_md(
        energies=[500.0 + 10 * i for i in range(nE)], ny=ny, nx=nx, dwell_ms=1.0,
        x_extent=[-5.0, 5.0], y_extent=[-2.0, 2.0],
        x_motor="SampleX", y_motor="SampleY", energy_motor="energy",
        data_field="STXMLineFlyer",
    )


def test_start_md_block():
    md = _md()
    assert md["plan_name"] == "stxm_energy_stack"
    s = md["stxm"]
    assert s["contract_version"] == 1
    assert s["shape"] == [2, 3, 4]
    assert s["energies"] == [500.0, 510.0]
    assert s["dwell_ms"] == 1.0
    assert s["x_extent"] == [-5.0, 5.0] and s["y_extent"] == [-2.0, 2.0]
    assert s["x_motor"] == "SampleX" and s["y_motor"] == "SampleY"
    assert s["energy_motor"] == "energy"
    assert s["data_field"] == "STXMLineFlyer"
    assert md["motors"] == ["energy", "SampleY"] and md["detectors"] == ["STXMLineFlyer"]


def test_decode_line_index():
    ny = 3
    assert contract.decode_line_index(0, ny) == (0, 0)
    assert contract.decode_line_index(2, ny) == (0, 2)
    assert contract.decode_line_index(3, ny) == (1, 0)
    assert contract.decode_line_index(5, ny) == (1, 2)


def test_cube_from_rows_full():
    rows = np.arange(6 * 4, dtype=float).reshape(6, 4)
    cube = contract.cube_from_rows(rows, (2, 3, 4))
    assert cube.shape == (2, 3, 4)
    assert np.array_equal(cube[0, 0], rows[0])
    assert np.array_equal(cube[1, 2], rows[5])
    assert not np.isnan(cube).any()


def test_cube_from_rows_partial_nan_fills_whole_lines():
    rows = np.ones((4, 4))  # 4 of 6 lines acquired
    cube = contract.cube_from_rows(rows, (2, 3, 4))
    assert not np.isnan(cube[0]).any()          # first energy complete
    assert not np.isnan(cube[1, 0]).any()       # E1 row 0 acquired
    assert np.isnan(cube[1, 1]).all()           # missing lines are whole-NaN (spec §4.2 atomicity)
    assert np.isnan(cube[1, 2]).all()


def test_cube_from_rows_empty():
    cube = contract.cube_from_rows(np.empty((0, 4)), (2, 3, 4))
    assert np.isnan(cube).all()


def _docs(nE=2, ny=3, nx=4, n_lines=None, exit_status="success"):
    """Minimal fabricated document stream in the contract layout."""
    n = nE * ny if n_lines is None else n_lines
    docs = [("start", {**_md(nE, ny, nx), "uid": "u1"})]
    for i in range(n):
        docs.append(("event_page", {
            "seq_num": [i + 1],
            "data": {"STXMLineFlyer": [list(np.ones(nx))],
                     "SampleX": [list(np.zeros(nx))], "SampleY": [0.0]},
        }))
    docs.append(("stop", {"exit_status": exit_status, "num_events": {"primary": n}}))
    return docs


def test_validate_ok():
    assert contract.validate_run_documents(_docs()) == []


def test_validate_flags_wrong_line_length():
    docs = _docs()
    docs[1][1]["data"]["STXMLineFlyer"] = [[1.0, 2.0]]  # nx=4 expected
    assert any("shape" in e or "length" in e for e in contract.validate_run_documents(docs))


def test_validate_flags_success_with_missing_lines():
    errors = contract.validate_run_documents(_docs(n_lines=4, exit_status="success"))
    assert errors, "successful run must have nE*ny events"


def test_validate_partial_run_is_valid_when_not_success():
    assert contract.validate_run_documents(_docs(n_lines=4, exit_status="fail")) == []


def test_validate_missing_stop_doc_is_valid_partial_run():
    # Spec §4.3: a missing stop doc is a valid partial run, same as a
    # non-success stop doc, as long as line count is within capacity.
    docs = [d for d in _docs(n_lines=4) if d[0] != "stop"]
    assert contract.validate_run_documents(docs) == []


def test_validate_missing_stop_doc_still_flags_over_capacity():
    docs = [d for d in _docs(n_lines=7) if d[0] != "stop"]  # nE*ny == 6
    errors = contract.validate_run_documents(docs)
    assert any("capacity" in e for e in errors)


def test_validate_flags_malformed_shape_wrong_length():
    docs = _docs()
    docs[0][1]["stxm"]["shape"] = [2, 3]
    errors = contract.validate_run_documents(docs)
    assert any("shape" in e for e in errors)


def test_validate_flags_malformed_shape_wrong_type():
    docs = _docs()
    docs[0][1]["stxm"]["shape"] = "2x3x4"
    errors = contract.validate_run_documents(docs)
    assert any("shape" in e for e in errors)


def test_validate_flags_event_missing_data_key():
    docs = [
        ("start", {**_md(nE=1, ny=2, nx=4), "uid": "u1"}),
        ("event_page", {"seq_num": [1]}),  # no "data" key at all
        ("event_page", {"seq_num": [2], "data": {"STXMLineFlyer": [list(np.ones(4))]}}),
        ("stop", {"exit_status": "fail", "num_events": {"primary": 1}}),
    ]
    errors = contract.validate_run_documents(docs)
    assert any("data" in e for e in errors)
