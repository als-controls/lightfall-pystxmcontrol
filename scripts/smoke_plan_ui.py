"""Spike: pin Lightfall plan-surfacing + device-catalog surfaces for the fly-scan UI launch.

Phase 2b spike (Task 1). NOT a test — an empirical probe of Lightfall's *internal*
plan-surfacing + device-catalog APIs, run against the real source so Tasks 2-4 build
against confirmed forms. Run with Lightfall's 3.14 venv:

    C:/Users/rp/PycharmProjects/ncs/lightfall/.venv/Scripts/python scripts/smoke_plan_ui.py

Four things pinned (see NOTES-environment.md "## Phase 2b — UI-launch spike"):
  (a) PlanInfo / ParameterInfo / from_function field names + annotations module forms
  (b) whether a non-Readable PystxmLineFlyer breaks the device-catalog state/status/list path
  (c) Annotated-signature introspection + the device_class filter matching semantics
  (d) end-to-end: resolve names -> instances -> build plan -> run on a bare RunEngine
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import asyncio
import inspect
from collections.abc import Generator
from typing import Annotated, Any, get_args, get_origin

from lightfall_pystxmcontrol import config
from lightfall_pystxmcontrol.backend import PystxmStxmBackend
from lightfall_pystxmcontrol.devices import PystxmAxis
from lightfall_pystxmcontrol.flyer import PystxmLineFlyer
from lightfall_pystxmcontrol.plans import stxm_fly_raster

# --- (a)/(c) PlanInfo introspection of an Annotated signature ---
from lightfall.acquire.plans.registry import ParameterInfo, PlanInfo
from lightfall.ui.annotations import DeviceFilter, Range, Unit

# device_class as the backend registers it (module:Class, see backend.py).
FLYER_DEVICE_CLASS = "lightfall_pystxmcontrol.flyer:PystxmLineFlyer"

print("=" * 70)
print("Phase 2b spike — pin plan-surfacing + device-catalog surfaces")
print("=" * 70)


def _probe_plan(
    flyer: Annotated[Any, DeviceFilter(device_class=FLYER_DEVICE_CLASS)],
    y_axis: Annotated[Any, DeviceFilter(category="motor")],
    y_start: Annotated[float, Unit("um")] = -5.0,
    y_stop: Annotated[float, Unit("um")] = 5.0,
    ny: Annotated[int, Range(1, 10000)] = 6,
    x_start: Annotated[float, Unit("um")] = -5.0,
    x_stop: Annotated[float, Unit("um")] = 5.0,
    nx: Annotated[int, Range(1, 10000)] = 10,
    dwell: Annotated[float, Unit("ms")] = 1.0,
) -> Generator[Any, Any, Any]:
    """Probe plan for introspection.

    A thin wrapper over stxm_fly_raster with Annotated UI hints. Used only to
    drive PlanInfo.from_function — exercises the same introspection path the
    real PlanPlugin will hit.

    Args:
        flyer: The line flyer detector to fly per row.
        y_axis: The slow-axis motor to step.
        y_start: Slow-axis scan start.
        y_stop: Slow-axis scan stop.
        ny: Number of rows.
        x_start: Fast-axis scan start.
        x_stop: Fast-axis scan stop.
        nx: Number of columns per row.
        dwell: Per-point dwell time.
    """
    yield from stxm_fly_raster(
        flyer,
        y_axis,
        y_start=y_start,
        y_stop=y_stop,
        ny=ny,
        x_start=x_start,
        x_stop=x_stop,
        nx=nx,
        dwell=dwell,
    )


print("\n--- (a) PlanInfo.from_function field names ---")
info = PlanInfo.from_function("stxm_fly_raster", _probe_plan, "fly")
print("type(info):", type(info).__name__)
print("PlanInfo public fields:", [f for f in vars(info) if not f.startswith("_")])
print("info.name:", info.name)
print("info.category:", info.category)
print("info.description:", repr(info.description))
print("info.get_display_name():", info.get_display_name())
print("info.get_icon():", info.get_icon())
print("type(parameters[0]):", type(info.parameters[0]).__name__)
print(
    "ParameterInfo fields:",
    [f for f in vars(info.parameters[0]) if not f.startswith("_")],
    "+ props: required, type_name",
)
print("\nParameter descriptors:")
for p in info.parameters:
    print(
        f"  name={p.name!r:12} type_name={p.type_name!r:18} "
        f"required={p.required!s:5} default={p.default!r:8} "
        f"kind={p.kind.name} desc={p.description!r}"
    )


# --- (c) Annotated-signature introspection: how params classify in the UI ---
# PlanInfo/ParameterInfo store the RAW annotation (the Annotated[...] object).
# The device-picker-vs-numeric classification lives in plan_config.py's
# _build_param_spec via extract_annotated_metadata + get_param_category.
# Replicate that logic here so the spike proves the classification WITHOUT a
# QApplication (the real classifier needs pyqtgraph/Qt). The matching rule for
# device_class is copied verbatim from plan_config.py (lines ~504-513).
print("\n--- (c) Annotated classification (mirrors plan_config._build_param_spec) ---")


def _extract_annotated_metadata(annotation: Any) -> tuple[Any, list[Any]]:
    """Mirror lightfall.ui.widgets.plan_config.extract_annotated_metadata.

    Annotations here are real objects (we did NOT use string annotations in the
    probe func's own scope), so no string-resolution step is needed.
    """
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        if args:
            return args[0], list(args[1:])
    return annotation, []


def _classify(param: ParameterInfo) -> str:
    base, metadata = _extract_annotated_metadata(param.annotation)
    has_device_filter = any(isinstance(m, DeviceFilter) for m in metadata)
    if has_device_filter:
        origin = get_origin(base)
        return "devices (multi)" if origin in (list, tuple) else "device (single)"
    # numeric/basic
    units = [m.suffix for m in metadata if isinstance(m, Unit)]
    ranges = [(m.min, m.max) for m in metadata if isinstance(m, Range)]
    extra = ""
    if units:
        extra += f" unit={units[0]}"
    if ranges:
        extra += f" range={ranges[0]}"
    tn = getattr(base, "__name__", str(base))
    return f"basic:{tn}{extra}"


for p in info.parameters:
    print(f"  {p.name:12} -> {_classify(p)}")


# --- (b) register a non-Readable flyer as a DeviceInfo; exercise the catalog path ---
print("\n--- (b) non-Readable flyer in the device catalog ---")
from lightfall.devices.catalog import DeviceCatalog
from lightfall.devices.model import ConnectionType, DeviceCategory, DeviceInfo, DeviceStatus

# Reset any prior singleton state so the spike is deterministic.
DeviceCatalog.reset_instance()

# Bring up the Phase-1 backend (registers SampleX, SampleY motors + Counter1 point
# detector with live ophyd-async instances). This is the "point Counter1" the
# device_class filter must NOT select.
backend = PystxmStxmBackend()
ok = backend.connect()
print("backend.connect():", ok, "device_count:", backend.get_backend_info()["device_count"])

# Build + connect the flyer (NOT Readable: no read/describe/position/value).
flyer = PystxmLineFlyer(
    config.DEFAULT_COUNTER, config.DEFAULT_AXES["SampleX"], name="STXMLineFlyer"
)
asyncio.run(flyer.connect(mock=False))
print(
    "flyer has read():", hasattr(flyer, "read"),
    " describe():", hasattr(flyer, "describe"),
    " position:", hasattr(flyer, "position"),
    " get():", hasattr(flyer, "get"),
    " connected:", hasattr(flyer, "connected"),
)

# Register the flyer as a DeviceInfo and inject it into the backend so the
# catalog resolver can find it by name. (Phase 2 will register it the same way
# the backend registers its own devices — via _add_device_internal.)
flyer_info = DeviceInfo(
    name="STXMLineFlyer",
    description="Simulated pystxmcontrol STXM line flyer",
    device_class=FLYER_DEVICE_CLASS,
    category=DeviceCategory.DETECTOR,
    connection_type=ConnectionType.SIMULATED,
    prefix="STXMLineFlyer",
    tags=["flyer", "stxm", "pystxmcontrol", "simulated"],
    metadata={},
)
flyer_info._ophyd_device = flyer
backend._add_device_internal(flyer_info)
backend._ophyd_devices["STXMLineFlyer"] = flyer

catalog = DeviceCatalog.get_instance()
catalog.set_backend(backend)

# Exercise the catalog/list/status/summary paths against the non-Readable flyer.
errors: list[str] = []


def _try(label: str, fn):
    try:
        out = fn()
        print(f"  OK   {label}: {out!r}")
    except Exception as exc:  # noqa: BLE001 — recording is the deliverable
        msg = f"{type(exc).__name__}: {exc}"
        print(f"  FAIL {label}: {msg}")
        errors.append(f"{label}: {msg}")


_try("list_devices()", lambda: [d.name for d in catalog.list_devices(active_only=False)])
_try(
    "list_devices(DETECTOR)",
    lambda: [d.name for d in catalog.list_devices(category=DeviceCategory.DETECTOR, active_only=False)],
)
_try("get_device_by_name('STXMLineFlyer')", lambda: catalog.get_device_by_name("STXMLineFlyer").name)
_try("flyer_info.state.status", lambda: flyer_info.state.status.value)
_try("flyer_info.to_summary()", lambda: flyer_info.to_summary())
_try("search_devices('flyer')", lambda: [d.name for d in catalog.search_devices("flyer")])
# refresh_device_state IS the one path that probes .position/.get() — but both are
# hasattr-guarded, so it must NOT raise on a non-Readable device.
_try(
    "refresh_device_state(flyer)",
    lambda: catalog.refresh_device_state(flyer_info.id).status.value,
)
_try("get_ophyd_device('STXMLineFlyer')", lambda: type(catalog.get_ophyd_device("STXMLineFlyer")).__name__)

print(
    f"  => non-Readable flyer broke the catalog path? "
    f"{'YES — ' + '; '.join(errors) if errors else 'NO (no path read()/describe()/position/value on it)'}"
)


# --- (c) device_class filter selects the flyer out of a list incl. the point Counter1 ---
print("\n--- (c) DeviceFilter(device_class=...) matching ---")


def _device_class_match(device_info: DeviceInfo, dc: str) -> bool:
    """Verbatim port of the filter_func built in plan_config._build_param_spec.

    Note: rsplit is on '.', NOT ':'. For 'pkg.mod:Class' the last '.'-segment is
    'mod:Class', so the bare-class fallback ('PystxmLineFlyer') will NOT match a
    'module:Class' device_class. Equality on the full string is what matches here.
    """
    return device_info is not None and (
        device_info.device_class == dc
        or device_info.device_class.rsplit(".", 1)[-1] == dc
    )


all_devs = catalog.list_devices(active_only=False)
selected = [d.name for d in all_devs if _device_class_match(d, FLYER_DEVICE_CLASS)]
print("  all devices:", [(d.name, d.device_class) for d in all_devs])
print(f"  DeviceFilter(device_class={FLYER_DEVICE_CLASS!r}) selects:", selected)
print(
    "  bare-class fallback DeviceFilter(device_class='PystxmLineFlyer') selects:",
    [d.name for d in all_devs if _device_class_match(d, "PystxmLineFlyer")],
)
# Motor picker (category) — confirm y_axis filter selects only motors.
motor_names = [d.name for d in catalog.list_devices(category=DeviceCategory.MOTOR, active_only=False)]
print("  DeviceFilter(category='motor') selects:", motor_names)


# --- (d) end-to-end run: resolve names -> instances -> build plan -> bare RunEngine ---
print("\n--- (d) end-to-end launch path ---")
from bluesky import RunEngine


def _resolve_single_device(name: str) -> Any:
    """Mirror BlueskyPanel._resolve_single_device: name -> ophyd instance."""
    di = catalog.get_device_by_name(name)
    if di is None:
        raise ValueError(f"device {name!r} not in catalog")
    return di.ophyd_device


# UI would deliver kwargs as device-NAME strings for device params + numerics.
ui_kwargs = {
    "flyer": "STXMLineFlyer",
    "y_axis": "SampleY",
    "y_start": -5.0,
    "y_stop": 5.0,
    "ny": 6,
    "x_start": -5.0,
    "x_stop": 5.0,
    "nx": 10,
    "dwell": 1.0,
}

# Device params (flyer, y_axis) resolve name -> instance; numerics pass through.
device_params = {"flyer", "y_axis"}
resolved = {
    k: (_resolve_single_device(v) if k in device_params else v)
    for k, v in ui_kwargs.items()
}
print("  resolved flyer:", type(resolved["flyer"]).__name__, "name=", resolved["flyer"].name)
print("  resolved y_axis:", type(resolved["y_axis"]).__name__, "name=", resolved["y_axis"].name)

# Build the plan from the introspected function and run on a bare RunEngine.
docs: list[tuple[str, dict]] = []
RE = RunEngine({})
RE(info.func(**resolved), lambda name, doc: docs.append((name, doc)))

doc_names = [n for n, _ in docs]
event_pages = [d for n, d in docs if n == "event_page"]
print("  document names:", doc_names)
print(f"  event_page count: {len(event_pages)} (expected ny={ui_kwargs['ny']})")

# Inspect counts. Phase 2a found 1.14.6 emits event_page with list-wrapped data[key].
counter_key = flyer.name  # "STXMLineFlyer"
total_counts = 0
positive_pages = 0
for ep in event_pages:
    # event_page.data[key] is a list (one entry per event in the page).
    arr = ep["data"][counter_key][0]
    s = float(sum(arr))
    total_counts += s
    if s > 0:
        positive_pages += 1
print(
    f"  positive-count pages: {positive_pages}/{len(event_pages)}  total counts={total_counts:.1f}"
)

assert len(event_pages) == ui_kwargs["ny"], "event_page count != ny"
assert positive_pages == len(event_pages), "some pages had non-positive counts"
print("  end-to-end run: PASS")

print("\n--- Phase 2b spike complete ---")
