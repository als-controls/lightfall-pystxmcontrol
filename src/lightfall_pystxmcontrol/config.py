"""Minimal in-repo sim config for pystxmcontrol devices (no install file read)."""

DEFAULT_AXES = {
    "SampleX": {"axis": "X", "units": 1.0, "offset": 0.0,
                "minValue": -100.0, "maxValue": 100.0},
    "SampleY": {"axis": "Y", "units": 1.0, "offset": 0.0,
                "minValue": -100.0, "maxValue": 100.0},
    # Sim energy axis (spec §3.1): an energy-shaped Movable, NOT the real
    # derivedEnergy zone-plate physics (Phase B). eV-scale soft limits are
    # load-bearing: xpsMotor.moveTo raises SoftwareLimitError even in sim.
    "energy": {"axis": "X", "units": 1.0, "offset": 0.0,
               "minValue": 250.0, "maxValue": 2500.0},
}

DEFAULT_COUNTER = {
    "name": "Counter1", "driver": "keysight53230A", "address": "sim",
    "port": 5025, "type": "point", "record": True, "simulation": True,
}


def make_sim_motor(axis_config):
    """Wire a pystxmcontrol motor in simulation mode (no hardware/sockets)."""
    from pystxmcontrol.drivers.xpsController import xpsController
    from pystxmcontrol.drivers.xpsMotor import xpsMotor

    ctrl = xpsController(address="sim", port=5001, simulation=True)
    ctrl.initialize(simulation=True)
    m = xpsMotor(controller=ctrl, config=axis_config)
    m.config = axis_config
    m.offset = axis_config["offset"]
    m.units = axis_config["units"]
    m.connect(axis=axis_config["axis"])
    return m


def make_sim_counter(daq_config):
    """Wire a pystxmcontrol daq in simulation mode."""
    from pystxmcontrol.drivers.keysight53230A import keysight53230A

    d = keysight53230A(address=daq_config["address"],
                       port=daq_config["port"], simulation=True)
    # Use update() to overlay daq_config onto the driver's default meta dict,
    # preserving the driver-set "gate" key that keysight53230A.start() reads.
    d.meta.update(daq_config)
    d.start()
    return d
