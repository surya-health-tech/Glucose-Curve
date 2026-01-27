"""
Meal-centered ML utilities for glucose curve prediction.

This package is intentionally lightweight and focused on:
- extracting meal-centered windows from the Django DB
- computing features + post-meal targets (peak / iAUC / slope)
- training and running a simple baseline model
"""

from .config import MealWindowConfig

