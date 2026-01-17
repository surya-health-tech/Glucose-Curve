from django.contrib import admin
from .models import FoodItem, MealTemplate, MealTemplateItem, MealEvent, MealEventItem, EGVReading, Workout
from .models import SleepSession, HealthMetric
from .models import ExerciseSet, ExerciseTemplate

@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = ("name", "serving_name", "serving_grams", "calories_kcal", "carbs_g", "fiber_g", "protein_g", "fat_g", "updated_at")
    search_fields = ("name",)
    list_filter = ()
    ordering = ("name",)


class MealTemplateItemInline(admin.TabularInline):
    model = MealTemplateItem
    extra = 1
    autocomplete_fields = ("food_item",)
    ordering = ("sort_order",)


@admin.register(MealTemplate)
class MealTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "updated_at")
    search_fields = ("name",)
    inlines = [MealTemplateItemInline]


@admin.register(MealEvent)
class MealEventAdmin(admin.ModelAdmin):
    list_display = ("eaten_at", "meal_template", "created_at")
    list_filter = ("meal_template",)
    search_fields = ("notes",)


@admin.register(EGVReading)
class EGVReadingAdmin(admin.ModelAdmin):
    list_display = ("measured_at", "glucose_mgdl", "source")
    list_filter = ("source",)
    ordering = ("-measured_at",)


@admin.register(Workout)
class WorkoutAdmin(admin.ModelAdmin):
    list_display = ("start_at", "activity_type", "duration_min", "distance_miles", "avg_hr_bpm", "active_energy_kcal", "source")
    list_filter = ("activity_type", "source")
    ordering = ("-start_at",)


# Optional: usually managed via MealEvent inline snapshots; keep visible if you want
@admin.register(MealTemplateItem)
class MealTemplateItemAdmin(admin.ModelAdmin):
    list_display = ("meal_template", "food_item", "grams", "sort_order")
    list_filter = ("meal_template",)


@admin.register(MealEventItem)
class MealEventItemAdmin(admin.ModelAdmin):
    list_display = ("meal_event", "food_item", "grams", "sort_order")
    list_filter = ("meal_event",)

from .models import MedicationOption, MedicationEvent, WeightReading

@admin.register(MedicationOption)
class MedicationOptionAdmin(admin.ModelAdmin):
    list_display = ("label", "name", "dose_mg", "created_at")
    search_fields = ("label", "name")

@admin.register(MedicationEvent)
class MedicationEventAdmin(admin.ModelAdmin):
    list_display = ("taken_at", "option", "created_at")
    list_filter = ("option__name",)
    search_fields = ("option__label",)

@admin.register(WeightReading)
class WeightReadingAdmin(admin.ModelAdmin):
    list_display = ("measured_at", "weight_kg", "source", "created_at")
    list_filter = ("source",)



@admin.register(SleepSession)
class SleepSessionAdmin(admin.ModelAdmin):
    list_display = ('stage', 'start_at', 'end_at', 'duration_fmt')
    list_filter = ('stage', 'source')

    def duration_fmt(self, obj):
        diff = obj.end_at - obj.start_at
        return str(diff)

@admin.register(HealthMetric)
class HealthMetricAdmin(admin.ModelAdmin):
    list_display = ('metric_type', 'value', 'unit', 'measured_at')
    list_filter = ('metric_type', 'source')


@admin.register(ExerciseSet)
class ExerciseSetAdmin(admin.ModelAdmin):
    list_display = ('name', 'reps', 'performed_at', 'source')
    list_filter = ('name', 'performed_at')

@admin.register(ExerciseTemplate)
class ExerciseTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "default_reps", "default_weight_kg", "updated_at")
    search_fields = ("name",)
    list_editable = ("default_reps", "default_weight_kg")
    
