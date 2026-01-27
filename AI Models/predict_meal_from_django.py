from __future__ import annotations

import argparse
from datetime import timezone
from pathlib import Path
from typing import Dict

import joblib
import numpy as np
import pandas as pd

from glucose_ml.config import MealWindowConfig
from glucose_ml.django_setup import setup_django
from glucose_ml.features import (
    compute_activity_features,
    compute_glucose_context_features,
    compute_meal_macros,
    compute_time_features,
)


def _to_utc_naive(dt):
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def main() -> int:
    ap = argparse.ArgumentParser(description="Predict meal response targets for a MealEvent in Django DB.")
    ap.add_argument("--model", required=True, help="Path to scalar_model.joblib")
    ap.add_argument("--meal-event-id", type=int, required=True, help="MealEvent.id")
    args = ap.parse_args()

    setup_django()
    from core.models import EGVReading, ExerciseSet, MealEvent, Workout  # noqa: WPS433

    cfg = MealWindowConfig()
    artifact = joblib.load(Path(args.model))
    feat_cols = artifact["feature_columns"]
    targets = artifact["targets"]
    models = artifact["models"]

    meal = (
        MealEvent.objects
        .prefetch_related("items__food_item")
        .select_related("meal_template")
        .get(id=args.meal_event_id)
    )
    meal_time = _to_utc_naive(meal.eaten_at)

    items = []
    for it in meal.items.all():
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
    meal_macros = compute_meal_macros(items)

    # previous meal gap
    prev = (
        MealEvent.objects
        .filter(eaten_at__lt=meal.eaten_at)
        .order_by("-eaten_at")
        .first()
    )
    minutes_since_prev_meal = float("nan")
    if prev is not None:
        minutes_since_prev_meal = float((_to_utc_naive(meal.eaten_at) - _to_utc_naive(prev.eaten_at)).total_seconds() / 60.0)

    # extract EGV in [-pre_context, +post]
    start = meal.eaten_at - pd.Timedelta(minutes=cfg.pre_context_minutes)
    end = meal.eaten_at + pd.Timedelta(minutes=cfg.post_minutes)
    egv = list(
        EGVReading.objects
        .filter(measured_at__gte=start, measured_at__lte=end)
        .order_by("measured_at")
        .values_list("measured_at", "glucose_mgdl")
    )
    egv_times = np.array([(_to_utc_naive(t) - meal_time).total_seconds() / 60.0 for t, _ in egv], dtype=float)
    egv_vals = np.array([float(v) for _, v in egv], dtype=float)

    # workouts / sets around meal
    w_start = meal.eaten_at - pd.Timedelta(minutes=cfg.activity_pre_minutes)
    w_end = meal.eaten_at + pd.Timedelta(minutes=cfg.activity_post_minutes)
    workouts = pd.DataFrame(list(
        Workout.objects
        .filter(start_at__gte=w_start, start_at__lte=w_end)
        .values("start_at", "end_at", "duration_min", "active_energy_kcal", "avg_hr_bpm", "activity_type")
    ))
    if not workouts.empty:
        workouts["start_at"] = workouts["start_at"].map(_to_utc_naive)
        workouts["end_at"] = workouts["end_at"].map(_to_utc_naive)

    sets = pd.DataFrame(list(
        ExerciseSet.objects
        .filter(performed_at__gte=w_start, performed_at__lte=w_end)
        .values("performed_at", "reps", "weight_kg", "name")
    ))
    if not sets.empty:
        sets["performed_at"] = sets["performed_at"].map(_to_utc_naive)

    feat: Dict[str, float] = {}
    feat.update(compute_time_features(meal_time))
    feat.update(meal_macros)
    feat.update(compute_glucose_context_features(egv_times, egv_vals, cfg))
    feat.update(compute_activity_features(meal_time, workouts, sets, cfg))
    feat["minutes_since_prev_meal"] = minutes_since_prev_meal

    # assemble feature vector
    x = np.array([float(feat.get(c, float("nan"))) for c in feat_cols], dtype=float).reshape(1, -1)

    preds = {t: float(models[t].predict(x)[0]) for t in targets}

    print(f"MealEvent {meal.id} @ {meal_time.isoformat()} template={meal.meal_template_id}")
    for k, v in preds.items():
        print(f"{k}: {v:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

