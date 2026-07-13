"""Generate pystxm_happi.json from the packaged sim fleet JSONs.

PV prefixes come from spec #2's fleet model (pystxmcontrol.iocs.config), so
naming can never drift between the IOCs and this plugin. Re-run + commit the
JSON after changing sim_motor.json/sim_daq.json.

    <lightfall-venv>/python scripts/build_pystxm_happi_db.py [--station SIM]
        [--iocs-src <pystxmcontrol fork checkout>]
"""
import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_IOCS_SRC = Path(
    r"C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\_pystxmcontrol_iocs_wt")
OUT = (Path(__file__).resolve().parents[1]
       / "src" / "lightfall_pystxmcontrol" / "pystxm_happi.json")


def build(station: str, iocs_src: Path) -> None:
    if str(iocs_src) not in sys.path:
        sys.path.insert(0, str(iocs_src))
    import happi
    from happi.backends.json_db import JSONBackend
    from pystxmcontrol.iocs.config import load_fleet

    from lightfall_pystxmcontrol import config

    fleet = load_fleet(config.sim_motor_json(), config.sim_daq_json(),
                       station=station)
    e712_label = next(g.label for g in fleet.controller_groups
                      if g.controller_cls == "E712Controller")

    OUT.write_text(json.dumps({}))
    client = happi.Client(database=JSONBackend(str(OUT)))

    for key, pv in fleet.motor_pv.items():
        client.add_item(happi.OphydItem(
            name=key, device_class="ophyd.EpicsMotor",
            args=[], prefix=pv, kwargs={"name": "{{name}}"}, active=True))

    client.add_item(happi.OphydItem(
        name="Counter1",
        device_class="lightfall_pystxmcontrol.devices.StxmCounter",
        args=[], prefix=fleet.daqs[0].prefix,
        kwargs={"name": "{{name}}"}, active=True))

    client.add_item(happi.OphydItem(
        name="STXMLineFlyer",
        device_class="lightfall_pystxmcontrol.flyer.StxmLineFlyer",
        args=[], prefix=f"STXM{station}:{e712_label}:FLY",
        kwargs={"name": "{{name}}"}, active=True))

    print(f"Wrote {OUT} ({len(client.search())} devices)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--station", default="SIM")
    p.add_argument("--iocs-src", default=os.environ.get(
        "PYSTXMCONTROL_IOCS_SRC", str(DEFAULT_IOCS_SRC)))
    a = p.parse_args()
    build(a.station, Path(a.iocs_src))
