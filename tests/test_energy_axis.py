"""Task 2: sim energy axis — eV-scale limits, happi entry, movable in sim."""
import asyncio
import json
from importlib.resources import files

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.devices import PystxmAxis


def test_energy_in_default_axes_with_ev_limits():
    cfg = config.DEFAULT_AXES["energy"]
    assert cfg["minValue"] == 250.0
    assert cfg["maxValue"] == 2500.0
    assert cfg["axis"] == "X"  # sim xpsMotor axis label; placeholder physics (spec §3.1)


def test_happi_db_has_energy_entry():
    db = json.loads(files("lightfall_pystxmcontrol").joinpath("pystxm_happi.json").read_text())
    assert "energy" in db, f"happi DB entries: {sorted(db)}"
    entry = db["energy"]
    assert entry["device_class"] == "lightfall_pystxmcontrol.devices.PystxmAxis"
    assert entry["kwargs"]["axis_config"]["minValue"] == 250.0
    assert entry["kwargs"]["axis_config"]["maxValue"] == 2500.0
    assert len(db) == 5  # SampleX, SampleY, Counter1, STXMLineFlyer, energy


def test_energy_axis_moves_to_ev_setpoint_in_sim():
    axis = PystxmAxis(config.DEFAULT_AXES["energy"], name="energy")

    async def _go():
        await axis.connect(mock=False)
        await axis.set(700.0)  # a realistic C-edge-ish eV value
        return await axis.readback.get_value()

    assert asyncio.run(_go()) == 700.0  # would raise SoftwareLimitError with ±100 limits
