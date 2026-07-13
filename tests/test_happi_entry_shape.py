"""Verify the packaged happi entries have the expected device_class/prefix shape."""
from importlib.resources import files

import happi
from happi.backends.json_db import JSONBackend


def _client():
    db_path = str(files("lightfall_pystxmcontrol").joinpath("pystxm_happi.json"))
    return happi.Client(database=JSONBackend(db_path))


def _item(client, name):
    return client.search(name=name)[0].item


def test_axes_are_epics_motor_with_matching_prefix():
    client = _client()
    expected_prefixes = {
        "SampleX": "STXMSIM:E712:SampleX",
        "SampleY": "STXMSIM:E712:SampleY",
        "energy": "STXMSIM:XPS:energy",
    }
    for name, prefix in expected_prefixes.items():
        item = _item(client, name)
        assert item.device_class == "ophyd.EpicsMotor"
        assert item.prefix == prefix


def test_counter_entry_shape():
    client = _client()
    item = _item(client, "Counter1")
    assert item.device_class == "lightfall_pystxmcontrol.devices.StxmCounter"
    assert item.prefix == "STXMSIM:DEFAULT"


def test_flyer_entry_shape():
    client = _client()
    item = _item(client, "STXMLineFlyer")
    assert item.device_class == "lightfall_pystxmcontrol.flyer.StxmLineFlyer"
    assert item.prefix == "STXMSIM:E712:FLY"
