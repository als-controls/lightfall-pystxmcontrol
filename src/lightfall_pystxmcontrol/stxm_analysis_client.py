"""Qt-side client for the external stxm-live analysis service (XPCS client shape)."""
from __future__ import annotations

from qtpy.QtCore import QObject, Signal

from lightfall_pystxmcontrol.contract import CONTRACT_VERSION


class StxmAnalysisClient(QObject):
    spectrumUpdated = Signal(dict)
    statusChanged = Signal(dict)
    errorReceived = Signal(dict)
    reductionComplete = Signal(dict)

    def __init__(self, ipc=None, parent=None) -> None:
        super().__init__(parent)
        if ipc is None:
            try:
                from lightfall.ipc.service import get_ipc_service
                ipc = get_ipc_service()
            except Exception:
                ipc = None
        self._ipc = ipc
        if self._ipc is not None:
            self._ipc.subscribe("stxm.spectrum.updated", self._on_spectrum)
            self._ipc.subscribe("stxm.status", self._on_status)
            self._ipc.subscribe("stxm.error", self._on_error)
            self._ipc.subscribe("stxm.reduction.complete", self._on_complete)

    # IPCService marshals callbacks to the Qt main thread (main_thread=True default)
    def _on_spectrum(self, subject, data, reply):
        self.spectrumUpdated.emit(data)

    def _on_status(self, subject, data, reply):
        self.statusChanged.emit(data)

    def _on_error(self, subject, data, reply):
        self.errorReceived.emit(data)

    def _on_complete(self, subject, data, reply):
        self.reductionComplete.emit(data)

    def discover(self, timeout_ms: int = 2000):
        if self._ipc is None:
            return None
        return self._ipc.request("_stxm.discover", {}, timeout_ms=timeout_ms)

    def bind_run(self, run_uid: str, tiled_url: str = "", tiled_api_key=None,
                 lightfall_prefix: str = "") -> None:
        if self._ipc is None:
            return
        self._ipc.publish("stxm.run.bind", {
            "run_uid": run_uid,
            "tiled_url": tiled_url,
            "tiled_api_key": tiled_api_key,
            "lightfall_prefix": lightfall_prefix,
            "contract_version": CONTRACT_VERSION,
        })

    def run_stop(self, run_uid: str) -> None:
        if self._ipc is None:
            return
        self._ipc.publish("stxm.run.stop", {"run_uid": run_uid})
