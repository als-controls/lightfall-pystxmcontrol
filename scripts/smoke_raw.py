"""Prove pystxmcontrol's simulation path works with no hardware and no ophyd."""
import asyncio
from pystxmcontrol.drivers.xpsController import xpsController
from pystxmcontrol.drivers.xpsMotor import xpsMotor
from pystxmcontrol.drivers.keysight53230A import keysight53230A

AXIS_CONFIG = {"axis": "X", "units": 1.0, "offset": 0.0,
               "minValue": -100.0, "maxValue": 100.0}
DAQ_META = {"type": "point", "record": True}


def make_sim_motor(axis_config):
    ctrl = xpsController(address="sim", port=5001, simulation=True)
    ctrl.initialize(simulation=True)
    m = xpsMotor(controller=ctrl, config=axis_config)
    m.config = axis_config
    m.offset = axis_config["offset"]
    m.units = axis_config["units"]
    m.connect(axis=axis_config["axis"])
    return m


async def main():
    m = make_sim_motor(AXIS_CONFIG)
    m.moveTo(5.0)
    print("motor pos after moveTo(5.0):", m.getPos(), "moving:", m.getStatus())

    d = keysight53230A(address="sim", port=5025, simulation=True)
    d.meta.update(DAQ_META)  # update rather than replace — preserves default "gate": False
    d.start()
    d.config(dwell=1.0)
    data = await d.getPoint()
    d.stop()
    print("daq getPoint:", data)
    print("daq getPoint type:", type(data))
    print("daq getPoint repr:", repr(data))
    if hasattr(data, 'shape'):
        print("daq getPoint shape:", data.shape)
    elif hasattr(data, '__len__'):
        print("daq getPoint len:", len(data))


if __name__ == "__main__":
    asyncio.run(main())
