from __future__ import annotations

import os
import sys
from pathlib import Path


def setup_django() -> None:
    """
    Make Django models importable from scripts in `AI Models/`.
    """
    repo_root = Path(__file__).resolve().parents[2]
    backend_dir = repo_root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "glucose_backend.settings")

    import django  # noqa: WPS433 (runtime import is intentional)

    django.setup()

