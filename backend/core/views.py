from django.shortcuts import render

# Create your views here.
from django.http import JsonResponse

def home(request):
    return JsonResponse({
        "ok": True,
        "message": "Glucose backend is running",
        "paths": ["/admin/", "/api/"]
    })