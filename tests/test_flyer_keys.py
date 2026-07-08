"""Task 3: flyer data-key constants + non-colliding default name."""
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
from lightfall_pystxmcontrol import config


def test_data_key_class_constants():
    assert PystxmLineFlyer.X_DATA_KEY == "SampleX"
    assert PystxmLineFlyer.Y_DATA_KEY == "SampleY"


def test_default_name_matches_happi_entry_not_counter():
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"])
    assert flyer.name == "STXMLineFlyer"  # was "Counter1" — collided with the counter device


def test_describe_collect_uses_constants():
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"])
    flyer.prepare(y=0.0, x_start=-1.0, x_stop=1.0, nx=4, dwell=1.0)
    desc = flyer.describe_collect()["primary"]
    assert set(desc) == {PystxmLineFlyer.X_DATA_KEY, PystxmLineFlyer.Y_DATA_KEY, "STXMLineFlyer"}
