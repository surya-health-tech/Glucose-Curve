from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import pandas as pd

from .config import MealWindowConfig
from .features import compute_meal_macros


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def extract_for_meal_dataset(
    cfg: MealWindowConfig,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Extract meals + sensor/activity data for building a meal-centered dataset.

    Returns DataFrames:
    - meals: one row per MealEvent with summed macros
    - egv: EGVReading points
    - workouts: Workout rows
    - exercise_sets: ExerciseSet rows
    """
    # Local import so scripts can call setup_django() first
    from core.models import EGVReading, ExerciseSet, MealEvent, Workout  # noqa: WPS433

    meal_qs = (
        MealEvent.objects
        .select_related("meal_template")
        .prefetch_related("items__food_item")
        .order_by("eaten_at")
    )
    if start is not None:
        meal_qs = meal_qs.filter(eaten_at__gte=start)
    if end is not None:
        meal_qs = meal_qs.filter(eaten_at__lt=end)

    meals_rows = []
    meal_times = []
    for m in meal_qs:
        items = []
        for it in m.items.all().order_by("sort_order", "id"):
            fi = it.food_item
            items.append({
                "grams": float(it.grams),
                "serving_grams": float(fi.serving_grams),
                "calories_kcal": float(fi.calories_kcal),
                "carbs_g": float(fi.carbs_g),
                "fiber_g": float(fi.fiber_g),
                "protein_g": float(fi.protein_g),
                "fat_g": float(fi.fat_g),
            })
        macros = compute_meal_macros(items)
        eaten_at = _to_utc_naive(m.eaten_at)
        meal_times.append(eaten_at)
        meals_rows.append({
            "meal_event_id": m.id,
            "eaten_at": eaten_at,
            "meal_template_id": m.meal_template_id,
            "meal_template_name": (m.meal_template.name if m.meal_template else None),
            **macros,
        })

    meals_df = pd.DataFrame(meals_rows)
    if meals_df.empty:
        return {
            "meals": meals_df,
            "egv": pd.DataFrame(),
            "workouts": pd.DataFrame(),
            "exercise_sets": pd.DataFrame(),
        }

    min_meal = min(meal_times)
    max_meal = max(meal_times)

    # widen extraction range to cover windows used for features/targets
    start_needed = min_meal - timedelta(minutes=max(cfg.pre_context_minutes, cfg.activity_pre_minutes))
    end_needed = max_meal + timedelta(minutes=max(cfg.post_minutes, cfg.activity_post_minutes))

    egv_qs = (
        EGVReading.objects
        .filter(measured_at__gte=start_needed, measured_at__lte=end_needed)
        .order_by("measured_at")
        .values("measured_at", "glucose_mgdl")
    )
    egv_df = pd.DataFrame([
        {"measured_at": _to_utc_naive(r["measured_at"]), "glucose_mgdl": float(r["glucose_mgdl"])}
        for r in egv_qs
    ])

    workout_qs = (
        Workout.objects
        .filter(start_at__gte=start_needed, start_at__lte=end_needed)
        .order_by("start_at")
        .values("start_at", "end_at", "duration_min", "active_energy_kcal", "avg_hr_bpm", "activity_type")
    )
    workouts_df = pd.DataFrame([
        {
            "start_at": _to_utc_naive(w["start_at"]),
            "end_at": _to_utc_naive(w["end_at"]),
            "duration_min": float(w["duration_min"]) if w["duration_min"] is not None else 0.0,
            "active_energy_kcal": float(w["active_energy_kcal"]) if w["active_energy_kcal"] is not None else 0.0,
            "avg_hr_bpm": float(w["avg_hr_bpm"]) if w["avg_hr_bpm"] is not None else 0.0,
            "activity_type": w["activity_type"],
        }
        for w in workout_qs
    ])

    sets_qs = (
        ExerciseSet.objects
        .filter(performed_at__gte=start_needed, performed_at__lte=end_needed)
        .order_by("performed_at")
        .values("performed_at", "name", "reps", "weight_kg")
    )
    exercise_sets_df = pd.DataFrame([
        {
            "performed_at": _to_utc_naive(s["performed_at"]),
            "name": s["name"],
            "reps": int(s["reps"]) if s["reps"] is not None else 0,
            "weight_kg": float(s["weight_kg"]) if s["weight_kg"] is not None else 0.0,
        }
        for s in sets_qs
    ])

    return {
        "meals": meals_df,
        "egv": egv_df,
        "workouts": workouts_df,
        "exercise_sets": exercise_sets_df,
    }

