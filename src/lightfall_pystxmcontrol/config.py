"""Paths to the packaged sim fleet configs (see spec #3)."""

from importlib.resources import files as _files


def sim_motor_json() -> str:
    """Absolute path to the packaged sim fleet motor config."""
    return str(_files("lightfall_pystxmcontrol") / "sim_motor.json")


def sim_daq_json() -> str:
    return str(_files("lightfall_pystxmcontrol") / "sim_daq.json")
