# Glucose Curve ML (baseline)

This folder contains a simple, meal-centered baseline pipeline to predict **post-meal glucose** outcomes:
- **peak** (mg/dL)
- **incremental_auc** (mg/dL * minutes)
- **slope** (mg/dL per minute)

It uses your Django tables:
- `core.EGVReading` (CGM)
- `core.MealEvent` + `core.MealEventItem` + `core.FoodItem` (meal + macros)
- `core.Workout` and `core.ExerciseSet` (activity)

## Install (in your backend venv)

On Windows, either activate your venv:

```bash
backend\venv\Scripts\activate
```

…or run with the venv python directly:

```bash
backend\venv\Scripts\python -m pip install -r "AI Models/requirements-ml.txt"
```

```bash
pip install -r "AI Models/requirements-ml.txt"
```

## 1) Build a training dataset from your Django DB

Exports a CSV with one row per `MealEvent` and computed features + targets.

```bash
python "AI Models/build_dataset_from_django.py" --out "AI Models/artifacts/meal_dataset.csv"
```

Optional filters:

```bash
python "AI Models/build_dataset_from_django.py" --out "AI Models/artifacts/meal_dataset.csv" --start 2025-01-01 --end 2026-01-01
```

## 2) Train a baseline model

Trains 3 regressors (one per target) and saves a single artifact.

```bash
python "AI Models/train_scalar_model.py" --data "AI Models/artifacts/meal_dataset.csv" --out "AI Models/artifacts/scalar_model.joblib"
```

## 3) Predict for a MealEvent (from DB)

```bash
python "AI Models/predict_meal_from_django.py" --model "AI Models/artifacts/scalar_model.joblib" --meal-event-id 123
```

## Notes / knobs
- Time windows and resampling are configured in `glucose_ml/config.py`.
- Targets are computed in `glucose_ml/targets.py`.
- Features are computed in `glucose_ml/features.py`.
