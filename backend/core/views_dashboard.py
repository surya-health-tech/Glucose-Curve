from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

@require_GET
def dashboard(request):
    # default: today, 6 hours
    ctx = {
        "default_date": timezone.localdate().isoformat(),
        "default_range": 6,
    }
    return render(request, "core/dashboard.html", ctx)
