from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

import numpy as np


def to_utc_naive(dt: datetime) -> datetime:
    """
    Convert aware datetimes to UTC naive for consistent numpy/pandas handling.
    Django typically returns aware datetimes when USE_TZ=True.
    """
    if dt is None:
        raise ValueError("datetime is None")
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def linear_slope(x: np.ndarray, y: np.ndarray) -> float:
    """
    Simple least-squares slope. Returns NaN if insufficient data.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 3:
        return float("nan")
    x0 = x[mask]
    y0 = y[mask]
    # slope of best-fit line
    return float(np.polyfit(x0, y0, 1)[0])


def resample_to_grid(
    minutes: np.ndarray,
    values: np.ndarray,
    grid_minutes: int,
    start_minute: int,
    end_minute: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Resample irregular (minutes, values) onto a regular grid using linear interpolation.
    Returns (grid_t, grid_y). Missing edges become NaN if no coverage.
    """
    minutes = np.asarray(minutes, dtype=float)
    values = np.asarray(values, dtype=float)
    mask = np.isfinite(minutes) & np.isfinite(values)
    if mask.sum() < 2:
        grid_t = np.arange(start_minute, end_minute + 0.0001, grid_minutes, dtype=float)
        return grid_t, np.full_like(grid_t, np.nan, dtype=float)

    t = minutes[mask]
    y = values[mask]
    order = np.argsort(t)
    t = t[order]
    y = y[order]

    grid_t = np.arange(start_minute, end_minute + 0.0001, grid_minutes, dtype=float)

    # only interpolate within observed range; outside becomes NaN
    y_interp = np.interp(grid_t, t, y)
    y_interp[grid_t < t[0]] = np.nan
    y_interp[grid_t > t[-1]] = np.nan
    return grid_t, y_interp

