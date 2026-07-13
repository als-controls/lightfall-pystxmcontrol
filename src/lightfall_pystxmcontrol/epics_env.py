"""EPICS transport guard: classic ophyd over caproto's control layer.

Must run before any ophyd import. netifaces is REQUIRED - it is an optional
caproto dependency, but CA address-list discovery breaks without it.
"""
import os
import sys


def ensure_caproto_layer() -> None:
    try:
        import netifaces  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "netifaces is required for the EPICS transport "
            "(optional caproto dep; pip install netifaces)") from exc
    os.environ.setdefault("OPHYD_CONTROL_LAYER", "caproto")
    if "ophyd" in sys.modules:  # imported before us with another layer?
        import ophyd
        if getattr(ophyd, "cl", None) is not None and ophyd.cl.name != "caproto":
            ophyd.set_cl("caproto")
