# tests/test_config.py
from pathlib import Path

from lightfall_pystxmcontrol import config


def test_sim_motor_json_path_exists():
    p = Path(config.sim_motor_json())
    assert p.name == "sim_motor.json"
    assert p.exists()


def test_sim_daq_json_path_exists():
    p = Path(config.sim_daq_json())
    assert p.name == "sim_daq.json"
    assert p.exists()
