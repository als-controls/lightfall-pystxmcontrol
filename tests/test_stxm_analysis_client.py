from lightfall_pystxmcontrol.stxm_analysis_client import StxmAnalysisClient


def test_event_signals(fake_ipc, qtbot):
    c = StxmAnalysisClient(ipc=fake_ipc)
    got = {}
    c.spectrumUpdated.connect(lambda d: got.setdefault("spec", d))
    c.statusChanged.connect(lambda d: got.setdefault("status", d))
    c.errorReceived.connect(lambda d: got.setdefault("err", d))
    c.reductionComplete.connect(lambda d: got.setdefault("done", d))
    fake_ipc.emit("stxm.spectrum.updated", {"seq": 1})
    fake_ipc.emit("stxm.status", {"state": "reducing"})
    fake_ipc.emit("stxm.error", {"error": "x"})
    fake_ipc.emit("stxm.reduction.complete", {"products": ["od"]})
    assert got["spec"]["seq"] == 1
    assert got["status"]["state"] == "reducing"
    assert got["err"]["error"] == "x"
    assert got["done"]["products"] == ["od"]


def test_bind_run_publishes_full_payload(fake_ipc):
    c = StxmAnalysisClient(ipc=fake_ipc)
    c.bind_run("u1", tiled_url="http://t", tiled_api_key="k",
               lightfall_prefix="als.7011")
    assert fake_ipc.published == [("stxm.run.bind", {
        "run_uid": "u1", "tiled_url": "http://t", "tiled_api_key": "k",
        "lightfall_prefix": "als.7011", "contract_version": 1})]


def test_run_stop_publishes(fake_ipc):
    c = StxmAnalysisClient(ipc=fake_ipc)
    c.run_stop("u1")
    assert ("stxm.run.stop", {"run_uid": "u1"}) in fake_ipc.published


def test_no_ipc_is_safe():
    c = StxmAnalysisClient(ipc=None)
    c.bind_run("u")
    c.run_stop("u")
    assert c.discover() is None


def test_discover_requests(fake_ipc):
    fake_ipc.replies["_stxm.discover"] = {"app_name": "stxm-live"}
    c = StxmAnalysisClient(ipc=fake_ipc)
    assert c.discover()["app_name"] == "stxm-live"
