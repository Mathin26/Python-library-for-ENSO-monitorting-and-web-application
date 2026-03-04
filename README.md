# ENSOpy — ENSO Climate Analysis & Weather Platform

A complete Python library and Django web application for monitoring **El Niño–Southern Oscillation (ENSO)** events and fetching real-time weather data via geospatial visualization.

---

## 📦 Project Structure

```
enso_project/
├── enso_lib/               # Python library (installable package)
│   ├── __init__.py
│   ├── client.py           # WeatherClient: multi-API weather fetching
│   ├── enso.py             # ENSOAnalyzer: indices + phase classification
│   ├── models.py           # Dataclasses: WeatherData, ENSOIndex, etc.
│   └── exceptions.py       # Custom exceptions
├── django_app/             # Django web application
│   ├── manage.py
│   ├── weather_project/    # Django project settings & URLs
│   │   ├── settings.py
│   │   └── urls.py
│   └── weather_app/        # Main Django app
│       ├── views.py        # Page views + REST API endpoints
│       ├── urls.py
│       └── templates/
│           └── weather_app/
│               ├── base.html
│               ├── index.html      # Dashboard
│               ├── map.html        # Geospatial map
│               └── enso_detail.html
├── setup.py
└── README.md
```

---

## 🚀 Quick Start

### 1. Install the Python Library

```bash
cd enso_project
pip install -e ".[all]"

# Or minimal install:
pip install requests
```

### 2. Use the Library

```python
from enso_lib.client import WeatherClient
from enso_lib.enso import ENSOAnalyzer

# ── Weather Data ──────────────────────────────────────────────
# Free (no API key required) — Open-Meteo
client = WeatherClient()
weather = client.get_current_weather_free(lat=13.08, lon=80.27)
print(f"Chennai: {weather.temperature_c}°C, {weather.weather_description}")
print(f"Wind: {weather.wind_speed_ms} m/s, Humidity: {weather.humidity_percent}%")

# With OpenWeatherMap API key
client = WeatherClient(openweather_api_key="YOUR_KEY")
weather = client.get_weather_by_city("Tokyo", "JP")
forecast = client.get_forecast(lat=35.68, lon=139.69, days=5)

# Sea Surface Temperatures (for ENSO monitoring)
sst = client.get_sst_data(lat=0, lon=-150)  # Niño 3.4 region
print(f"SST Anomaly: {sst}°C")

# ── ENSO Analysis ─────────────────────────────────────────────
analyzer = ENSOAnalyzer()

# Current conditions
summary = analyzer.get_enso_summary()
print(f"Phase: {summary['current_phase']}")
print(f"ONI: {summary['oni_value']}")
print(f"Strength: {summary['strength']}")
print(f"Outlook: {summary['outlook']}")

# ONI time series
series = analyzer.get_oni_series(year_start=2020, year_end=2025)
for idx in series[-6:]:  # last 6 months
    print(f"{idx.date_label}: ONI={idx.oni_value}, Phase={idx.phase.value}")

# Regional impact assessment
impacts = analyzer.get_regional_impacts(lat=13.08, lon=80.27)
for impact in impacts:
    print(f"\n{impact['region_name']}")
    print(f"  Impact: {impact['impact']}")
    print(f"  Season: {impact['affected_season']}")
```

### 3. Run the Django Web App

```bash
cd enso_project/django_app

# Set your OpenWeatherMap API key (optional — free tier works without it)
export OPENWEATHER_API_KEY="your_openweathermap_key"

# Initialize database
python manage.py migrate

# Start development server
python manage.py runserver
```

Open **http://localhost:8000** in your browser.

---

## 🌐 Web Application Pages

| URL | Page |
|-----|------|
| `/` | Dashboard — ENSO summary, ONI chart, historical events |
| `/map/` | Geospatial Map — Interactive Leaflet map with ENSO regions and live weather |
| `/enso/` | ENSO Analysis — Detailed ONI series, trend analysis, teleconnection regions |

## ⚡ REST API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/enso/summary/` | Current ENSO phase, ONI, outlook |
| `GET /api/enso/oni-series/?year_start=2020` | ONI monthly time series |
| `GET /api/weather/current/?lat=13.08&lon=80.27` | Current weather (Open-Meteo, free) |
| `GET /api/weather/forecast/?lat=13.08&lon=80.27` | 5-day forecast (requires OWM key) |
| `GET /api/enso/regional-impacts/?lat=13.08&lon=80.27` | ENSO teleconnection impacts |
| `GET /api/enso/sst-grid/` | Sea surface temperatures in Niño 3.4 region |
| `GET /api/geocode/?city=Chennai` | Geocode city to lat/lon (requires OWM key) |

---

## 🌊 What is ENSO?

**ENSO (El Niño–Southern Oscillation)** is the most important year-to-year climate variability driver on Earth:

- **El Niño** — Warmer than normal sea surface temperatures (SST) in the central-eastern tropical Pacific. ONI ≥ +0.5°C. Associated with drought in Australia/SE Asia, floods in Peru/Ecuador, weakened Indian monsoon, warmer winters in North America.

- **La Niña** — Cooler than normal SSTs in the same region. ONI ≤ −0.5°C. Associated with above-normal rainfall in Australia, enhanced Indian monsoon, increased Atlantic hurricane activity.

- **Neutral** — SST anomalies between −0.5°C and +0.5°C.

### Key Indices

| Index | Description |
|-------|-------------|
| **ONI** | Oceanic Niño Index — 3-month running mean SST anomaly in Niño 3.4 region. Primary NOAA threshold. |
| **SOI** | Southern Oscillation Index — Pressure difference between Tahiti and Darwin |
| **MEI** | Multivariate ENSO Index — Combined atmosphere-ocean signal |

---

## 🔑 API Keys

| Service | Required | Free Tier | Get Key |
|---------|----------|-----------|---------|
| **Open-Meteo** | ❌ No | ✅ Completely free | No registration |
| **OpenWeatherMap** | Optional | ✅ 1,000 calls/day | [openweathermap.org](https://openweathermap.org/api) |
| **NOAA CDO** | Optional | ✅ Free | [ncdc.noaa.gov](https://www.ncdc.noaa.gov/cdo-web/token) |

---

## 🏗️ Production Deployment

```bash
# Install production dependencies
pip install gunicorn whitenoise

# Collect static files
python manage.py collectstatic

# Set environment variables
export DJANGO_SECRET_KEY="your-secret-key"
export DEBUG=False
export ALLOWED_HOSTS="yourdomain.com"
export OPENWEATHER_API_KEY="your-key"

# Run with gunicorn
gunicorn weather_project.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

---

## 📚 Data Sources

- **Open-Meteo** — Free weather and marine API (open-meteo.com)
- **NOAA CPC** — ONI data (cpc.ncep.noaa.gov)
- **OpenWeatherMap** — Current weather, forecasts, geocoding

---

## 📄 License

MIT License — see LICENSE file for details.
