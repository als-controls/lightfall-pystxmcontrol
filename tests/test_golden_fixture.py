"""Task 7: the checked-in golden run must satisfy the contract validator."""
import json
from pathlib import Path

from lightfall_pystxmcontrol import contract

FIXTURE = Path(__file__).parent / "fixtures" / "golden_energy_stack_run.json"


def test_golden_fixture_exists_and_validates():
    docs = [(n, d) for n, d in json.loads(FIXTURE.read_text())]
    errors = contract.validate_run_documents(docs)
    assert errors == [], errors


def test_golden_fixture_shape_is_2x3x4():
    docs = json.loads(FIXTURE.read_text())
    start = next(d for n, d in docs if n == "start")
    assert start["stxm"]["shape"] == [2, 3, 4]
