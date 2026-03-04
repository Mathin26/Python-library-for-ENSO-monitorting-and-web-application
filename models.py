"""
Data models for ENSOpy library.
Dataclasses representing weather data, ENSO indices, and climate anomalies.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class ENSOPhase(Enum):
    """ENSO phase classification."""
    EL_NINO = "El Niño"
    LA_NINA = "La Niña"
    NEUTRAL = "Neutral"


class ENSOStrength(Enum):
    """ENSO event strength classification."""
    WEAK = "Weak"
    MODERATE = "Moderate"
    STRONG = "Strong"
    VERY_STRONG = "Very Strong"
    UNKNOWN = "Unknown"


@dataclass
class WeatherData:
    """Represents weather observation data for a location."""
    latitude: float
    longitude: float
    timestamp: datetime
    temperature_c: float
    feels_like_c: float
    humidity_percent: float
    pressure_hpa: float
    wind_speed_ms: float
    wind_direction_deg: float
    cloud_cover_percent: float
    visibility_m: float
    weather_condition: str
    weather_description: str
    city_name: Optional[str] = None
    country_code: Optional[str] = None
    precipitation_mm: Optional[float] = None
    uv_index: Optional[float] = None
    sea_surface_temp_c: Optional[float] = None
    raw_data: Optional[Dict[str, Any]] = field(default=None, repr=False)

    @property
    def temperature_f(self) -> float:
        """Convert Celsius to Fahrenheit."""
        return (self.temperature_c * 9 / 5) + 32

    @property
    def temperature_anomaly_label(self) -> str:
        """Label temperature relative to global average (~15°C)."""
        diff = self.temperature_c - 15.0
        if diff > 2:
            return "Significantly Warmer"
        elif diff > 0.5:
            return "Warmer than Average"
        elif diff < -2:
            return "Significantly Cooler"
        elif diff < -0.5:
            return "Cooler than Average"
        return "Near Average"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timestamp": self.timestamp.isoformat(),
            "temperature_c": self.temperature_c,
            "temperature_f": self.temperature_f,
            "feels_like_c": self.feels_like_c,
            "humidity_percent": self.humidity_percent,
            "pressure_hpa": self.pressure_hpa,
            "wind_speed_ms": self.wind_speed_ms,
            "wind_direction_deg": self.wind_direction_deg,
            "cloud_cover_percent": self.cloud_cover_percent,
            "visibility_m": self.visibility_m,
            "weather_condition": self.weather_condition,
            "weather_description": self.weather_description,
            "city_name": self.city_name,
            "country_code": self.country_code,
            "precipitation_mm": self.precipitation_mm,
            "uv_index": self.uv_index,
            "sea_surface_temp_c": self.sea_surface_temp_c,
        }


@dataclass
class ENSOIndex:
    """
    Represents ENSO indices for a specific time period.

    Key indices:
    - ONI (Oceanic Niño Index): 3-month running mean SST anomaly in Niño 3.4 region
    - SOI (Southern Oscillation Index): Normalized pressure difference between
      Tahiti and Darwin
    - MEI (Multivariate ENSO Index): Combined atmosphere-ocean index
    """
    year: int
    month: int
    oni_value: Optional[float] = None       # Oceanic Niño Index
    soi_value: Optional[float] = None       # Southern Oscillation Index
    mei_value: Optional[float] = None       # Multivariate ENSO Index
    nino34_sst: Optional[float] = None      # Niño 3.4 SST anomaly
    nino3_sst: Optional[float] = None       # Niño 3 SST anomaly
    nino4_sst: Optional[float] = None       # Niño 4 SST anomaly
    nino12_sst: Optional[float] = None      # Niño 1+2 SST anomaly

    @property
    def phase(self) -> ENSOPhase:
        """Determine ENSO phase from ONI value."""
        if self.oni_value is None:
            return ENSOPhase.NEUTRAL
        if self.oni_value >= 0.5:
            return ENSOPhase.EL_NINO
        elif self.oni_value <= -0.5:
            return ENSOPhase.LA_NINA
        return ENSOPhase.NEUTRAL

    @property
    def strength(self) -> ENSOStrength:
        """Classify ENSO event strength."""
        if self.oni_value is None:
            return ENSOStrength.UNKNOWN
        abs_oni = abs(self.oni_value)
        if abs_oni < 0.5:
            return ENSOStrength.UNKNOWN
        elif abs_oni < 1.0:
            return ENSOStrength.WEAK
        elif abs_oni < 1.5:
            return ENSOStrength.MODERATE
        elif abs_oni < 2.0:
            return ENSOStrength.STRONG
        return ENSOStrength.VERY_STRONG

    @property
    def date_label(self) -> str:
        from calendar import month_abbr
        return f"{month_abbr[self.month]} {self.year}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "year": self.year,
            "month": self.month,
            "date_label": self.date_label,
            "oni_value": self.oni_value,
            "soi_value": self.soi_value,
            "mei_value": self.mei_value,
            "nino34_sst": self.nino34_sst,
            "phase": self.phase.value,
            "strength": self.strength.value,
        }


@dataclass
class ClimateAnomaly:
    """Represents a climate anomaly at a geographic location."""
    latitude: float
    longitude: float
    variable: str                   # e.g., "temperature", "precipitation"
    anomaly_value: float            # Departure from climatological mean
    baseline_period: str            # e.g., "1991-2020"
    timestamp: datetime
    enso_phase: Optional[ENSOPhase] = None
    region_name: Optional[str] = None
    units: str = "°C"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "variable": self.variable,
            "anomaly_value": self.anomaly_value,
            "baseline_period": self.baseline_period,
            "timestamp": self.timestamp.isoformat(),
            "enso_phase": self.enso_phase.value if self.enso_phase else None,
            "region_name": self.region_name,
            "units": self.units,
        }


@dataclass
class ForecastData:
    """Represents weather forecast data."""
    latitude: float
    longitude: float
    forecast_time: datetime
    temperature_c: float
    humidity_percent: float
    pressure_hpa: float
    wind_speed_ms: float
    weather_condition: str
    pop: float = 0.0               # Probability of precipitation (0-1)
    precipitation_mm: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "forecast_time": self.forecast_time.isoformat(),
            "temperature_c": self.temperature_c,
            "humidity_percent": self.humidity_percent,
            "pressure_hpa": self.pressure_hpa,
            "wind_speed_ms": self.wind_speed_ms,
            "weather_condition": self.weather_condition,
            "pop": self.pop,
            "precipitation_mm": self.precipitation_mm,
        }


@dataclass
class ENSOImpactRegion:
    """Describes expected climate impacts for a region during an ENSO phase."""
    region_name: str
    latitude_range: tuple        # (min_lat, max_lat)
    longitude_range: tuple      # (min_lon, max_lon)
    el_nino_impact: str
    la_nina_impact: str
    affected_season: str
    impact_variable: str         # "temperature", "precipitation", "both"

    def get_impact(self, phase: ENSOPhase) -> str:
        if phase == ENSOPhase.EL_NINO:
            return self.el_nino_impact
        elif phase == ENSOPhase.LA_NINA:
            return self.la_nina_impact
        return "Near-normal conditions expected"
