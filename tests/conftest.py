import pytest


class FakeIPC:
    """Duck-type of lightfall.ipc.service.IPCService for unit tests."""

    def __init__(self):
        self.published = []
        self.requests = []
        self.replies = {}
        self.subscriptions = {}

    def publish(self, subject, data):
        self.published.append((subject, data))

    def request(self, subject, data, timeout_ms=1000):
        self.requests.append((subject, data))
        return self.replies.get(subject)

    def subscribe(self, subject, callback, *, main_thread=True):
        self.subscriptions[subject] = callback

    def emit(self, subject, data):
        self.subscriptions[subject](subject, data, None)


@pytest.fixture
def fake_ipc():
    return FakeIPC()


# ---- EPICS fleet fixtures (spec #3) -------------------------------------
import os
import random
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_IOCS_SRC = Path(
    r"C:\Users\rp\PycharmProjects\ncs\lightfall-pystxmcontrol\_pystxmcontrol_iocs_wt")


@pytest.fixture(scope="session")
def iocs_src() -> Path:
    src = Path(os.environ.get("PYSTXMCONTROL_IOCS_SRC", _DEFAULT_IOCS_SRC))
    if not (src / "pystxmcontrol" / "iocs" / "supervisor.py").exists():
        pytest.fail(
            f"spec-#2 IOC layer not found at {src}. Set PYSTXMCONTROL_IOCS_SRC "
            "to the pystxmcontrol fork checkout (branch feature/caproto-iocs).")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return src


_issued_udp_ports: set[int] = set()


def _free_udp_port() -> int:
    """Find a UDP port free at bind-time and not already handed out this session.

    Binding and releasing only proves the port was free at that instant; a
    later call in the same fleet spawn loop could re-discover the same port
    before the first IOC has claimed it (TOCTOU). Track issued ports across
    calls so sequential spawns never collide with each other.
    """
    for _ in range(50):
        port = random.randint(40000, 60000)
        if port in _issued_udp_ports:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                _issued_udp_ports.add(port)
                return port
            except OSError:
                continue
    raise RuntimeError("no free UDP port found")


@pytest.fixture(scope="session")
def stxm_fleet(iocs_src, tmp_path_factory):
    """Spawn the full sim IOC fleet (spec-#2 supervisor plan) once per session."""
    from lightfall_pystxmcontrol import config, epics_env
    epics_env.ensure_caproto_layer()
    from pystxmcontrol.iocs.config import load_fleet
    from pystxmcontrol.iocs.supervisor import plan_fleet

    slice_dir = tmp_path_factory.mktemp("stxm_slices")
    fleet = load_fleet(config.sim_motor_json(), config.sim_daq_json(), station="SIM")

    from lightfall_pystxmcontrol.flyer import _DAQ_KEY
    assert fleet.daqs[0].key == _DAQ_KEY, (
        f"fleet daq key {fleet.daqs[0].key!r} != flyer's expected {_DAQ_KEY!r}; "
        "sim_daq.json was likely renamed/restructured without updating flyer.py "
        "(fails fast here instead of hanging on a PV connect below)")

    plans = plan_fleet(fleet, str(slice_dir))

    addr_entries: list[str] = []
    procs: list[subprocess.Popen] = []
    for plan in plans:
        port = _free_udp_port()
        addr_entries.append(f"127.0.0.1:{port}")
        env = dict(os.environ)
        env.update({
            "EPICS_CAS_SERVER_PORT": str(port),
            "EPICS_CA_SERVER_PORT": str(port),   # caproto server binds via this
            "EPICS_CA_ADDR_LIST": " ".join(addr_entries),
            "EPICS_CA_AUTO_ADDR_LIST": "NO",
            "PYTHONPATH": os.pathsep.join(
                [str(iocs_src), str(REPO_ROOT / "src")]),
        })
        procs.append(subprocess.Popen(
            [sys.executable, "-m", plan.module, "--slice", plan.slice_path,
             "--quiet"],
            env=env))
        time.sleep(0.5)

    addr_list = " ".join(addr_entries)
    saved_env = {k: os.environ.get(k)
                 for k in ("EPICS_CA_ADDR_LIST", "EPICS_CA_AUTO_ADDR_LIST")}
    os.environ["EPICS_CA_ADDR_LIST"] = addr_list
    os.environ["EPICS_CA_AUTO_ADDR_LIST"] = "NO"
    try:
        time.sleep(3.0)
        dead = [p.args for p in procs if p.poll() is not None]
        assert not dead, f"IOC(s) exited early: {dead}"

        e712_label = next(g.label for g in fleet.controller_groups
                          if g.controller_cls == "E712Controller")
        yield SimpleNamespace(
            addr_list=addr_list,
            motor_pv=fleet.motor_pv,
            fly_prefix=f"STXMSIM:{e712_label}:FLY",
            daq_prefix=fleet.daqs[0].prefix,
        )
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
        for key, prior in saved_env.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior
