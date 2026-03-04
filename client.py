"""
WeatherClient - Unified interface for fetching weather data from multiple APIs.

Supported APIs:
- OpenWeatherMap (Current, Forecast, Historical)
- Open-Meteo (Free, no API key required)
- NOAA Climate Data Online
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlencode
import json

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from .models import WeatherData, ForecastData
from .exceptions import APIError, DataFetchError, ConfigurationError

logger = logging.getLogger(__name__)


class WeatherClient:
    """
    Unified client for fetching weather data from multiple providers.

    Usage:
        client = WeatherClient(openweather_api_key="your_key")
        weather = client.get_current_weather(lat=35.6762, lon=139.6503)
        print(f"Tokyo: {weather.temperature_c}°C")
    """

    OPENWEATHER_BASE = "https://api.openweathermap.org/data/2.5"
    OPENWEATHER_GEO = "https://api.openweathermap.org/geo/1.0"
    OPEN_METEO_BASE = "https://api.open-meteo.com/v1"
    NOAA_CDO_BASE = "https://www.ncdc.noaa.gov/cdo-web/api/v2"

    # WMO weather interpretation codes for Open-Meteo
    WMO_CODES = {
        0: ("Clear Sky", "clear"),
        1: ("Mainly Clear", "clear"),
        2: ("Partly Cloudy", "clouds"),
        3: ("Overcast", "clouds"),
        45: ("Foggy", "atmosphere"),
        48: ("Depositing Rime Fog", "atmosphere"),
        51: ("Light Drizzle", "drizzle"),
        53: ("Moderate Drizzle", "drizzle"),
        55: ("Dense Drizzle", "drizzle"),
        61: ("Slight Rain", "rain"),
        63: ("Moderate Rain", "rain"),
        65: ("Heavy Rain", "rain"),
        71: ("Slight Snow", "snow"),
        73: ("Moderate Snow", "snow"),
        75: ("Heavy Snow", "snow"),
        77: ("Snow Grains", "snow"),
        80: ("Slight Rain Showers", "rain"),
        81: ("Moderate Rain Showers", "rain"),
        82: ("Violent Rain Showers", "rain"),
        85: ("Slight Snow Showers", "snow"),
        86: ("Heavy Snow Showers", "snow"),
        95: ("Thunderstorm", "thunderstorm"),
        96: ("Thunderstorm with Slight Hail", "thunderstorm"),
        99: ("Thunderstorm with Heavy Hail", "thunderstorm"),
    }

    def __init__(
        self,
        openweather_api_key: Optional[str] = None,
        noaa_token: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        cache_ttl: int = 300,  # seconds
    ):
        """
        Initialize WeatherClient.

        Args:
            openweather_api_key: API key for OpenWeatherMap. Falls back to
                                 OPENWEATHER_API_KEY environment variable.
            noaa_token: Token for NOAA Climate Data Online API.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts.
            cache_ttl: Cache time-to-live in seconds (0 to disable).
        """
        self.openweather_api_key = (
            openweather_api_key or os.environ.get("OPENWEATHER_API_KEY")
        )
        self.noaa_token = noaa_token or os.environ.get("NOAA_CDO_TOKEN")
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[Any, float]] = {}

        if HAS_REQUESTS:
            self._session = self._create_session(max_retries)
        else:
            self._session = None
            logger.warning(
                "requests library not installed. Using urllib fallback."
            )

    def _create_session(self, max_retries: int) -> "requests.Session":
        """Create a requests session with retry logic."""
        session = requests.Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get(self, url: str, params: Dict = None, headers: Dict = None) -> Dict:
        """Perform a GET request with caching."""
        cache_key = f"{url}?{urlencode(params or {})}"

        # Check cache
        if self.cache_ttl > 0 and cache_key in self._cache:
            data, cached_at = self._cache[cache_key]
            if time.time() - cached_at < self.cache_ttl:
                logger.debug(f"Cache hit: {cache_key[:80]}")
                return data

        logger.debug(f"Fetching: {url}")

        try:
            if HAS_REQUESTS:
                resp = self._session.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )
                if resp.status_code == 401:
                    raise APIError("Invalid API key", status_code=401)
                if resp.status_code == 429:
                    raise APIError("Rate limit exceeded", status_code=429)
                if not resp.ok:
                    raise APIError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )
                data = resp.json()
            else:
                import urllib.request
                full_url = url + ("?" + urlencode(params) if params else "")
                req = urllib.request.Request(full_url, headers=headers or {})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.loads(r.read().decode())

            # Cache result
            if self.cache_ttl > 0:
                self._cache[cache_key] = (data, time.time())

            return data

        except (APIError, ConfigurationError):
            raise
        except Exception as e:
            raise DataFetchError(f"Failed to fetch data from {url}: {e}") from e

    # -------------------------------------------------------------------------
    # OpenWeatherMap Methods
    # -------------------------------------------------------------------------

    def _check_owm_key(self):
        """Ensure OpenWeatherMap API key is available."""
        if not self.openweather_api_key:
            raise ConfigurationError(
                "OpenWeatherMap API key required. Pass openweather_api_key= or "
                "set OPENWEATHER_API_KEY environment variable."
            )

    def get_current_weather(self, lat: float, lon: float) -> WeatherData:
        """
        Fetch current weather for a lat/lon using OpenWeatherMap.

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)

        Returns:
            WeatherData instance
        """
        self._check_owm_key()
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.openweather_api_key,
            "units": "metric",
        }
        data = self._get(f"{self.OPENWEATHER_BASE}/weather", params)
        return self._parse_owm_current(data, lat, lon)

    def get_weather_by_city(self, city: str, country_code: str = None) -> WeatherData:
        """
        Fetch current weather by city name.

        Args:
            city: City name
            country_code: ISO 3166 country code (e.g., "US", "IN")
        """
        self._check_owm_key()
        query = f"{city},{country_code}" if country_code else city
        params = {
            "q": query,
            "appid": self.openweather_api_key,
            "units": "metric",
        }
        data = self._get(f"{self.OPENWEATHER_BASE}/weather", params)
        return self._parse_owm_current(data, data["coord"]["lat"], data["coord"]["lon"])

    def get_forecast(
        self, lat: float, lon: float, days: int = 5
    ) -> List[ForecastData]:
        """
        Fetch 5-day / 3-hour forecast from OpenWeatherMap.

        Args:
            lat: Latitude
            lon: Longitude
            days: Number of forecast days (1-5)

        Returns:
            List of ForecastData instances
        """
        self._check_owm_key()
        cnt = min(days * 8, 40)  # 8 slots per day (3-hour intervals)
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.openweather_api_key,
            "units": "metric",
            "cnt": cnt,
        }
        data = self._get(f"{self.OPENWEATHER_BASE}/forecast", params)
        return [self._parse_owm_forecast(item, lat, lon) for item in data["list"]]

    def get_air_quality(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Fetch air quality data from OpenWeatherMap Air Pollution API.

        Returns:
            Dict with AQI and pollutant concentrations (CO, NO2, O3, PM2.5, PM10)
        """
        self._check_owm_key()
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.openweather_api_key,
        }
        data = self._get(f"{self.OPENWEATHER_BASE}/air_pollution", params)
        components = data["list"][0]["components"]
        aqi = data["list"][0]["main"]["aqi"]
        aqi_labels = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
        return {
            "aqi": aqi,
            "aqi_label": aqi_labels.get(aqi, "Unknown"),
            "co": components.get("co"),
            "no2": components.get("no2"),
            "o3": components.get("o3"),
            "pm2_5": components.get("pm2_5"),
            "pm10": components.get("pm10"),
            "so2": components.get("so2"),
            "nh3": components.get("nh3"),
        }

    def geocode(self, city: str, country_code: str = None, limit: int = 5) -> List[Dict]:
        """
        Geocode a city name to lat/lon using OpenWeatherMap Geocoding API.

        Returns:
            List of location dicts with lat, lon, name, country, state
        """
        self._check_owm_key()
        query = f"{city},{country_code}" if country_code else city
        params = {
            "q": query,
            "limit": limit,
            "appid": self.openweather_api_key,
        }
        data = self._get(f"{self.OPENWEATHER_GEO}/direct", params)
        return [
            {
                "name": loc.get("name"),
                "latitude": loc.get("lat"),
                "longitude": loc.get("lon"),
                "country": loc.get("country"),
                "state": loc.get("state"),
            }
            for loc in data
        ]

    def _parse_owm_current(self, data: Dict, lat: float, lon: float) -> WeatherData:
        """Parse OpenWeatherMap current weather response."""
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        rain = data.get("rain", {})
        snow = data.get("snow", {})
        precip = rain.get("1h", 0) + snow.get("1h", 0)
        main = data["main"]
        weather = data["weather"][0]

        return WeatherData(
            latitude=lat,
            longitude=lon,
            timestamp=datetime.utcfromtimestamp(data["dt"]),
            temperature_c=main["temp"],
            feels_like_c=main["feels_like"],
            humidity_percent=main["humidity"],
            pressure_hpa=main["pressure"],
            wind_speed_ms=wind.get("speed", 0.0),
            wind_direction_deg=wind.get("deg", 0.0),
            cloud_cover_percent=clouds.get("all", 0),
            visibility_m=data.get("visibility", 10000),
            weather_condition=weather["main"],
            weather_description=weather["description"].title(),
            city_name=data.get("name"),
            country_code=data.get("sys", {}).get("country"),
            precipitation_mm=precip if precip else None,
            raw_data=data,
        )

    def _parse_owm_forecast(self, item: Dict, lat: float, lon: float) -> ForecastData:
        """Parse a single OWM forecast item."""
        main = item["main"]
        wind = item.get("wind", {})
        rain = item.get("rain", {})
        snow = item.get("snow", {})
        precip = rain.get("3h", 0) + snow.get("3h", 0)

        return ForecastData(
            latitude=lat,
            longitude=lon,
            forecast_time=datetime.utcfromtimestamp(item["dt"]),
            temperature_c=main["temp"],
            humidity_percent=main["humidity"],
            pressure_hpa=main["pressure"],
            wind_speed_ms=wind.get("speed", 0.0),
            weather_condition=item["weather"][0]["main"],
            pop=item.get("pop", 0.0),
            precipitation_mm=precip if precip else None,
        )

    # -------------------------------------------------------------------------
    # Open-Meteo Methods (Free, no API key required)
    # -------------------------------------------------------------------------

    def get_current_weather_free(self, lat: float, lon: float) -> WeatherData:
        """
        Fetch current weather using Open-Meteo API (free, no API key needed).

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            WeatherData instance
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "pressure_msl",
                "wind_speed_10m",
                "wind_direction_10m",
                "cloud_cover",
                "visibility",
            ]),
            "wind_speed_unit": "ms",
            "timezone": "UTC",
        }
        data = self._get(f"{self.OPEN_METEO_BASE}/forecast", params)
        return self._parse_open_meteo_current(data, lat, lon)

    def get_historical_weather_free(
        self,
        lat: float,
        lon: float,
        start_date: str,
        end_date: str,
    ) -> List[WeatherData]:
        """
        Fetch historical weather data using Open-Meteo Historical API.

        Args:
            lat: Latitude
            lon: Longitude
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of WeatherData instances (daily aggregates)
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "daily": ",".join([
                "temperature_2m_max",
                "temperature_2m_min",
                "temperature_2m_mean",
                "precipitation_sum",
                "wind_speed_10m_max",
                "weather_code",
            ]),
            "wind_speed_unit": "ms",
            "timezone": "UTC",
        }
        data = self._get("https://archive-api.open-meteo.com/v1/archive", params)
        return self._parse_open_meteo_historical(data, lat, lon)

    def get_sst_data(self, lat: float, lon: float) -> Optional[float]:
        """
        Fetch sea surface temperature from Open-Meteo Marine API.

        Args:
            lat: Latitude (ocean location)
            lon: Longitude (ocean location)

        Returns:
            Sea surface temperature in Celsius, or None
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "sea_surface_temperature",
            "timezone": "UTC",
        }
        try:
            data = self._get("https://marine-api.open-meteo.com/v1/marine", params)
            return data.get("current", {}).get("sea_surface_temperature")
        except Exception as e:
            logger.warning(f"Could not fetch SST at ({lat}, {lon}): {e}")
            return None

    def _parse_open_meteo_current(self, data: Dict, lat: float, lon: float) -> WeatherData:
        """Parse Open-Meteo current weather response."""
        current = data.get("current", {})
        wmo_code = current.get("weather_code", 0)
        desc, condition = self.WMO_CODES.get(wmo_code, ("Unknown", "unknown"))

        return WeatherData(
            latitude=lat,
            longitude=lon,
            timestamp=datetime.utcnow(),
            temperature_c=current.get("temperature_2m", 0.0),
            feels_like_c=current.get("apparent_temperature", 0.0),
            humidity_percent=current.get("relative_humidity_2m", 0),
            pressure_hpa=current.get("pressure_msl", 1013.25),
            wind_speed_ms=current.get("wind_speed_10m", 0.0),
            wind_direction_deg=current.get("wind_direction_10m", 0.0),
            cloud_cover_percent=current.get("cloud_cover", 0),
            visibility_m=current.get("visibility", 10000),
            weather_condition=condition.title(),
            weather_description=desc,
            precipitation_mm=current.get("precipitation"),
            raw_data=data,
        )

    def _parse_open_meteo_historical(
        self, data: Dict, lat: float, lon: float
    ) -> List[WeatherData]:
        """Parse Open-Meteo historical weather response."""
        daily = data.get("daily", {})
        times = daily.get("time", [])
        results = []

        for i, date_str in enumerate(times):
            wmo_code = (daily.get("weather_code") or [0])[i] if daily.get("weather_code") else 0
            desc, condition = self.WMO_CODES.get(wmo_code, ("Unknown", "unknown"))
            temp_max = (daily.get("temperature_2m_max") or [None])[i]
            temp_min = (daily.get("temperature_2m_min") or [None])[i]
            temp_mean = (daily.get("temperature_2m_mean") or [None])[i]
            temp = temp_mean or ((temp_max + temp_min) / 2 if temp_max and temp_min else 15.0)

            results.append(WeatherData(
                latitude=lat,
                longitude=lon,
                timestamp=datetime.strptime(date_str, "%Y-%m-%d"),
                temperature_c=temp,
                feels_like_c=temp,
                humidity_percent=0.0,
                pressure_hpa=1013.25,
                wind_speed_ms=(daily.get("wind_speed_10m_max") or [0.0])[i] or 0.0,
                wind_direction_deg=0.0,
                cloud_cover_percent=0,
                visibility_m=10000,
                weather_condition=condition.title(),
                weather_description=desc,
                precipitation_mm=(daily.get("precipitation_sum") or [None])[i],
            ))

        return results

    # -------------------------------------------------------------------------
    # Multi-location batch methods
    # -------------------------------------------------------------------------

    def get_weather_grid(
        self,
        lat_min: float, lat_max: float,
        lon_min: float, lon_max: float,
        resolution: float = 5.0,
    ) -> List[WeatherData]:
        """
        Fetch weather for a grid of points (useful for ENSO region analysis).

        Args:
            lat_min, lat_max: Latitude bounds
            lon_min, lon_max: Longitude bounds
            resolution: Grid resolution in degrees

        Returns:
            List of WeatherData for each grid point
        """
        import math
        results = []
        lat = lat_min
        while lat <= lat_max:
            lon = lon_min
            while lon <= lon_max:
                try:
                    weather = self.get_current_weather_free(lat, lon)
                    results.append(weather)
                except Exception as e:
                    logger.warning(f"Failed at ({lat}, {lon}): {e}")
                lon = round(lon + resolution, 2)
            lat = round(lat + resolution, 2)
        return results

    def get_nino34_sst(self) -> List[Dict]:
        """
        Fetch sea surface temperatures for the Niño 3.4 region
        (5°N–5°S, 170°W–120°W) at key grid points.

        Returns:
            List of dicts with lat, lon, sst
        """
        points = [
            (5, -170), (5, -150), (5, -120),
            (0, -170), (0, -150), (0, -120),
            (-5, -170), (-5, -150), (-5, -120),
        ]
        results = []
        for lat, lon in points:
            sst = self.get_sst_data(lat, lon)
            results.append({"latitude": lat, "longitude": lon, "sst": sst})
        return results

    def clear_cache(self):
        """Clear the response cache."""
        self._cache.clear()
        logger.info("Cache cleared.")
