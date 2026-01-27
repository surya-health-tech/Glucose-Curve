from __future__ import annotations

from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd

from .config import MealWindowConfig
from .features import compute_activity_features, compute_glucose_context_features, compute_time_features
from .targets import compute_targets


def build_meal_dataset(
    meals: pd.DataFrame,
    egv: pd.DataFrame,
    workouts: pd.DataFrame,
    exercise_sets: pd.DataFrame,
    cfg: MealWindowConfig,
) -> pd.DataFrame:
    """
    Build a meal-centered dataset (one row per MealEvent).

    Expected input frames:
    - meals: columns [meal_event_id, eaten_at, meal_* macros ...]
    - egv: columns [measured_at, glucose_mgdl]
    - workouts: columns [start_at, ...]
    - exercise_sets: columns [performed_at, ...]
    """
    if meals.empty:
        return pd.DataFrame()

    egv = egv.sort_values("measured_at") if not egv.empty else egv
    egv_t = pd.to_datetime(egv["measured_at"]) if not egv.empty else pd.Series([], dtype="datetime64[ns]")
    egv_y = egv["glucose_mgdl"].to_numpy(dtype=float) if not egv.empty else np.array([], dtype=float)

    rows: List[Dict] = []

    meals = meals.sort_values("eaten_at")
    eaten_times = pd.to_datetime(meals["eaten_at"]).to_list()

    for idx, m in meals.iterrows():
        meal_time: datetime = pd.to_datetime(m["eaten_at"]).to_pydatetime()

        # slice EGV readings in [-pre_context, +post]
        if egv.empty:
            minutes_rel = np.array([], dtype=float)
            glucose = np.array([], dtype=float)
        else:
            dt_minutes = (egv_t - pd.Timestamp(meal_time)).dt.total_seconds().to_numpy(dtype=float) / 60.0
            mask = (dt_minutes >= -cfg.pre_context_minutes) & (dt_minutes <= cfg.post_minutes)
            minutes_rel = dt_minutes[mask]
            glucose = egv_y[mask]

        feat = {}
        feat.update(compute_time_features(meal_time))

        # meal macros already included in meals df
        for col in meals.columns:
            if col.startswith("meal_"):
                feat[col] = float(m[col]) if pd.notna(m[col]) else float("nan")

        feat.update(compute_glucose_context_features(minutes_rel, glucose, cfg))
        feat.update(compute_activity_features(meal_time, workouts, exercise_sets, cfg))

        # time since previous meal (minutes)
        if idx == meals.index[0]:
            feat["minutes_since_prev_meal"] = float("nan")
        else:
            prev_time = pd.to_datetime(meals.loc[meals.index[meals.index.get_loc(idx) - 1], "eaten_at"]).to_pydatetime()
            feat["minutes_since_prev_meal"] = float((meal_time - prev_time).total_seconds() / 60.0)

        targ = compute_targets(minutes_rel, glucose, cfg)

        rows.append({
            "meal_event_id": int(m["meal_event_id"]),
            "eaten_at": meal_time,
            **feat,
            **targ,
            "egv_points_in_window": int(len(glucose)),
        })

    return pd.DataFrame(rows)

