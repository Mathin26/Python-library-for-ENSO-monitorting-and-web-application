"""
ENSOAnalyzer - Analyze ENSO indices and classify El Niño / La Niña events.

Data sources:
- NOAA CPC ONI data (Oceanic Niño Index)
- NOAA CPC SOI data (Southern Oscillation Index)
- IRI/LDEO ENSO data
"""

import logging
import statistics
from datetime import datetime
from typing import List, Optional, Dict, Tuple, Any
from calendar import month_abbr

from .models import ENSOIndex, ENSOPhase, ENSOStrength, ENSOImpactRegion, ClimateAnomaly
from .exceptions import DataFetchError, AnalysisError

logger = logging.getLogger(__name__)


# Known historical ENSO events for reference/fallback
HISTORICAL_ENSO_EVENTS = [
    {"year_start": 1957, "year_end": 1958, "phase": "El Niño", "strength": "Strong"},
    {"year_start": 1965, "year_end": 1966, "phase": "El Niño", "strength": "Moderate"},
    {"year_start": 1972, "year_end": 1973, "phase": "El Niño", "strength": "Strong"},
    {"year_start": 1976, "year_end": 1977, "phase": "El Niño", "strength": "Moderate"},
    {"year_start": 1982, "year_end": 1983, "phase": "El Niño", "strength": "Very Strong"},
    {"year_start": 1986, "year_end": 1987, "phase": "El Niño", "strength": "Moderate"},
    {"year_start": 1991, "year_end": 1992, "phase": "El Niño", "strength": "Moderate"},
    {"year_start": 1994, "year_end": 1995, "phase": "El Niño", "strength": "Moderate"},
    {"year_start": 1997, "year_end": 1998, "phase": "El Niño", "strength": "Very Strong"},
    {"year_start": 2002, "year_end": 2003, "phase": "El Niño", "strength": "Moderate"},
    {"year_start": 2004, "year_end": 2005, "phase": "El Niño", "strength": "Weak"},
    {"year_start": 2009, "year_end": 2010, "phase": "El Niño", "strength": "Moderate"},
    {"year_start": 2014, "year_end": 2016, "phase": "El Niño", "strength": "Very Strong"},
    {"year_start": 2018, "year_end": 2019, "phase": "El Niño", "strength": "Weak"},
    {"year_start": 2023, "year_end": 2024, "phase": "El Niño", "strength": "Strong"},
    {"year_start": 1973, "year_end": 1974, "phase": "La Niña", "strength": "Strong"},
    {"year_start": 1975, "year_end": 1976, "phase": "La Niña", "strength": "Strong"},
    {"year_start": 1988, "year_end": 1989, "phase": "La Niña", "strength": "Strong"},
    {"year_start": 1999, "year_end": 2001, "phase": "La Niña", "strength": "Moderate"},
    {"year_start": 2007, "year_end": 2008, "phase": "La Niña", "strength": "Strong"},
    {"year_start": 2010, "year_end": 2012, "phase": "La Niña", "strength": "Strong"},
    {"year_start": 2020, "year_end": 2023, "phase": "La Niña", "strength": "Moderate"},
]

# Global ENSO teleconnection impact regions
ENSO_IMPACT_REGIONS = [
    ENSOImpactRegion(
        region_name="Southeast Asia & Australia",
        latitude_range=(-40, 20),
        longitude_range=(90, 160),
        el_nino_impact="Drought conditions, reduced monsoon rainfall, increased wildfire risk",
        la_nina_impact="Above-normal rainfall, flooding risk, enhanced monsoon",
        affected_season="June-November",
        impact_variable="precipitation",
    ),
    ENSOImpactRegion(
        region_name="India & South Asia",
        latitude_range=(5, 35),
        longitude_range=(60, 100),
        el_nino_impact="Weakened Indian Summer Monsoon, below-normal rainfall",
        la_nina_impact="Enhanced Indian Summer Monsoon, above-normal rainfall",
        affected_season="June-September",
        impact_variable="precipitation",
    ),
    ENSOImpactRegion(
        region_name="East Africa",
        latitude_range=(-15, 15),
        longitude_range=(25, 50),
        el_nino_impact="Above-normal rainfall, flooding in Oct-Dec",
        la_nina_impact="Drought, below-normal Oct-Dec rainfall",
        affected_season="October-December",
        impact_variable="precipitation",
    ),
    ENSOImpactRegion(
        region_name="Southern Africa",
        latitude_range=(-35, -15),
        longitude_range=(15, 50),
        el_nino_impact="Drought, below-normal rainfall",
        la_nina_impact="Above-normal rainfall",
        affected_season="November-February",
        impact_variable="precipitation",
    ),
    ENSOImpactRegion(
        region_name="Southern United States",
        latitude_range=(25, 40),
        longitude_range=(-120, -75),
        el_nino_impact="Wetter than normal winters, cooler temperatures",
        la_nina_impact="Drier winters, warmer temperatures, drought risk",
        affected_season="December-February",
        impact_variable="both",
    ),
    ENSOImpactRegion(
        region_name="Northern United States & Canada",
        latitude_range=(40, 65),
        longitude_range=(-135, -60),
        el_nino_impact="Warmer and drier winters",
        la_nina_impact="Cooler and wetter winters",
        affected_season="December-February",
        impact_variable="both",
    ),
    ENSOImpactRegion(
        region_name="Tropical Pacific (Niño 3.4 Region)",
        latitude_range=(-5, 5),
        longitude_range=(-170, -120),
        el_nino_impact="Warmer SSTs (+0.5°C to +3°C above average), suppressed upwelling",
        la_nina_impact="Cooler SSTs (-0.5°C to -2°C below average), enhanced upwelling",
        affected_season="Year-round",
        impact_variable="temperature",
    ),
    ENSOImpactRegion(
        region_name="Brazil & South America (North)",
        latitude_range=(-10, 10),
        longitude_range=(-80, -35),
        el_nino_impact="Drought in northern Brazil, Amazonia; flooding in Peru/Ecuador",
        la_nina_impact="Above-normal rainfall in northern Brazil",
        affected_season="January-April",
        impact_variable="precipitation",
    ),
    ENSOImpactRegion(
        region_name="Western Europe",
        latitude_range=(40, 65),
        longitude_range=(-10, 30),
        el_nino_impact="Mild winters with increased storminess",
        la_nina_impact="Colder winters, blocking high pressure patterns",
        affected_season="December-February",
        impact_variable="temperature",
    ),
]


class ENSOAnalyzer:
    """
    Analyzes ENSO indices and provides climate impact assessment.

    Usage:
        analyzer = ENSOAnalyzer()
        current = analyzer.get_current_oni()
        phase = analyzer.get_current_phase()
        impacts = analyzer.get_regional_impacts(lat=13.08, lon=80.27)
    """

    # Embedded recent ONI data (Jan 2020 - Dec 2024)
    # Source: NOAA CPC - values represent 3-month running means
    EMBEDDED_ONI = {
        (2020, 1): -0.2, (2020, 2): 0.1, (2020, 3): 0.4, (2020, 4): 0.3,
        (2020, 5): -0.1, (2020, 6): -0.4, (2020, 7): -0.8, (2020, 8): -1.2,
        (2020, 9): -1.5, (2020, 10): -1.6, (2020, 11): -1.5, (2020, 12): -1.3,
        (2021, 1): -1.1, (2021, 2): -1.0, (2021, 3): -0.8, (2021, 4): -0.5,
        (2021, 5): -0.3, (2021, 6): -0.1, (2021, 7): -0.1, (2021, 8): -0.3,
        (2021, 9): -0.6, (2021, 10): -0.9, (2021, 11): -1.0, (2021, 12): -1.0,
        (2022, 1): -1.0, (2022, 2): -1.0, (2022, 3): -1.1, (2022, 4): -1.1,
        (2022, 5): -1.0, (2022, 6): -0.9, (2022, 7): -0.9, (2022, 8): -1.0,
        (2022, 9): -1.1, (2022, 10): -1.2, (2022, 11): -1.2, (2022, 12): -1.0,
        (2023, 1): -0.7, (2023, 2): -0.4, (2023, 3): -0.1, (2023, 4): 0.3,
        (2023, 5): 0.7, (2023, 6): 1.1, (2023, 7): 1.5, (2023, 8): 1.8,
        (2023, 9): 2.0, (2023, 10): 2.0, (2023, 11): 2.0, (2023, 12): 2.0,
        (2024, 1): 1.9, (2024, 2): 1.6, (2024, 3): 1.2, (2024, 4): 0.9,
        (2024, 5): 0.6, (2024, 6): 0.2, (2024, 7): -0.1, (2024, 8): -0.4,
        (2024, 9): -0.6, (2024, 10): -0.8, (2024, 11): -0.9, (2024, 12): -1.0,
        (2025, 1): -0.9, (2025, 2): -0.8, (2025, 3): -0.6, (2025, 4): -0.3,
        (2025, 5): -0.1, (2025, 6): 0.1, (2025, 7): 0.1, (2025, 8): 0.0,
    }

    def __init__(self, weather_client=None):
        """
        Initialize ENSOAnalyzer.

        Args:
            weather_client: Optional WeatherClient for fetching live SST data.
        """
        self.client = weather_client
        self._oni_cache: Optional[List[ENSOIndex]] = None

    def get_oni_series(self, year_start: int = 2015, year_end: int = None) -> List[ENSOIndex]:
        """
        Get ONI time series from embedded data.

        Args:
            year_start: Start year
            year_end: End year (defaults to current year)

        Returns:
            List of ENSOIndex objects sorted by time
        """
        if year_end is None:
            year_end = datetime.now().year

        results = []
        for (year, month), oni_val in sorted(self.EMBEDDED_ONI.items()):
            if year_start <= year <= year_end:
                results.append(ENSOIndex(
                    year=year,
                    month=month,
                    oni_value=oni_val,
                ))
        return results

    def get_current_oni(self) -> Optional[ENSOIndex]:
        """Get the most recent available ONI value."""
        series = self.get_oni_series(year_start=2023)
        if not series:
            return None
        return series[-1]

    def get_current_phase(self) -> ENSOPhase:
        """Get the current ENSO phase."""
        latest = self.get_current_oni()
        if latest:
            return latest.phase
        return ENSOPhase.NEUTRAL

    def get_phase_duration(self) -> Tuple[ENSOPhase, int]:
        """
        Calculate how many consecutive months the current phase has persisted.

        Returns:
            Tuple of (ENSOPhase, months_duration)
        """
        series = self.get_oni_series()
        if not series:
            return ENSOPhase.NEUTRAL, 0

        current_phase = series[-1].phase
        count = 0
        for index in reversed(series):
            if index.phase == current_phase:
                count += 1
            else:
                break
        return current_phase, count

    def classify_event(self, oni_value: float) -> Tuple[ENSOPhase, ENSOStrength]:
        """Classify an ONI value into phase and strength."""
        if oni_value >= 0.5:
            phase = ENSOPhase.EL_NINO
        elif oni_value <= -0.5:
            phase = ENSOPhase.LA_NINA
        else:
            phase = ENSOPhase.NEUTRAL

        abs_val = abs(oni_value)
        if abs_val < 0.5:
            strength = ENSOStrength.UNKNOWN
        elif abs_val < 1.0:
            strength = ENSOStrength.WEAK
        elif abs_val < 1.5:
            strength = ENSOStrength.MODERATE
        elif abs_val < 2.0:
            strength = ENSOStrength.STRONG
        else:
            strength = ENSOStrength.VERY_STRONG

        return phase, strength

    def get_regional_impacts(self, lat: float, lon: float) -> List[Dict[str, Any]]:
        """
        Get ENSO climate impact assessment for a specific location.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            List of relevant impact dicts for the location
        """
        current_phase = self.get_current_phase()
        impacts = []

        for region in ENSO_IMPACT_REGIONS:
            lat_min, lat_max = region.latitude_range
            lon_min, lon_max = region.longitude_range

            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                impacts.append({
                    "region_name": region.region_name,
                    "current_phase": current_phase.value,
                    "impact": region.get_impact(current_phase),
                    "affected_season": region.affected_season,
                    "impact_variable": region.impact_variable,
                })

        if not impacts:
            impacts.append({
                "region_name": "Global",
                "current_phase": current_phase.value,
                "impact": f"Current {current_phase.value} phase may affect regional teleconnections. "
                          "Check with regional climate services for specific impacts.",
                "affected_season": "Varies by region",
                "impact_variable": "both",
            })

        return impacts

    def get_all_regional_impacts(self) -> List[Dict[str, Any]]:
        """Get ENSO impacts for all defined regions."""
        current_phase = self.get_current_phase()
        latest_oni = self.get_current_oni()
        oni_val = latest_oni.oni_value if latest_oni else 0.0

        return [
            {
                "region_name": region.region_name,
                "latitude_range": region.latitude_range,
                "longitude_range": region.longitude_range,
                "current_phase": current_phase.value,
                "impact": region.get_impact(current_phase),
                "affected_season": region.affected_season,
                "impact_variable": region.impact_variable,
                "oni_value": oni_val,
            }
            for region in ENSO_IMPACT_REGIONS
        ]

    def get_historical_events(self) -> List[Dict[str, Any]]:
        """Return list of historical ENSO events."""
        return HISTORICAL_ENSO_EVENTS

    def get_oni_trend(self, months: int = 12) -> Dict[str, Any]:
        """
        Analyze the ONI trend over the past N months.

        Returns:
            Dict with trend info, min, max, mean, and direction
        """
        series = self.get_oni_series()
        recent = series[-months:] if len(series) >= months else series
        if not recent:
            return {}

        values = [idx.oni_value for idx in recent if idx.oni_value is not None]
        if len(values) < 2:
            return {}

        mean_val = statistics.mean(values)
        trend = "Warming" if values[-1] > values[0] else "Cooling"
        trend_magnitude = values[-1] - values[0]

        return {
            "period_months": len(values),
            "mean_oni": round(mean_val, 2),
            "min_oni": round(min(values), 2),
            "max_oni": round(max(values), 2),
            "start_oni": round(values[0], 2),
            "end_oni": round(values[-1], 2),
            "trend": trend,
            "trend_magnitude": round(trend_magnitude, 2),
            "current_phase": self.classify_event(values[-1])[0].value,
        }

    def get_enso_summary(self) -> Dict[str, Any]:
        """
        Get a comprehensive ENSO status summary.

        Returns:
            Dict with current conditions, trend, and outlook
        """
        latest = self.get_current_oni()
        phase, duration = self.get_phase_duration()
        trend = self.get_oni_trend(months=6)

        oni_val = latest.oni_value if latest else 0.0
        _, strength = self.classify_event(oni_val)

        outlook = self._generate_outlook(oni_val, trend)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "current_phase": phase.value,
            "strength": strength.value,
            "oni_value": oni_val,
            "phase_duration_months": duration,
            "trend": trend,
            "outlook": outlook,
            "data_period": f"{latest.date_label if latest else 'N/A'}",
        }

    def _generate_outlook(self, current_oni: float, trend: Dict) -> str:
        """Generate a plain-language ENSO outlook."""
        phase, strength = self.classify_event(current_oni)
        trend_dir = trend.get("trend", "Neutral")

        if phase == ENSOPhase.EL_NINO:
            if trend_dir == "Cooling":
                return (
                    f"Current {strength.value} El Niño conditions are weakening. "
                    "A transition toward neutral or La Niña conditions is possible in coming months."
                )
            return (
                f"Active {strength.value} El Niño. Expect warmer SSTs in the central-eastern "
                "tropical Pacific and associated global teleconnections."
            )
        elif phase == ENSOPhase.LA_NINA:
            if trend_dir == "Warming":
                return (
                    f"Current {strength.value} La Niña conditions are weakening. "
                    "A transition toward neutral conditions is anticipated."
                )
            return (
                f"Active {strength.value} La Niña. Cooler than normal SSTs in the "
                "central-eastern Pacific with associated global climate impacts."
            )
        return (
            "Neutral ENSO conditions currently prevail. "
            "Neither El Niño nor La Niña thresholds are being met."
        )
