# src/lightfall_pystxmcontrol/plans.py
import numpy as np
import bluesky.plan_stubs as bps
from bluesky.preprocessors import run_decorator


def stxm_fly_raster(flyer, y_axis, *, y_start, y_stop, ny,
                    x_start, x_stop, nx, dwell, md=None):
    """Step the slow axis (Y), fly the fast axis (X) per row.

    Emits one event per line (the flyer's collect): SampleX[nx], SampleY, Counter1[nx].
    """
    _md = {"plan_name": "stxm_fly_raster", "shape": [ny, nx],
           "motors": [y_axis.name], "detectors": [flyer.name]}
    if md:
        _md.update(md)

    @run_decorator(md=_md)
    def _inner():
        for y in np.linspace(y_start, y_stop, ny):
            yield from bps.mv(y_axis, y)
            flyer.prepare(y=float(y), x_start=x_start, x_stop=x_stop,
                          nx=nx, dwell=dwell)
            yield from bps.kickoff(flyer, wait=True)
            yield from bps.complete(flyer, wait=True)
            yield from bps.collect(flyer)

    return (yield from _inner())
