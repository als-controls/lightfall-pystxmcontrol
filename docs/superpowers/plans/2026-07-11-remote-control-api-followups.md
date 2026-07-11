# Remote Control API — Follow-ups (post-merge, from final review 2026-07-11)

Branch: lightfall `feature/remote-control-api` (39dddd4..f664196, kept local — Ron drives merge).
All items below were triaged by the final whole-branch review as **follow-up, not merge-blocking**.

## Robustness
1. **Clamp client-controlled `timeout_s` in `device.put`** (`remote/service.py`): uncapped value can park an executor worker (4 workers total → starvation). Clamp to e.g. 600 s.
2. **Clear `_current` on run finish/abort/exception**: `engine.status` in the window between a new item starting and its start doc reports the previous run's `item_id`/`run_uid` with `state: "running"`.
3. **Lock `_session_channels`/`_trusted_actions`/`_subscriptions`** in IPCService in one pass (currently GIL-benign dict ops, consistent with pre-existing pattern).
4. **Guard `invoke_in_main_thread` scheduling in `plan.abort`** — if scheduling itself fails, the client only sees a timeout.

## Contract accuracy
5. **`limits` error classification**: use `isinstance(exc, ophyd.utils.errors.LimitError)` instead of the "limit"-substring heuristic.
6. **Shared writability heuristic** (`signal_control.py:77`, mirrored in `remote/service.py`): mislabels ophyd `_ReadbackSignal` as writable. Pre-existing debt; a put on a readback fails but with an imprecise code.
7. **`plugins/agents/plan_tools.py:604,795`** still return `procedure_id` in the Claude-agent tool surface — out of IPC scope, rename for vocabulary consistency someday.

## Layering / hygiene
8. **ipc→remote import inversion**: `lightfall.ipc.service` imports `lightfall.remote.protocol`. No cycle (protocol is a leaf), but consider moving `CONTRACT_VERSION`/`error_reply` into `lightfall.ipc`.
9. **Token in logs**: `_make_handler` error paths log the full subject, which embeds the session token for capability traffic; truncate the session segment.
10. **e2e hygiene**: `_ClientRunner` stops but never closes its asyncio loop (teardown stderr noise); plan.run reply `run_uid` only soft-asserted in `test_full_contract_flow`; dead-channel check uses `pytest.raises(Exception)` rather than pinning the denied reply.

## Design notes (no action)
- Missing `contract_version` in requests is treated as v1 — deliberate, documented.
- Two clients sharing an `app_name` evict each other's channel on re-auth — inherent to app-name-keyed trust; consistent with TrustManager.
- Busy-check TOCTOU across executor workers on concurrent `plan.run(reject)` — spec explicitly treats reject as a race backstop in the free-for-all model.
