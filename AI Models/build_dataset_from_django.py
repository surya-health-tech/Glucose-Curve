from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from glucose_ml.config import MealWindowConfig
from glucose_ml.dataset import build_meal_dataset
from glucose_ml.django_setup import setup_django
from glucose_ml.orm_extract import extract_for_meal_dataset


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    # Accept YYYY-MM-DD or full ISO datetime
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        # try date-only
        dt = datetime.fromisoformat(value.strip() + "T00:00:00")
    return dt


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a meal-centered ML dataset from Django DB.")
    ap.add_argument("--out", required=True, help="Output CSV path")
    ap.add_argument("--start", default=None, help="Filter meals eaten_at >= start (YYYY-MM-DD or ISO datetime)")
    ap.add_argument("--end", default=None, help="Filter meals eaten_at < end (YYYY-MM-DD or ISO datetime)")
    args = ap.parse_args()

    setup_django()

    cfg = MealWindowConfig()
    start = _parse_date(args.start)
    end = _parse_date(args.end)

    extracted = extract_for_meal_dataset(cfg=cfg, start=start, end=end)
    ds = build_meal_dataset(
        meals=extracted["meals"],
        egv=extracted["egv"],
        workouts=extracted["workouts"],
        exercise_sets=extracted["exercise_sets"],
        cfg=cfg,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_csv(out_path, index=False)

    print(f"Wrote {len(ds)} meals -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

