"""Task 6: UI adapter + plan plugin for stxm_energy_stack."""
from lightfall_pystxmcontrol.plan_plugin import StxmEnergyStackPlanPlugin


def test_identity():
    p = StxmEnergyStackPlanPlugin()
    assert p.name == "stxm_energy_stack"
    assert p.category == "stxm"


def test_parameters():
    info = StxmEnergyStackPlanPlugin().get_plan_info()
    names = {p.name for p in info.parameters}
    assert names == {"flyer", "energy_axis", "y_axis", "energies",
                     "y_start", "y_stop", "ny", "x_start", "x_stop", "nx", "dwell_ms"}


def test_manifest_has_entry():
    from lightfall_pystxmcontrol.manifest import manifest
    entries = {(e.type_name, e.name) for e in manifest.plugins}
    assert ("plan", "stxm_energy_stack") in entries


def test_adapter_runs_and_validates():
    import asyncio
    from bluesky import RunEngine
    from lightfall_pystxmcontrol import config, contract
    from lightfall_pystxmcontrol.devices import PystxmAxis
    from lightfall_pystxmcontrol.flyer import PystxmLineFlyer

    plan_func = StxmEnergyStackPlanPlugin().get_plan_function()
    flyer = PystxmLineFlyer(config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"])
    y = PystxmAxis(config.DEFAULT_AXES["SampleY"], name="SampleY")
    en = PystxmAxis(config.DEFAULT_AXES["energy"], name="energy")

    async def _c():
        await flyer.connect(mock=False); await y.connect(mock=False); await en.connect(mock=False)
    asyncio.run(_c())

    docs = []
    RE = RunEngine()
    RE(plan_func(flyer, en, y, energies=[500.0, 510.0],
                 y_start=-2, y_stop=2, ny=2, x_start=-4, x_stop=4, nx=4, dwell_ms=1.0),
       lambda n, d: docs.append((n, d)))
    assert contract.validate_run_documents(docs) == []
