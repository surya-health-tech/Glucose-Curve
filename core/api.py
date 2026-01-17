import uuid
import logging  # Added logging import
import traceback # Added traceback for detailed error logs
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from core.models import (
    EGVReading,
    Workout,
    MealEvent,
    MealEventItem,
    FoodItem,
    MealTemplate,
    MealTemplateItem,
    SyncRun,
    MedicationOption,
    MedicationEvent,
    WeightReading,
    SleepSession,
    HealthMetric,
    ExerciseSet,
    ExerciseTemplate,
)

# 1. Initialize Logger
logger = logging.getLogger(__name__)

# -------------------------
# Helpers
# -------------------------

def _parse_dt(value: str, field_name: str):
    """
    Parse ISO-8601 datetime. Ensures timezone-aware.
    """
    dt = parse_datetime(value) if value else None
    if dt is None:
        raise ValueError(f"Invalid datetime for '{field_name}': {value}")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except Exception:
        raise ValueError(f"Invalid UUID for '{field_name}': {value}")


# -------------------------
# Reference endpoints (phone reads these)
# -------------------------

@api_view(["GET"])
def food_items(request):
    qs = FoodItem.objects.all().order_by("name")
    data = [
        {
            "id": fi.id,
            "name": fi.name,
            "brand": fi.brand,
            "notes": fi.notes,
            "serving_name": fi.serving_name,
            "serving_grams": str(fi.serving_grams),
            "calories_kcal": str(fi.calories_kcal),
            "carbs_g": str(fi.carbs_g),
            "fiber_g": str(fi.fiber_g),
            "protein_g": str(fi.protein_g),
            "fat_g": str(fi.fat_g),
            "updated_at": fi.updated_at.isoformat() if fi.updated_at else None,
        }
        for fi in qs
    ]
    return Response({"ok": True, "food_items": data})


@api_view(["GET"])
def meal_templates(request):
    qs = (
        MealTemplate.objects.all()
        .order_by("name")
        .prefetch_related("items__food_item")
    )

    out = []
    for mt in qs:
        items = []
        for it in mt.items.all().order_by("sort_order", "id"):
            fi = it.food_item
            items.append(
                {
                    "id": it.id,
                    "food_item_id": fi.id,
                    "food_item_name": fi.name,
                    "grams": str(it.grams),
                    "sort_order": it.sort_order,
                }
            )

        out.append(
            {
                "id": mt.id,
                "name": mt.name,
                "notes": mt.notes,
                "updated_at": mt.updated_at.isoformat() if mt.updated_at else None,
                "items": items,
            }
        )

    return Response({"ok": True, "meal_templates": out})


@api_view(["GET"])
def exercise_templates(request):
    """
    Returns a list of all exercise templates for the mobile app quick-log picker.
    """
    qs = ExerciseTemplate.objects.all().order_by("name")
    data = [
        {
            "id": ex.id,
            "name": ex.name,
            "default_reps": ex.default_reps,
            "default_weight_kg": str(ex.default_weight_kg),
            "notes": ex.notes,
        }
        for ex in qs
    ]
    return Response({"ok": True, "exercise_templates": data})


@api_view(["GET"])
def medication_options(request):
    qs = MedicationOption.objects.all().order_by("name", "dose_mg")
    data = [
        {
            "id": mo.id,
            "name": mo.name,
            "dose_mg": mo.dose_mg,
            "label": mo.label,
            "notes": mo.notes,
        }
        for mo in qs
    ]
    return Response({"ok": True, "medication_options": data})


@api_view(["GET"])
def ping(request):
    return Response({"ok": True, "message": "API is running"})


# -------------------------
# Single sync endpoint (phone POSTs everything since last upload)
# -------------------------

@api_view(["POST"])
def sync(request):
    payload = request.data or {}
    device = payload.get("device", "iphone")
    notes = payload.get("notes")

    # 2. Log incoming sync attempt
    logger.info(f"Starting sync for device: {device}")
    
    # Extract standard payloads
    egvs = payload.get("egv_readings", []) or []
    workouts = payload.get("workouts", []) or []
    weights = payload.get("weight_readings", []) or []
    meals = payload.get("meal_events", []) or []
    meds = payload.get("medication_events", []) or []

    # Extract new payloads
    sleeps = payload.get("sleep_sessions", []) or []
    metrics = payload.get("health_metrics", []) or []
    sets = payload.get("exercise_sets", []) or []

    counts = {
        "egv_upserted": 0,
        "workouts_upserted": 0,
        "weights_upserted": 0,
        "meal_events_upserted": 0,
        "medication_events_upserted": 0,
        "sleep_sessions_upserted": 0,
        "health_metrics_upserted": 0,
        "exercise_sets_upserted": 0,
    }

    try:
        with transaction.atomic():
            SyncRun.objects.create(device=device, notes=notes)

            # 1. EGV readings
            for r in egvs:
                measured_at = _parse_dt(r.get("measured_at"), "measured_at")
                source = r.get("source", "healthkit")
                source_id = r.get("source_id")
                defaults = {
                    "measured_at": measured_at, "glucose_mgdl": r.get("glucose_mgdl"),
                    "source": source, "source_id": source_id,
                }
                if source_id:
                    EGVReading.objects.update_or_create(source=source, source_id=str(source_id), defaults=defaults)
                else:
                    EGVReading.objects.update_or_create(measured_at=measured_at, source=source, defaults=defaults)
                counts["egv_upserted"] += 1

            # 2. Workouts
            for w in workouts:
                start_at = _parse_dt(w.get("start_at"), "start_at")
                end_at = _parse_dt(w.get("end_at"), "end_at")
                source_id = w.get("source_id")
                defaults = {
                    "start_at": start_at, "end_at": end_at,
                    "activity_type": w.get("activity_type"), "duration_min": w.get("duration_min", 0),
                    "source": w.get("source", "healthkit"), "source_id": source_id,
                }
                if source_id:
                    Workout.objects.update_or_create(source=defaults["source"], source_id=str(source_id), defaults=defaults)
                else:
                    Workout.objects.update_or_create(start_at=start_at, end_at=end_at, activity_type=w.get("activity_type"), defaults=defaults)
                counts["workouts_upserted"] += 1

            # 3. Sleep Sessions
            for s in sleeps:
                start_at = _parse_dt(s.get("start_at"), "start_at")
                end_at = _parse_dt(s.get("end_at"), "end_at")
                source_id = s.get("source_id")
                defaults = {
                    "start_at": start_at, "end_at": end_at,
                    "stage": s.get("stage"), "source": s.get("source", "healthkit"),
                    "source_id": source_id
                }
                if source_id:
                    SleepSession.objects.update_or_create(source=defaults["source"], source_id=str(source_id), defaults=defaults)
                else:
                    SleepSession.objects.update_or_create(start_at=start_at, end_at=end_at, stage=s.get("stage"), defaults=defaults)
                counts["sleep_sessions_upserted"] += 1

            # 4. Health Metrics
            for h in metrics:
                measured_at = _parse_dt(h.get("measured_at"), "measured_at")
                source_id = h.get("source_id")
                defaults = {
                    "measured_at": measured_at, "metric_type": h.get("metric_type"),
                    "value": h.get("value"), "unit": h.get("unit"),
                    "source": h.get("source", "healthkit"), "source_id": source_id
                }
                if source_id:
                    HealthMetric.objects.update_or_create(source=defaults["source"], source_id=str(source_id), defaults=defaults)
                else:
                    HealthMetric.objects.update_or_create(measured_at=measured_at, metric_type=h.get("metric_type"), defaults=defaults)
                counts["health_metrics_upserted"] += 1

           # 5. Exercise Sets
            for ex in sets:
                performed_at = _parse_dt(ex.get("performed_at"), "performed_at")
                
                # Check for client_uuid to avoid database errors if missing
                c_uuid = ex.get("client_uuid")
                if not c_uuid:
                    logger.warning(f"Skipping ExerciseSet: missing client_uuid in payload item: {ex}")
                    continue

                ExerciseSet.objects.update_or_create(
                    client_uuid=c_uuid,
                    defaults={
                        "performed_at": performed_at,
                        "template_id": ex.get("template_id"),
                        "name": ex.get("name"),
                        "reps": ex.get("reps"),
                        "weight_kg": ex.get("weight_kg", 0),
                        "source": ex.get("source", "manual")
                    }
                )
                counts["exercise_sets_upserted"] += 1

            # 6. Weight Readings
            for wr in weights:
                measured_at = _parse_dt(wr.get("measured_at"), "measured_at")
                source_id = wr.get("source_id")
                defaults = {
                    "measured_at": measured_at, "weight_kg": wr.get("weight_kg"),
                    "source": wr.get("source", "healthkit"), "source_id": source_id,
                    "notes": wr.get("notes"),
                }
                if source_id:
                    WeightReading.objects.update_or_create(source=defaults["source"], source_id=str(source_id), defaults=defaults)
                else:
                    WeightReading.objects.update_or_create(measured_at=measured_at, source=defaults["source"], defaults=defaults)
                counts["weights_upserted"] += 1

            # 7. Meal events
            for m in meals:
                client_uuid = _parse_uuid(m.get("client_uuid"), "client_uuid")
                eaten_at = _parse_dt(m.get("eaten_at"), "eaten_at")
                me, _ = MealEvent.objects.update_or_create(
                    client_uuid=client_uuid,
                    defaults={"eaten_at": eaten_at, "meal_template_id": m.get("meal_template_id"), "notes": m.get("notes")},
                )
                items = m.get("items", []) or []
                MealEventItem.objects.filter(meal_event=me).delete()
                bulk = [MealEventItem(meal_event=me, food_item_id=it.get("food_item_id"), grams=it.get("grams"), sort_order=it.get("sort_order", idx)) for idx, it in enumerate(items)]
                if bulk:
                    MealEventItem.objects.bulk_create(bulk, ignore_conflicts=True)
                counts["meal_events_upserted"] += 1

            # 8. Medication events
            for e in meds:
                client_uuid = _parse_uuid(e.get("client_uuid"), "client_uuid")
                taken_at = _parse_dt(e.get("taken_at"), "taken_at")
                MedicationEvent.objects.update_or_create(
                    client_uuid=client_uuid,
                    defaults={"taken_at": taken_at, "option_id": e.get("option_id") or e.get("medication_option_id"), "notes": e.get("notes")},
                )
                counts["medication_events_upserted"] += 1

        logger.info(f"Sync successful. Results: {counts}") # Log success
        return Response({"ok": True, "counts": counts, "server_time": timezone.now().isoformat()})

    except ValueError as ve:
        logger.error(f"Validation error during sync: {str(ve)}") # Log validation errors
        return Response({"ok": False, "error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as ex:
        # 3. Log the full traceback for 500 errors
        logger.error("CRITICAL SYNC ERROR:")
        logger.error(traceback.format_exc())
        return Response({"ok": False, "error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)