from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


DEFAULT_TARGETS = [
    "peak_inc_mgdl",
    "incremental_auc_mgdl_min",
    "slope_0_60_mgdl_per_min",
]


def _pick_feature_columns(df: pd.DataFrame, targets: List[str]) -> List[str]:
    drop = set(["meal_event_id", "eaten_at", "egv_points_in_window"]) | set(targets)
    cols = []
    for c in df.columns:
        if c in drop:
            continue
        # only numeric
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
    return cols


def _time_split(df: pd.DataFrame, test_frac: float = 0.2):
    df = df.sort_values("eaten_at")
    n = len(df)
    cut = int(max(1, (1.0 - test_frac) * n))
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()


def main() -> int:
    ap = argparse.ArgumentParser(description="Train baseline scalar model(s) for meal response.")
    ap.add_argument("--data", required=True, help="CSV created by build_dataset_from_django.py")
    ap.add_argument("--out", required=True, help="Output .joblib path")
    ap.add_argument("--test-frac", type=float, default=0.2, help="Holdout fraction (time-based)")
    ap.add_argument("--targets", nargs="*", default=DEFAULT_TARGETS, help="Target columns to train")
    args = ap.parse_args()

    df = pd.read_csv(args.data, parse_dates=["eaten_at"])
    targets = list(args.targets)

    # keep only rows with all targets present
    mask = np.ones(len(df), dtype=bool)
    for t in targets:
        if t not in df.columns:
            raise SystemExit(f"Missing target column: {t}")
        mask &= pd.to_numeric(df[t], errors="coerce").notna().to_numpy()
    df = df.loc[mask].copy()

    if len(df) < 20:
        raise SystemExit(f"Not enough labeled meals to train: {len(df)} rows after filtering.")

    feat_cols = _pick_feature_columns(df, targets)
    if not feat_cols:
        raise SystemExit("No numeric feature columns found.")

    train_df, test_df = _time_split(df, test_frac=float(args.test_frac))

    X_train = train_df[feat_cols].to_numpy(dtype=float)
    X_test = test_df[feat_cols].to_numpy(dtype=float)

    models: Dict[str, HistGradientBoostingRegressor] = {}
    metrics: Dict[str, Dict[str, float]] = {}

    for t in targets:
        y_train = pd.to_numeric(train_df[t], errors="coerce").to_numpy(dtype=float)
        y_test = pd.to_numeric(test_df[t], errors="coerce").to_numpy(dtype=float)

        model = HistGradientBoostingRegressor(
            max_depth=6,
            learning_rate=0.05,
            max_iter=400,
            random_state=42,
        )
        model.fit(X_train, y_train)
        pred = model.predict(X_test)

        metrics[t] = {
            "mae": float(mean_absolute_error(y_test, pred)),
            "rmse": float(mean_squared_error(y_test, pred, squared=False)),
            "r2": float(r2_score(y_test, pred)),
            "n_train": float(len(train_df)),
            "n_test": float(len(test_df)),
        }
        models[t] = model

    artifact = {
        "feature_columns": feat_cols,
        "targets": targets,
        "models": models,
        "metrics": metrics,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, out_path)

    print(f"Saved model -> {out_path}")
    for t in targets:
        m = metrics[t]
        print(f"{t}: MAE={m['mae']:.3f} RMSE={m['rmse']:.3f} R2={m['r2']:.3f} (n_test={int(m['n_test'])})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

