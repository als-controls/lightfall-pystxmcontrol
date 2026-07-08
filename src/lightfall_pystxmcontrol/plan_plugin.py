"""Lightfall PlanPlugin exposing the simulated STXM fly raster in the UI."""
# PEP 563: keep annotations as source strings so parameter metadata like
# ``Unit("ms")`` survives introspection. Without this, inspect.signature returns
# the evaluated ``Annotated[...]`` object whose ``__name__`` is just "Annotated",
# so PlanInfo.type_name (registry.py) drops the unit and MCP plan discovery
# (list_plans) shows a bare "Annotated" — hiding that dwell is milliseconds.
# Built-in lightfall plans already rely on this; the UI resolves string
# annotations via resolve_string_annotation()/extract_annotated_metadata().
from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Annotated, Any

from lightfall.plugins.plan_plugin import PlanPlugin
from lightfall.ui.annotations import DeviceFilter, Range, Unit

from .flyer import PystxmLineFlyer
from .plans import stxm_fly_raster

# Derived from the flyer class to guarantee byte-identity with what HappiBackend
# stores: Python dotted import path (module.ClassName), matching the device_class
# field in pystxm_happi.json.
FLYER_DEVICE_CLASS = f"{PystxmLineFlyer.__module__}.{PystxmLineFlyer.__name__}"


def _stxm_fly_raster_ui(
    flyer: Annotated[Any, DeviceFilter(device_class=FLYER_DEVICE_CLASS)],
    y_axis: Annotated[Any, DeviceFilter(category="motor")],
    *,
    y_start: Annotated[float, Unit("um")] = -5.0,
    y_stop: Annotated[float, Unit("um")] = 5.0,
    ny: Annotated[int, Range(1, 10000)] = 6,
    x_start: Annotated[float, Unit("um")] = -5.0,
    x_stop: Annotated[float, Unit("um")] = 5.0,
    nx: Annotated[int, Range(1, 10000)] = 10,
    dwell: Annotated[float, Unit("ms")] = 1.0,
) -> Generator[Any, Any, Any]:
    """Step the slow axis (Y) and fly the fast axis (X) per row, one event per line.

    UNITS: y_start/y_stop/x_start/x_stop are in micrometers (um); dwell is the
    per-point count time in MILLISECONDS (ms), NOT seconds. e.g. dwell=1000 is
    1 s/point; the sim count rate is ~1e7 counts/s. A small dwell (1-10 ms)
    completes almost instantly.

    UI-facing adapter: delegates to the pure ``plans.stxm_fly_raster`` so the
    bare-RunEngine plan stays decoupled from Lightfall's UI annotations.
    """
    return (yield from stxm_fly_raster(
        flyer, y_axis, y_start=y_start, y_stop=y_stop, ny=ny,
        x_start=x_start, x_stop=x_stop, nx=nx, dwell=dwell, md=None))


class StxmFlyRasterPlanPlugin(PlanPlugin):
    """Contributes the simulated STXM fly raster to Lightfall's plan registry."""

    @property
    def name(self) -> str:
        return "stxm_fly_raster"

    @property
    def category(self) -> str:
        return "stxm"

    def get_plan_function(self) -> Callable[..., Generator[Any, Any, Any]]:
        return _stxm_fly_raster_ui
