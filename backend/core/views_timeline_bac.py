from __future__ import annotations

from datetime import datetime, timedelta, time as dtime
from typing import Optional, Tuple

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.models import (
    EGVReading,
    Workout,
    MealEvent,
    MealEventItem,
    MedicationEvent,
    WeightReading,
    SleepSession,
    HealthMetric,
    ExerciseSet,
)

# --------------------------
# Helpers
# --------------------------

def _parse_date_yyyy_mm_dd(date_str: str) -> datetime.date:
    # Expect "YYYY-MM-DD"
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _parse_start_time_hhmm(start_time_str: str) -> dtime:
    # Expect "HH:MM"
    return datetime.strptime(start_time_str, "%H:%M").time()

def _window_for(
    date_str: Optional[str],
    hours: int,
    start_time_str: Optional[str],
) -> Tuple[datetime, datetime, str]:
    """
    Returns (start, end, time_echo). 
    If a time is provided, it acts as the END of the window.
    """
    tz = timezone.get_current_timezone()
    now = timezone.localtime(timezone.now(), tz)

    # 1. Base Date Selection
    if date_str:
        day = _parse_date_yyyy_mm_dd(date_str)
    else:
        day = now.date()

    # 2. Determine the Anchor (End Time)
    if start_time_str:
        # Use specific time on the selected day as the END point
        t = _parse_start_time_hhmm(start_time_str)
        end_naive = datetime.combine(day, t)
        end = timezone.make_aware(end_naive, tz)
    else:
        # Default behavior: End at now if today, or end of day if past
        if day == now.date():
            end = now
        else:
            end_naive = datetime.combine(day, dtime(23, 59, 59))
            end = timezone.make_aware(end_naive, tz)

    # 3. Calculate Start by looking back from the end anchor
    start = end - timedelta(hours=hours)
    
    return start, end, start_time_str or ""


def _iso(dt: datetime) -> str:
    # Always return in local timezone for consistent UI
    return timezone.localtime(dt).isoformat()


# --------------------------
# API endpoint
# --------------------------

@require_GET
def timeline(request):
    """
    GET /api/timeline/?date=YYYY-MM-DD&range_hours=6&start_time=HH:MM

    - date: optional; if omitted, returns last N hours ending now
    - range_hours: 3|6|12|24 (default 6)
    - start_time: optional "HH:MM" for fixed window end anchor within that date
    """
    date_str = request.GET.get("date") or None
    start_time_str = request.GET.get("start_time") or None
    try:
        range_hours = int(request.GET.get("range_hours", "6"))
    except ValueError:
        range_hours = 6

    try:
        # Updated to use the look-back logic
        start, end, start_time_echo = _window_for(date_str, range_hours, start_time_str)
    except Exception as ex:
        return JsonResponse({"ok": False, "error": f"Bad date/start_time: {ex}"}, status=400)

    # --------------------------
    # 1. EGV readings in window
    # --------------------------
    egv_qs = (
        EGVReading.objects
        .filter(measured_at__gte=start, measured_at__lt=end)
        .order_by("measured_at")
        .values("measured_at", "glucose_mgdl")
    )
    egv = [{"t": _iso(r["measured_at"]), "y": float(r["glucose_mgdl"])} for r in egv_qs]

    # --------------------------
    # 2. Workouts overlapping window
    # --------------------------
    workouts_qs = (
        Workout.objects
        .filter(start_at__lt=end, end_at__gt=start)
        .order_by("start_at")
        .values(
            "start_at", "end_at", "activity_type", "duration_min",
            "distance_miles", "avg_hr_bpm", "active_energy_kcal"
        )
    )

    workouts = []
    for w in workouts_qs:
        workouts.append({
            "start_at": _iso(w["start_at"]),
            "end_at": _iso(w["end_at"]),
            "activity_type": w["activity_type"],
            "duration_min": float(w["duration_min"]),
            "distance_miles": (float(w["distance_miles"]) if w["distance_miles"] is not None else None),
            "avg_hr_bpm": (float(w["avg_hr_bpm"]) if w["avg_hr_bpm"] is not None else None),
            "active_energy_kcal": (float(w["active_energy_kcal"]) if w["active_energy_kcal"] is not None else None),
        })

    # --------------------------
    # 3. Sleep Sessions overlapping window
    # --------------------------
    sleep_qs = (
        SleepSession.objects
        .filter(start_at__lt=end, end_at__gt=start)
        .order_by("start_at")
    )
    sleep = [{
        "start": _iso(s.start_at),
        "end": _iso(s.end_at),
        "stage": s.stage
    } for s in sleep_qs]

    # --------------------------
    # 4. Health Metrics (HRV, Respiratory, etc.)
    # --------------------------
    metrics_qs = (
        HealthMetric.objects
        .filter(measured_at__gte=start, measured_at__lt=end)
        .order_by("measured_at")
    )
    metrics = [{
        "t": _iso(m.measured_at),
        "type": m.metric_type,
        "value": float(m.value),
        "unit": m.unit
    } for m in metrics_qs]

    # --------------------------
    # 5. Exercise Sets (e.g., Pushups)
    # --------------------------
    sets_qs = (
        ExerciseSet.objects
        .filter(performed_at__gte=start, performed_at__lt=end)
        .order_by("performed_at")
    )
    exercise_sets = [{
        "t": _iso(ex.performed_at),
        "name": ex.name,
        "reps": ex.reps,
        "weight_kg": ex.weight_kg
    } for ex in sets_qs]

    # --------------------------
    # 6. Meals in window + totals for popup
    # --------------------------
    meal_events = (
        MealEvent.objects
        .filter(eaten_at__gte=start, eaten_at__lt=end)
        .select_related("meal_template")
        .order_by("eaten_at")
    )

    meal_items = (
        MealEventItem.objects
        .filter(meal_event__in=meal_events)
        .select_related("meal_event", "food_item")
        .order_by("sort_order", "id")
    )

    items_by_event = {}
    for it in meal_items:
        items_by_event.setdefault(it.meal_event_id, []).append(it)

    meals_out = []
    for m in meal_events:
        items = items_by_event.get(m.id, [])

        total_carbs = 0.0
        total_kcal = 0.0

        items_out = []
        for it in items:
            fi = it.food_item
            grams = float(it.grams)
            sg = float(fi.serving_grams) if fi.serving_grams else 0.0
            factor = (grams / sg) if sg > 0 else 0.0

            carbs = float(fi.carbs_g) * factor
            kcal = float(fi.calories_kcal) * factor

            total_carbs += carbs
            total_kcal += kcal

            items_out.append({
                "food_item_id": fi.id,
                "food_item_name": fi.name,
                "grams": grams,
                "sort_order": it.sort_order,
            })

        meals_out.append({
            "eaten_at": _iso(m.eaten_at),
            "meal_template_id": m.meal_template_id,
            "meal_template_name": (m.meal_template.name if m.meal_template else ""),
            "notes": m.notes or "",
            "total_carbs_g": round(total_carbs, 2),
            "total_calories_kcal": round(total_kcal, 2),
            "items": items_out,
        })

    # --------------------------
    # 7. Medications in window
    # --------------------------
    meds_qs = (
        MedicationEvent.objects
        .filter(taken_at__gte=start, taken_at__lt=end)
        .select_related("option")
        .order_by("taken_at")
    )

    medications = [{
        "taken_at": _iso(e.taken_at),
        "label": e.option.label,
        "name": e.option.name,
        "dose_mg": e.option.dose_mg,
        "notes": e.notes or "",
    } for e in meds_qs]

    # --------------------------
    # 8. Weights in window
    # --------------------------
    weights_qs = (
        WeightReading.objects
        .filter(measured_at__gte=start, measured_at__lt=end)
        .order_by("measured_at")
        .values("measured_at", "weight_kg", "source")
    )
    weights = [{"t": _iso(r["measured_at"]), "kg": float(r["weight_kg"]), "source": r["source"]} for r in weights_qs]

    return JsonResponse({
        "ok": True,
        "start": _iso(start),
        "end": _iso(end),
        "range_hours": range_hours,
        "start_time": start_time_echo,
        "egv": egv,
        "workouts": workouts,
        "sleep": sleep,
        "metrics": metrics,
        "exercise_sets": exercise_sets,
        "meals": meals_out,
        "medications": medications,
        "weights": weights,
    })