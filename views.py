"""
Views for ENSOpy Weather Platform Django application.
"""

import json
import logging
import sys
import os
from datetime import datetime
from typing import Any, Dict

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

# Add enso_lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from enso_lib.client import WeatherClient
from enso_lib.enso import ENSOAnalyzer, ENSO_IMPACT_REGIONS
from enso_lib.models import ENSOPhase
from enso_lib.exceptions import APIError, DataFetchError, ConfigurationError

logger = logging.getLogger(__name__)


def get_weather_client() -> WeatherClient:
    """Get a configured WeatherClient instance."""
    return WeatherClient(
        openweather_api_key=getattr(settings, "OPENWEATHER_API_KEY", None),
        cache_ttl=getattr(settings, "WEATHER_CACHE_TTL", 300),
    )


def get_enso_analyzer() -> ENSOAnalyzer:
    """Get an ENSOAnalyzer instance."""
    client = get_weather_client()
    return ENSOAnalyzer(weather_client=client)


# ─────────────────────────────────────────────────────────────────────────────
# Page Views
# ─────────────────────────────────────────────────────────────────────────────

def index(request):
    """Main dashboard page."""
    analyzer = get_enso_analyzer()
    summary = analyzer.get_enso_summary()
    oni_series = analyzer.get_oni_series(year_start=2020)

    # Prepare chart data
    chart_labels = [f"{idx.date_label}" for idx in oni_series]
    chart_values = [idx.oni_value for idx in oni_series]

    # Color for each bar (red=El Niño, blue=La Niña, gray=Neutral)
    chart_colors = []
    for v in chart_values:
        if v is None:
            chart_colors.append("rgba(156,163,175,0.6)")
        elif v >= 0.5:
            chart_colors.append("rgba(239,68,68,0.75)")
        elif v <= -0.5:
            chart_colors.append("rgba(59,130,246,0.75)")
        else:
            chart_colors.append("rgba(156,163,175,0.6)")

    phase = summary["current_phase"]
    phase_color = {
        "El Niño": "#ef4444",
        "La Niña": "#3b82f6",
        "Neutral": "#6b7280",
    }.get(phase, "#6b7280")

    context = {
        "summary": summary,
        "phase_color": phase_color,
        "chart_labels": json.dumps(chart_labels),
        "chart_values": json.dumps(chart_values),
        "chart_colors": json.dumps(chart_colors),
        "historical_events": analyzer.get_historical_events()[-10:],
    }
    return render(request, "weather_app/index.html", context)


def map_view(request):
    """Geospatial map page."""
    analyzer = get_enso_analyzer()
    summary = analyzer.get_enso_summary()
    impacts = analyzer.get_all_regional_impacts()

    context = {
        "summary": summary,
        "impacts_json": json.dumps(impacts),
        "openweather_api_key": getattr(settings, "OPENWEATHER_API_KEY", ""),
    }
    return render(request, "weather_app/map.html", context)


def enso_detail(request):
    """Detailed ENSO analysis page."""
    analyzer = get_enso_analyzer()
    summary = analyzer.get_enso_summary()
    oni_series = analyzer.get_oni_series(year_start=2010)
    trend = analyzer.get_oni_trend(months=12)
    phase, duration = analyzer.get_phase_duration()

    # Format series for charts
    chart_data = [idx.to_dict() for idx in oni_series]

    context = {
        "summary": summary,
        "oni_series_json": json.dumps(chart_data),
        "trend": trend,
        "duration": duration,
        "impact_regions": ENSO_IMPACT_REGIONS,
        "historical_events": analyzer.get_historical_events(),
    }
    return render(request, "weather_app/enso_detail.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

def api_enso_summary(request):
    """API: Current ENSO summary."""
    cache_key = "api_enso_summary"
    data = cache.get(cache_key)
    if not data:
        analyzer = get_enso_analyzer()
        data = analyzer.get_enso_summary()
        cache.set(cache_key, data, 3600)  # cache 1 hour
    return JsonResponse(data)


def api_oni_series(request):
    """API: ONI time series data."""
    year_start = int(request.GET.get("year_start", 2015))
    year_end = int(request.GET.get("year_end", datetime.now().year))

    cache_key = f"api_oni_{year_start}_{year_end}"
    data = cache.get(cache_key)
    if not data:
        analyzer = get_enso_analyzer()
        series = analyzer.get_oni_series(year_start=year_start, year_end=year_end)
        data = [idx.to_dict() for idx in series]
        cache.set(cache_key, data, 3600)

    return JsonResponse({"series": data, "count": len(data)})


def api_current_weather(request):
    """API: Current weather at lat/lon."""
    try:
        lat = float(request.GET.get("lat", 13.0827))
        lon = float(request.GET.get("lon", 80.2707))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid lat/lon parameters"}, status=400)

    cache_key = f"api_weather_{lat:.2f}_{lon:.2f}"
    data = cache.get(cache_key)
    if not data:
        try:
            client = get_weather_client()
            weather = client.get_current_weather_free(lat, lon)
            data = weather.to_dict()
            cache.set(cache_key, data, 300)  # 5 min cache
        except (DataFetchError, Exception) as e:
            logger.error(f"Weather fetch error at ({lat}, {lon}): {e}")
            return JsonResponse({"error": str(e)}, status=503)

    return JsonResponse(data)


def api_forecast(request):
    """API: 5-day forecast at lat/lon (requires OWM API key)."""
    try:
        lat = float(request.GET.get("lat", 13.0827))
        lon = float(request.GET.get("lon", 80.2707))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid lat/lon parameters"}, status=400)

    try:
        client = get_weather_client()
        forecasts = client.get_forecast(lat, lon)
        data = [f.to_dict() for f in forecasts]
        return JsonResponse({"forecasts": data, "count": len(data)})
    except ConfigurationError:
        return JsonResponse(
            {"error": "OpenWeatherMap API key required for forecast data. "
                      "Set OPENWEATHER_API_KEY environment variable."},
            status=503,
        )
    except Exception as e:
        logger.error(f"Forecast error: {e}")
        return JsonResponse({"error": str(e)}, status=503)


def api_regional_impacts(request):
    """API: ENSO regional impacts for a location."""
    try:
        lat = float(request.GET.get("lat", 13.0827))
        lon = float(request.GET.get("lon", 80.2707))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid lat/lon"}, status=400)

    analyzer = get_enso_analyzer()
    impacts = analyzer.get_regional_impacts(lat, lon)
    summary = analyzer.get_enso_summary()

    return JsonResponse({
        "latitude": lat,
        "longitude": lon,
        "enso_phase": summary["current_phase"],
        "oni_value": summary["oni_value"],
        "impacts": impacts,
    })


def api_sst_grid(request):
    """API: Sea surface temperatures in Niño 3.4 region."""
    cache_key = "api_sst_grid"
    data = cache.get(cache_key)
    if not data:
        try:
            client = get_weather_client()
            sst_data = client.get_nino34_sst()
            data = {"sst_points": sst_data, "region": "Niño 3.4 (5°N–5°S, 170°W–120°W)"}
            cache.set(cache_key, data, 1800)
        except Exception as e:
            logger.error(f"SST error: {e}")
            data = {"sst_points": [], "error": str(e)}

    return JsonResponse(data)


def api_geocode(request):
    """API: Geocode a city name."""
    city = request.GET.get("city", "")
    if not city:
        return JsonResponse({"error": "city parameter required"}, status=400)

    try:
        client = get_weather_client()
        locations = client.geocode(city)
        return JsonResponse({"locations": locations})
    except ConfigurationError:
        return JsonResponse(
            {"error": "OpenWeatherMap API key required for geocoding."},
            status=503,
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=503)
