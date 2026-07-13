"""The sim fleet spawns and its PVs are reachable over real CA."""


def test_fleet_pvs_connect(stxm_fleet):
    from caproto.threading.client import Context
    ctx = Context()
    names = [
        stxm_fleet.motor_pv["SampleX"],
        stxm_fleet.motor_pv["SampleY"],
        stxm_fleet.motor_pv["energy"],
        f"{stxm_fleet.daq_prefix}:COUNTS",
        f"{stxm_fleet.fly_prefix}:STATE",
    ]
    pvs = ctx.get_pvs(*names, timeout=20)
    for pv in pvs:
        pv.wait_for_connection(timeout=20)
    assert all(pv.connected for pv in pvs)


def test_motor_pv_naming(stxm_fleet):
    assert stxm_fleet.motor_pv["SampleX"] == "STXMSIM:E712:SampleX"
    assert stxm_fleet.motor_pv["energy"] == "STXMSIM:XPS:energy"
    assert stxm_fleet.daq_prefix == "STXMSIM:DEFAULT"
    assert stxm_fleet.fly_prefix == "STXMSIM:E712:FLY"
