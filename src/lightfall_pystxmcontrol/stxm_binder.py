"""Publishes stxm.run.bind/stop on RunEngine start/stop (XPCS binding.py shape)."""
from __future__ import annotations

from typing import Callable

from loguru import logger


def _default_run_engine():
    from lightfall.acquire.engine import get_engine
    return get_engine().RE


def _default_credentials():
    tiled_url, api_key = "", None
    try:
        from lightfall.core.services import ServiceRegistry
        from lightfall.services.tiled_service import TiledService
        ts = ServiceRegistry.get_instance().get(TiledService, None)
        if ts and ts.config:
            tiled_url = ts.config.url or ""
    except Exception:
        pass
    try:
        from lightfall.auth.session import SessionManager
        api_key = SessionManager.get_instance().get_api_key("tiled")
    except Exception:
        pass
    return tiled_url, api_key, None


def _default_prefix():
    try:
        from lightfall.ui.preferences.manager import PreferencesManager
        return PreferencesManager.get_instance().get("ipc_topic_prefix", "als.7011")
    except Exception:
        return "als.7011"


class StxmRunBinder:
    def __init__(
        self,
        client,
        run_engine_getter: Callable = _default_run_engine,
        credentials_getter: Callable = _default_credentials,
        prefix_getter: Callable = _default_prefix,
    ) -> None:
        self._client = client
        self._get_re = run_engine_getter
        self._get_creds = credentials_getter
        self._get_prefix = prefix_getter
        self._token = None
        self._re = None
        self._bound_uid: str | None = None

    @property
    def enabled(self) -> bool:
        return self._token is not None

    def enable(self) -> None:
        if self.enabled:
            return
        self._re = self._get_re()
        self._token = self._re.subscribe(self._on_document)

    def disable(self) -> None:
        if not self.enabled:
            return
        try:
            self._re.unsubscribe(self._token)
        finally:
            self._token = None
            self._re = None

    def _on_document(self, name: str, doc: dict) -> None:
        try:
            if name == "start":
                if "stxm" not in doc:
                    return  # not an stxm run; stay quiet on the bus
                uid = doc["uid"]
                tiled_url, api_key, _ = self._get_creds()
                self._client.bind_run(
                    uid, tiled_url=tiled_url, tiled_api_key=api_key,
                    lightfall_prefix=self._get_prefix())
                self._bound_uid = uid
            elif name == "stop":
                uid = doc.get("run_start") or self._bound_uid
                if uid and uid == self._bound_uid:
                    self._client.run_stop(uid)
                self._bound_uid = None
        except Exception as ex:  # never break the RunEngine document stream
            logger.exception(ex)
