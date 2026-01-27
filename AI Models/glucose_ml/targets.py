from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Tuple

import numpy as np

from .config import MealWindowConfig
from .time_utils import linear_slope, resample_to_grid


def _trapz_auc(y: np.ndarray, dt_minutes: float) -> float:
    if y.size < 2 or not np.isfinite(y).any():
        return 0.0
    y0 = np.where(np.isfinite(y), y, 0.0)
    return float(np.trapz(y0, dx=dt_minutes))


def compute_targets(
    minutes_rel: np.ndarray,
    glucose_mgdl: np.ndarray,
    cfg: MealWindowConfig,
) -> Dict[str, float]:
    """
    Compute post-meal targets from irregular glucose samples relative to the meal.

    Inputs:
    - minutes_rel: minutes relative to meal time (negative before meal)
    - glucose_mgdl: glucose values
    """
    minutes_rel = np.asarray(minutes_rel, dtype=float)
    glucose_mgdl = np.asarray(glucose_mgdl, dtype=float)

    # baseline window [-pre_baseline, 0)
    pre_mask = (minutes_rel >= -cfg.pre_baseline_minutes) & (minutes_rel < 0)
    pre_vals = glucose_mgdl[pre_mask]
    baseline = float(np.nanmedian(pre_vals)) if np.isfinite(pre_vals).sum() >= cfg.min_points_pre_baseline else float("nan")

    # resample post window [0, post_minutes] to stable grid
    grid_t, grid_g = resample_to_grid(
        minutes=minutes_rel,
        values=glucose_mgdl,
        grid_minutes=cfg.grid_minutes,
        start_minute=0,
        end_minute=cfg.post_minutes,
    )

    # basic data quality: require enough non-nan points post-meal
    if np.isfinite(grid_g).sum() < cfg.min_points_post:
        return {
            "baseline_mgdl": baseline,
            "peak_mgdl": float("nan"),
            "peak_inc_mgdl": float("nan"),
            "incremental_auc_mgdl_min": float("nan"),
            "slope_0_60_mgdl_per_min": float("nan"),
        }

    peak = float(np.nanmax(grid_g))
    peak_inc = float(peak - baseline) if np.isfinite(baseline) else float("nan")

    if np.isfinite(baseline):
        inc = np.maximum(0.0, grid_g - baseline)
        iauc = _trapz_auc(inc, dt_minutes=float(cfg.grid_minutes))
    else:
        iauc = float("nan")

    # slope over [0, slope_minutes]
    slope_end = min(cfg.slope_minutes, cfg.post_minutes)
    slope_mask = (grid_t >= 0) & (grid_t <= slope_end)
    slope = linear_slope(grid_t[slope_mask], grid_g[slope_mask])

    return {
        "baseline_mgdl": baseline,
        "peak_mgdl": peak,
        "peak_inc_mgdl": peak_inc,
        "incremental_auc_mgdl_min": float(iauc),
        "slope_0_60_mgdl_per_min": float(slope),
    }

