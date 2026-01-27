from __future__ import annotations

from datetime import datetime, timedelta, time as dtime
from typing import Optional, Tuple, List, Dict
import math

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.models import EGVReading, MealEvent
from core.views_timeline import _window_for, _iso, _parse_date_yyyy_mm_dd, _parse_start_time_hhmm


def calculate_time_in_range(egv_readings: List[Dict], range_min: float = 70.0, range_max: float = 180.0) -> Dict:
    """Calculate Time in Range (TIR) - percentage of time glucose is within target range."""
    if len(egv_readings) < 2:
        return {"percentage": 0.0, "minutes_in_range": 0, "total_minutes": 0}
    
    total_time_minutes = 0
    time_in_range_minutes = 0
    
    for i in range(len(egv_readings) - 1):
        current = egv_readings[i]
        next_reading = egv_readings[i + 1]
        
        current_time = datetime.fromisoformat(current['t'].replace('Z', '+00:00'))
        next_time = datetime.fromisoformat(next_reading['t'].replace('Z', '+00:00'))
        
        time_diff = (next_time - current_time).total_seconds() / 60.0
        total_time_minutes += time_diff
        
        current_glucose = current['y']
        next_glucose = next_reading['y']
        
        # Check if both points are in range
        if range_min <= current_glucose <= range_max and range_min <= next_glucose <= range_max:
            time_in_range_minutes += time_diff
        # Check if partially in range (interpolate)
        elif (range_min <= current_glucose <= range_max) or (range_min <= next_glucose <= range_max):
            # Simple approximation: average the two values
            avg_glucose = (current_glucose + next_glucose) / 2.0
            if range_min <= avg_glucose <= range_max:
                time_in_range_minutes += time_diff
    
    percentage = (time_in_range_minutes / total_time_minutes * 100.0) if total_time_minutes > 0 else 0.0
    
    return {
        "percentage": round(percentage, 2),
        "minutes_in_range": round(time_in_range_minutes, 1),
        "total_minutes": round(total_time_minutes, 1),
        "range_min": range_min,
        "range_max": range_max
    }


def calculate_auc(egv_readings: List[Dict], baseline: float = 0.0) -> Dict:
    """Calculate Area Under Curve (AUC) using trapezoidal rule."""
    if len(egv_readings) < 2:
        return {"auc": 0.0, "units": "mg/dL * minutes"}
    
    total_auc = 0.0
    
    for i in range(len(egv_readings) - 1):
        current = egv_readings[i]
        next_reading = egv_readings[i + 1]
        
        current_time = datetime.fromisoformat(current['t'].replace('Z', '+00:00'))
        next_time = datetime.fromisoformat(next_reading['t'].replace('Z', '+00:00'))
        
        time_diff_minutes = (next_time - current_time).total_seconds() / 60.0
        current_glucose = current['y']
        next_glucose = next_reading['y']
        
        # Trapezoidal rule: area = (y1 + y2) / 2 * (x2 - x1)
        area = ((current_glucose + next_glucose) / 2.0 - baseline) * time_diff_minutes
        total_auc += area
    
    return {
        "auc": round(total_auc, 2),
        "units": "mg/dL * minutes"
    }


def calculate_iauc(egv_readings: List[Dict], baseline: Optional[float] = None) -> Dict:
    """Calculate Incremental Area Under Curve (IAUC) - area above baseline."""
    if len(egv_readings) < 2:
        return {"iauc": 0.0, "baseline": baseline or 0.0, "units": "mg/dL * minutes"}
    
    # Use first reading as baseline if not provided
    if baseline is None:
        baseline = egv_readings[0]['y']
    
    total_iauc = 0.0
    
    for i in range(len(egv_readings) - 1):
        current = egv_readings[i]
        next_reading = egv_readings[i + 1]
        
        current_time = datetime.fromisoformat(current['t'].replace('Z', '+00:00'))
        next_time = datetime.fromisoformat(next_reading['t'].replace('Z', '+00:00'))
        
        time_diff_minutes = (next_time - current_time).total_seconds() / 60.0
        current_glucose = current['y']
        next_glucose = next_reading['y']
        
        # Only count area above baseline
        current_above = max(0, current_glucose - baseline)
        next_above = max(0, next_glucose - baseline)
        
        # Trapezoidal rule for area above baseline
        area = ((current_above + next_above) / 2.0) * time_diff_minutes
        total_iauc += area
    
    return {
        "iauc": round(total_iauc, 2),
        "baseline": baseline,
        "units": "mg/dL * minutes"
    }


def calculate_gmi(egv_readings: List[Dict]) -> Dict:
    """Calculate Glucose Management Indicator (GMI) - estimated A1C from mean glucose."""
    if not egv_readings:
        return {"gmi": 0.0, "mean_glucose": 0.0, "estimated_a1c": 0.0}
    
    # Calculate mean glucose
    mean_glucose = sum(r['y'] for r in egv_readings) / len(egv_readings)
    
    # GMI formula: 3.31 + 0.02392 * mean_glucose_mgdl
    # This gives estimated A1C percentage
    gmi = 3.31 + (0.02392 * mean_glucose)
    
    return {
        "gmi": round(gmi, 2),
        "mean_glucose": round(mean_glucose, 1),
        "estimated_a1c": round(gmi, 2),
        "units": "%"
    }


def calculate_post_meal_peaks(egv_readings: List[Dict], meals: List[Dict], window_hours: float = 3.0) -> List[Dict]:
    """Calculate post-meal peak glucose for each meal."""
    if not meals or not egv_readings:
        return []
    
    peaks = []
    
    for meal in meals:
        meal_time = datetime.fromisoformat(meal['eaten_at'].replace('Z', '+00:00'))
        window_end = meal_time + timedelta(hours=window_hours)
        
        # Find EGV readings within the post-meal window
        window_readings = [
            r for r in egv_readings
            if meal_time <= datetime.fromisoformat(r['t'].replace('Z', '+00:00')) <= window_end
        ]
        
        if window_readings:
            peak_reading = max(window_readings, key=lambda x: x['y'])
            peak_time = datetime.fromisoformat(peak_reading['t'].replace('Z', '+00:00'))
            time_to_peak_minutes = (peak_time - meal_time).total_seconds() / 60.0
            
            peaks.append({
                "meal_time": _iso(meal_time),
                "meal_name": meal.get('meal_template_name', 'Unknown'),
                "peak_glucose": round(peak_reading['y'], 1),
                "peak_time": _iso(peak_time),
                "time_to_peak_minutes": round(time_to_peak_minutes, 1),
                "window_hours": window_hours
            })
    
    return peaks


@require_GET
def metrics(request):
    """
    GET /api/metrics/?date=YYYY-MM-DD&range_hours=24
    
    Returns EGV metrics:
    - Time in Range (TIR)
    - Area Under Curve (AUC)
    - Incremental Area Under Curve (IAUC)
    - Glucose Management Indicator (GMI)
    - Post-meal peak glucose
    """
    date_str = request.GET.get("date") or None
    start_time_str = request.GET.get("start_time") or None
    try:
        range_hours = int(request.GET.get("range_hours", "24"))
    except ValueError:
        range_hours = 24
    
    try:
        start, end, start_time_echo = _window_for(date_str, range_hours, start_time_str)
    except Exception as ex:
        return JsonResponse({"ok": False, "error": f"Bad date/start_time: {ex}"}, status=400)
    
    # Get EGV readings
    egv_qs = (
        EGVReading.objects
        .filter(measured_at__gte=start, measured_at__lt=end)
        .order_by("measured_at")
        .values("measured_at", "glucose_mgdl")
    )
    egv_readings = [{"t": _iso(r["measured_at"]), "y": float(r["glucose_mgdl"])} for r in egv_qs]
    
    # Get meals
    meal_events = (
        MealEvent.objects
        .filter(eaten_at__gte=start, eaten_at__lt=end)
        .select_related("meal_template")
        .order_by("eaten_at")
    )
    
    meals = [{
        "eaten_at": _iso(m.eaten_at),
        "meal_template_name": (m.meal_template.name if m.meal_template else "Unknown")
    } for m in meal_events]
    
    # Calculate metrics
    tir = calculate_time_in_range(egv_readings)
    auc = calculate_auc(egv_readings)
    iauc = calculate_iauc(egv_readings)
    gmi = calculate_gmi(egv_readings)
    post_meal_peaks = calculate_post_meal_peaks(egv_readings, meals)
    
    return JsonResponse({
        "ok": True,
        "start": _iso(start),
        "end": _iso(end),
        "range_hours": range_hours,
        "egv": egv_readings,
        "meals": meals,
        "metrics": {
            "time_in_range": tir,
            "area_under_curve": auc,
            "incremental_auc": iauc,
            "gmi": gmi,
            "post_meal_peaks": post_meal_peaks
        }
    })
