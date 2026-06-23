# tests/test_config.py
from lightfall_pystxmcontrol import config


def test_default_axes_have_required_keys():
    for name, cfg in config.DEFAULT_AXES.items():
        assert {"axis", "units", "offset"} <= cfg.keys()
    assert {"SampleX", "SampleY"} <= config.DEFAULT_AXES.keys()


def test_default_counter_is_simulating():
    assert config.DEFAULT_COUNTER["simulation"] is True
