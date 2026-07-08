# src/lightfall_pystxmcontrol/plans.py
import numpy as np
import bluesky.plan_stubs as bps
from bluesky.preprocessors import run_decorator

from . import contract


def _fly_rows(flyer, y_axis, *, y_start, y_stop, ny, x_start, x_stop, nx, dwell_ms):
    """Shared per-row line-fly machinery: mv slow axis, prepare/kickoff/
    complete/collect the flyer once per row. Lines are atomic: an exception
    in complete() emits no event for that row (spec §4.2)."""
    for y in np.linspace(y_start, y_stop, ny):
        yield from bps.mv(y_axis, y)
        flyer.prepare(y=float(y), x_start=x_start, x_stop=x_stop,
                      nx=nx, dwell=dwell_ms)
        yield from bps.kickoff(flyer, wait=True)
        yield from bps.complete(flyer, wait=True)
        yield from bps.collect(flyer)


def stxm_fly_raster(flyer, y_axis, *, y_start, y_stop, ny,
                    x_start, x_stop, nx, dwell, md=None):
    """Step the slow axis (Y), fly the fast axis (X) per row.

    Emits one event per line (the flyer's collect): SampleX[nx], SampleY, Counter1[nx].

    Units: y_start/y_stop/x_start/x_stop in micrometers (um); ``dwell`` is the
    per-point count time in MILLISECONDS (ms), not seconds — it is passed
    unchanged to keysight53230A.config(), whose sim getLine() sleeps
    ``dwell/1000 * nx`` seconds. So dwell=1000 -> 1 s/point.
    """
    _md = {"plan_name": "stxm_fly_raster", "shape": [ny, nx],
           "motors": [y_axis.name], "detectors": [flyer.name],
           # Extents in motor coords so consumers (e.g. the STXM scan panel)
           # can place this image in the motor coordinate frame.
           "x_extent": [float(x_start), float(x_stop)],
           "y_extent": [float(y_start), float(y_stop)]}
    if md:
        _md.update(md)

    @run_decorator(md=_md)
    def _inner():
        yield from _fly_rows(flyer, y_axis, y_start=y_start, y_stop=y_stop, ny=ny,
                             x_start=x_start, x_stop=x_stop, nx=nx, dwell_ms=dwell)

    return (yield from _inner())


def stxm_energy_stack(flyer, energy_axis, y_axis, *, energies,
                      y_start, y_stop, ny, x_start, x_stop, nx,
                      dwell_ms, md=None):
    """Energy-stack STXM: for each energy, move the energy axis then fly a
    full (ny, nx) image with the per-row line flyer (spec §3.2).

    One run, one ``primary`` stream, ``len(energies) * ny`` line events of
    shape (nx,). Ordering contract: seq_num = iE*ny + iy + 1 (spec §4.2).
    Units: positions um; ``dwell_ms`` MILLISECONDS end-to-end.
    """
    _md = contract.stxm_start_md(
        energies=energies, ny=ny, nx=nx, dwell_ms=dwell_ms,
        x_extent=[x_start, x_stop], y_extent=[y_start, y_stop],
        x_motor=flyer.X_DATA_KEY, y_motor=y_axis.name,
        energy_motor=energy_axis.name, data_field=flyer.name,
    )
    if md:
        _md.update(md)

    @run_decorator(md=_md)
    def _inner():
        for e in _md["stxm"]["energies"]:
            yield from bps.mv(energy_axis, e)
            yield from _fly_rows(flyer, y_axis, y_start=y_start, y_stop=y_stop,
                                 ny=ny, x_start=x_start, x_stop=x_stop, nx=nx,
                                 dwell_ms=dwell_ms)

    return (yield from _inner())
