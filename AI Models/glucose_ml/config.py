from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MealWindowConfig:
    """
    Defines how we slice glucose/activity around each meal.
    All durations are in minutes.
    """

    # glucose windows (relative to meal time)
    pre_baseline_minutes: int = 30          # [-30, 0) for baseline
    pre_context_minutes: int = 120          # [-120, 0) for context stats
    post_minutes: int = 180                 # [0, 180] post-meal outcome window

    # slope window (relative to meal time)
    slope_minutes: int = 60                 # [0, 60] used for slope target

    # resampling grid step used for consistent target computation
    grid_minutes: int = 5                   # resample CGM to 5-minute grid

    # activity aggregation windows
    activity_pre_minutes: int = 360         # [-6h, 0) aggregate workouts/sets
    activity_post_minutes: int = 180        # [0, +3h] aggregate workouts/sets

    # data quality thresholds
    min_points_pre_baseline: int = 3
    min_points_post: int = 10

