from django.urls import path
from core import api
from core.views_timeline import timeline
from core.views_dashboard import dashboard

urlpatterns = [
    path("ping/", api.ping),
    path("sync/", api.sync),
    path("food-items/", api.food_items),
    path("meal-templates/", api.meal_templates),
    path("exercise-templates/", api.exercise_templates),
    path("medication-options/", api.medication_options),
    path("timeline/", timeline, name="timeline"),
    path("dashboard/", dashboard, name="dashboard"),
]
