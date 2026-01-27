from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from .config import MealWindowConfig
from .time_utils import linear_slope


def compute_meal_macros(items: List[Dict]) -> Dict[str, float]:
    """
    Sum meal macros from `MealEventItem`s joined to `FoodItem`.

    Each item dict should include:
    - grams (float)
    - serving_grams (float)
    - calories_kcal, carbs_g, fiber_g, protein_g, fat_g (floats) stored per serving
    """
    totals = dict(
        meal_grams=0.0,
        meal_calories_kcal=0.0,
        meal_carbs_g=0.0,
        meal_fiber_g=0.0,
        meal_protein_g=0.0,
        meal_fat_g=0.0,
    )

    for it in items:
        grams = float(it.get("grams") or 0.0)
        serving_grams = float(it.get("serving_grams") or 0.0)
        if grams <= 0 or serving_grams <= 0:
            continue

        mult = grams / serving_grams
        totals["meal_grams"] += grams
        totals["meal_calories_kcal"] += float(it.get("calories_kcal") or 0.0) * mult
        totals["meal_carbs_g"] += float(it.get("carbs_g") or 0.0) * mult
        totals["meal_fiber_g"] += float(it.get("fiber_g") or 0.0) * mult
        totals["meal_protein_g"] += float(it.get("protein_g") or 0.0) * mult
        totals["meal_fat_g"] += float(it.get("fat_g") or 0.0) * mult

    return totals


def compute_time_features(meal_time: datetime) -> Dict[str, float]:
    return {
        "meal_hour": float(meal_time.hour),
        "meal_dow": float(meal_time.weekday()),   # 0=Mon
        "meal_is_weekend": float(1.0 if meal_time.weekday() >= 5 else 0.0),
    }


def compute_glucose_context_features(
    minutes_rel: np.ndarray,
    glucose_mgdl: np.ndarray,
    cfg: MealWindowConfig,
) -> Dict[str, float]:
    minutes_rel = np.asarray(minutes_rel, dtype=float)
    glucose_mgdl = np.asarray(glucose_mgdl, dtype=float)

    # baseline [-pre_baseline,0)
    m0 = (minutes_rel >= -cfg.pre_baseline_minutes) & (minutes_rel < 0)
    baseline = float(np.nanmedian(glucose_mgdl[m0])) if np.isfinite(glucose_mgdl[m0]).sum() >= cfg.min_points_pre_baseline else float("nan")

    # slope over [-pre_baseline,0)
    pre_slope = linear_slope(minutes_rel[m0], glucose_mgdl[m0])

    # context stats over [-pre_context,0)
    m1 = (minutes_rel >= -cfg.pre_context_minutes) & (minutes_rel < 0)
    ctx = glucose_mgdl[m1]
    ctx_mean = float(np.nanmean(ctx)) if np.isfinite(ctx).sum() >= 3 else float("nan")
    ctx_std = float(np.nanstd(ctx)) if np.isfinite(ctx).sum() >= 3 else float("nan")

    return {
        "baseline_mgdl": baseline,
        "pre_slope_mgdl_per_min": float(pre_slope),
        "pre_mean_mgdl": ctx_mean,
        "pre_std_mgdl": ctx_std,
    }


def _mask_between(df: pd.DataFrame, col: str, start: datetime, end: datetime) -> pd.Series:
    if df.empty:
        return pd.Series([], dtype=bool)
    s = df[col]
    return (s >= start) & (s < end)


def compute_activity_features(
    meal_time: datetime,
    workouts: pd.DataFrame,
    exercise_sets: pd.DataFrame,
    cfg: MealWindowConfig,
) -> Dict[str, float]:
    """
    Aggregate workouts and exercise sets around each meal.

    workouts columns expected:
    - start_at, end_at, duration_min, active_energy_kcal, avg_hr_bpm

    exercise_sets columns expected:
    - performed_at, reps, weight_kg
    """
    pre_start = meal_time - timedelta(minutes=cfg.activity_pre_minutes)
    post_end = meal_time + timedelta(minutes=cfg.activity_post_minutes)

    # Workouts pre
    w_pre = workouts[_mask_between(workouts, "start_at", pre_start, meal_time)] if not workouts.empty else workouts
    # Workouts post
    w_post = workouts[_mask_between(workouts, "start_at", meal_time, post_end)] if not workouts.empty else workouts

    def _sum(col: str, df: pd.DataFrame) -> float:
        if df.empty or col not in df.columns:
            return 0.0
        return float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum())

    def _count(df: pd.DataFrame) -> float:
        return float(len(df)) if df is not None else 0.0

    # Exercise sets pre/post
    s_pre = exercise_sets[_mask_between(exercise_sets, "performed_at", pre_start, meal_time)] if not exercise_sets.empty else exercise_sets
    s_post = exercise_sets[_mask_between(exercise_sets, "performed_at", meal_time, post_end)] if not exercise_sets.empty else exercise_sets

    # simple volume proxy
    def _volume(df: pd.DataFrame) -> float:
        if df.empty:
            return 0.0
        reps = pd.to_numeric(df.get("reps"), errors="coerce").fillna(0.0)
        wt = pd.to_numeric(df.get("weight_kg"), errors="coerce").fillna(0.0)
        return float((reps * wt).sum())

    return {
        "workout_count_pre6h": _count(w_pre),
        "workout_minutes_pre6h": _sum("duration_min", w_pre),
        "workout_energy_kcal_pre6h": _sum("active_energy_kcal", w_pre),
        "workout_count_post3h": _count(w_post),
        "workout_minutes_post3h": _sum("duration_min", w_post),
        "workout_energy_kcal_post3h": _sum("active_energy_kcal", w_post),
        "exercise_set_count_pre6h": _count(s_pre),
        "exercise_set_volume_pre6h": _volume(s_pre),
        "exercise_set_count_post3h": _count(s_post),
        "exercise_set_volume_post3h": _volume(s_post),
    }

