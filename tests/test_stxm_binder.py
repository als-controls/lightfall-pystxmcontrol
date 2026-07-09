from unittest.mock import MagicMock

from lightfall_pystxmcontrol.stxm_analysis_client import StxmAnalysisClient
from lightfall_pystxmcontrol.stxm_binder import StxmRunBinder


def _binder(fake_ipc):
    client = StxmAnalysisClient(ipc=fake_ipc)
    re = MagicMock()
    re.subscribe.return_value = 7
    b = StxmRunBinder(
        client,
        run_engine_getter=lambda: re,
        credentials_getter=lambda: ("http://t", "key", None),
        prefix_getter=lambda: "als.7011",
    )
    return b, re, fake_ipc


def _start_doc(uid="runX"):
    return {"uid": uid, "plan_name": "stxm_energy_stack", "stxm": {"contract_version": 1}}


def test_enable_subscribes_disable_unsubscribes(fake_ipc):
    b, re, _ = _binder(fake_ipc)
    b.enable()
    assert b.enabled
    b.enable()  # idempotent
    re.subscribe.assert_called_once()
    b.disable()
    re.unsubscribe.assert_called_once_with(7)
    assert not b.enabled


def test_stxm_start_publishes_bind(fake_ipc):
    b, re, ipc = _binder(fake_ipc)
    b.enable()
    cb = re.subscribe.call_args[0][0]
    cb("start", _start_doc())
    assert ipc.published == [("stxm.run.bind", {
        "run_uid": "runX", "tiled_url": "http://t", "tiled_api_key": "key",
        "lightfall_prefix": "als.7011", "contract_version": 1})]
    cb("stop", {"run_start": "runX"})
    assert ("stxm.run.stop", {"run_uid": "runX"}) in ipc.published


def test_non_stxm_run_ignored(fake_ipc):
    b, re, ipc = _binder(fake_ipc)
    b.enable()
    cb = re.subscribe.call_args[0][0]
    cb("start", {"uid": "plain", "plan_name": "count"})
    cb("stop", {"run_start": "plain"})
    assert ipc.published == []


def test_callback_exceptions_swallowed(fake_ipc):
    b, re, _ = _binder(fake_ipc)
    b._get_creds = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    b.enable()
    cb = re.subscribe.call_args[0][0]
    cb("start", _start_doc())  # must not raise
