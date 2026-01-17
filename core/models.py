from django.db import models
from django.db.models import Q
import uuid



# -------------------------
# Reference / templates
# -------------------------

class FoodItem(models.Model):
    name = models.TextField(unique=True)
    brand = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    # macros stored per serving
    serving_name = models.TextField(default="serving")
    serving_grams = models.DecimalField(max_digits=10, decimal_places=2, default=1)  # >0

    calories_kcal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    carbs_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fiber_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    protein_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fat_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "food_items"

    def __str__(self):
        return self.name


class MealTemplate(models.Model):
    name = models.TextField(unique=True)
    notes = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "meal_templates"

    def __str__(self):
        return self.name


class MealTemplateItem(models.Model):
    meal_template = models.ForeignKey(MealTemplate, on_delete=models.CASCADE, related_name="items")
    food_item = models.ForeignKey(FoodItem, on_delete=models.PROTECT, related_name="template_items")

    grams = models.DecimalField(max_digits=10, decimal_places=2)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "meal_template_items"
        constraints = [
            models.UniqueConstraint(
                fields=["meal_template", "food_item"],
                name="uniq_meal_template_food_item",
            )
        ]
        indexes = [
            models.Index(fields=["meal_template"]),
        ]

    def __str__(self):
        return f"{self.meal_template} - {self.food_item} ({self.grams}g)"


# -------------------------
# Logged events (from phone)
# -------------------------

class MealEvent(models.Model):
    """
    What you logged: selected a template at a time.
    client_uuid ensures idempotent sync from phone.
    """
    client_uuid = models.UUIDField(unique=True)  # generated on phone once per event

    eaten_at = models.DateTimeField()
    meal_template = models.ForeignKey(MealTemplate, null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meal_events"
        indexes = [
            models.Index(fields=["eaten_at"]),
        ]

    def __str__(self):
        return f"Meal @ {self.eaten_at}"


class MealEventItem(models.Model):
    """
    Snapshot of what was eaten for that meal event.
    We enforce unique (meal_event, food_item) to avoid duplicate rows on repeated sync.
    """
    meal_event = models.ForeignKey(MealEvent, on_delete=models.CASCADE, related_name="items")
    food_item = models.ForeignKey(FoodItem, on_delete=models.PROTECT, related_name="meal_event_items")

    grams = models.DecimalField(max_digits=10, decimal_places=2)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "meal_event_items"
        constraints = [
            models.UniqueConstraint(
                fields=["meal_event", "food_item"],
                name="uniq_meal_event_food_item",
            )
        ]
        indexes = [
            models.Index(fields=["meal_event"]),
        ]

    def __str__(self):
        return f"{self.meal_event_id} - {self.food_item} ({self.grams}g)"


# -------------------------
# HealthKit / sensor data
# -------------------------

class EGVReading(models.Model):
    """
    Use (source, source_id) for perfect dedupe.
    source_id should be HKSample UUID string for HealthKit.
    """
    measured_at = models.DateTimeField()
    glucose_mgdl = models.DecimalField(max_digits=10, decimal_places=2)

    source = models.TextField(default="healthkit")
    source_id = models.TextField(null=True, blank=True)  # HKSample UUID

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "egv_readings"
        indexes = [
            models.Index(fields=["measured_at"]),
        ]
        constraints = [
            # If source_id present, enforce unique per source_id
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=Q(source_id__isnull=False),
                name="uniq_egv_source_sourceid",
            ),
            # Fallback uniqueness if no source_id (optional)
            models.UniqueConstraint(
                fields=["measured_at", "source"],
                name="uniq_egv_measured_at_source",
            ),
        ]

    def __str__(self):
        return f"{self.glucose_mgdl} mg/dL @ {self.measured_at}"


class Workout(models.Model):
    """
    Use (source, source_id) for dedupe if available (HealthKit workout UUID).
    """
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    activity_type = models.TextField()

    duration_min = models.DecimalField(max_digits=10, decimal_places=2)
    distance_miles = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    avg_hr_bpm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    active_energy_kcal = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    source = models.TextField(default="healthkit")
    source_id = models.TextField(null=True, blank=True)  # HKWorkout UUID

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "workouts"
        indexes = [
            models.Index(fields=["start_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=Q(source_id__isnull=False),
                name="uniq_workout_source_sourceid",
            ),
            # Fallback uniqueness if no source_id
            models.UniqueConstraint(
                fields=["start_at", "end_at", "activity_type", "source"],
                name="uniq_workout_session",
            ),
        ]

    def __str__(self):
        return f"{self.activity_type} @ {self.start_at}"


class WeightReading(models.Model):
    """
    Weight from HealthKit or manual.
    Use (source, source_id) if available; else fallback (measured_at, source).
    Store kg internally.
    """
    measured_at = models.DateTimeField()
    weight_kg = models.FloatField()

    source = models.CharField(max_length=40, default="healthkit")  # healthkit/manual
    source_id = models.TextField(null=True, blank=True)            # HKSample UUID if from HealthKit
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "weight_readings"
        indexes = [models.Index(fields=["measured_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=Q(source_id__isnull=False),
                name="uniq_weight_source_sourceid",
            ),
            models.UniqueConstraint(
                fields=["measured_at", "source"],
                name="uniq_weight_measured_at_source",
            ),
        ]

    def __str__(self):
        return f"{self.weight_kg:.2f} kg @ {self.measured_at}"


# -------------------------
# Medications (quick picks + events)
# -------------------------

class MedicationOption(models.Model):
    """
    Admin-created presets the phone can show as quick picks.
    """
    name = models.CharField(max_length=100)  # "Metformin"
    dose_mg = models.IntegerField()          # 1000, 500
    label = models.CharField(max_length=120, unique=True)  # "Metformin 1000 mg (Afternoon)"
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "medication_options"

    def __str__(self):
        return self.label


class MedicationEvent(models.Model):
    """
    What you actually took and when.
    client_uuid ensures idempotent sync from phone.
    """
    client_uuid = models.UUIDField(unique=True)

    taken_at = models.DateTimeField()
    option = models.ForeignKey(MedicationOption, on_delete=models.PROTECT, related_name="events")
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "medication_events"
        indexes = [models.Index(fields=["taken_at"])]

    def __str__(self):
        return f"{self.option.label} @ {self.taken_at}"

# -------------------------
# Sleep & Restorative Data
# -------------------------

class SleepSession(models.Model):
    """
    Tracks duration-based sleep intervals.
    Apple HealthKit maps this to HKCategoryTypeIdentifierSleepAnalysis.
    Stages: "InBed", "AsleepCore", "AsleepDeep", "AsleepREM", "Awake"
    """
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    
    # Stores the sleep stage (e.g., "Deep", "REM", "Core")
    stage = models.TextField() 

    source = models.TextField(default="healthkit")
    source_id = models.TextField(null=True, blank=True)  # UUID from HKCategorySample

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sleep_sessions"
        indexes = [
            models.Index(fields=["start_at"]),
            models.Index(fields=["end_at"]),
        ]
        constraints = [
            # Dedupe based on HK UUID
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=Q(source_id__isnull=False),
                name="uniq_sleep_source_sourceid",
            ),
            # Fallback dedupe if no UUID available
            models.UniqueConstraint(
                fields=["start_at", "end_at", "stage", "source"],
                name="uniq_sleep_session",
            ),
        ]

    def __str__(self):
        return f"{self.stage} ({self.start_at} - {self.end_at})"


class HealthMetric(models.Model):
    """
    Generic table for point-in-time restorative metrics.
    metric_type examples: "HRV", "RestingHR", "RespiratoryRate", "WristTemp"
    """
    measured_at = models.DateTimeField()
    
    metric_type = models.TextField()  
    value = models.DecimalField(max_digits=10, decimal_places=4) # Precision for HRV (ms) or Temp
    unit = models.CharField(max_length=50) # "ms", "count/min", "degC"

    source = models.TextField(default="healthkit")
    source_id = models.TextField(null=True, blank=True) # UUID from HKQuantitySample

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "health_metrics"
        indexes = [
            models.Index(fields=["measured_at"]),
            models.Index(fields=["metric_type"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=Q(source_id__isnull=False),
                name="uniq_metric_source_sourceid",
            ),
            models.UniqueConstraint(
                fields=["measured_at", "metric_type", "source"],
                name="uniq_metric_measure_type_source",
            ),
        ]

    def __str__(self):
        return f"{self.metric_type}: {self.value} {self.unit} @ {self.measured_at}"
    

class ExerciseSet(models.Model):
    # ADD THIS LINE: generated on phone once per event to ensure idempotent sync
    client_uuid = models.UUIDField(unique=True, null=True, blank=True) 

    template = models.ForeignKey(
        'ExerciseTemplate', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="sets"
    )
    
    performed_at = models.DateTimeField()
    name = models.CharField(max_length=100) 
    reps = models.IntegerField()
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    source = models.CharField(max_length=40, default="manual")

    class Meta:
        db_table = "exercise_sets"
        indexes = [
            models.Index(fields=["performed_at"]),
            models.Index(fields=["client_uuid"]), # Optional: speed up lookups
        ]

    def __str__(self):
        return f"{self.name} - {self.reps} reps @ {self.performed_at}"

    


class ExerciseTemplate(models.Model):
    """
    Templates for quick-logging common exercises (Pushups, Squats, etc.)
    """
    name = models.CharField(max_length=100, unique=True)
    default_reps = models.IntegerField(default=0)
    default_weight_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "exercise_templates"

    def __str__(self):
        return self.name

# -------------------------
# Sync bookkeeping
# -------------------------

class SyncRun(models.Model):
    ran_at = models.DateTimeField(auto_now_add=True)
    device = models.TextField(default="iphone")
    notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "sync_runs"

    def __str__(self):
        return f"sync @ {self.ran_at} ({self.device})"
