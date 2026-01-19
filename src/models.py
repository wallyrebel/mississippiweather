"""
Data models for Mississippi Weather Desk.

Defines dataclasses for weather alerts, forecasts, outlooks, and briefings.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class AlertSeverity(Enum):
    """NWS Alert severity levels."""
    EXTREME = "Extreme"
    SEVERE = "Severe"
    MODERATE = "Moderate"
    MINOR = "Minor"
    UNKNOWN = "Unknown"


class AlertCertainty(Enum):
    """NWS Alert certainty levels."""
    OBSERVED = "Observed"
    LIKELY = "Likely"
    POSSIBLE = "Possible"
    UNLIKELY = "Unlikely"
    UNKNOWN = "Unknown"


class SPCRisk(Enum):
    """SPC categorical risk levels."""
    TSTM = "General Thunder"
    MRGL = "Marginal"
    SLGT = "Slight"
    ENH = "Enhanced"
    MDT = "Moderate"
    HIGH = "High"
    NONE = "None"


class EROCategory(Enum):
    """WPC Excessive Rainfall Outlook categories."""
    MRGL = "Marginal"
    SLGT = "Slight"
    MDT = "Moderate"
    HIGH = "High"
    NONE = "None"


@dataclass
class Alert:
    """NWS weather alert."""
    id: str
    event: str
    headline: str
    description: str
    instruction: Optional[str]
    severity: AlertSeverity
    certainty: AlertCertainty
    onset: Optional[datetime]
    expires: Optional[datetime]
    affected_zones: List[str]
    affected_counties: List[str]
    sender: str
    message_type: str


@dataclass
class GridForecast:
    """NWS gridpoint forecast for a location."""
    location_name: str
    region: str
    lat: float
    lon: float
    grid_id: str
    grid_x: int
    grid_y: int
    
    # Forecast data
    temperature_high: Optional[int] = None
    temperature_low: Optional[int] = None
    pop: Optional[int] = None  # Probability of precipitation (%)
    qpf: Optional[float] = None  # Quantitative precipitation forecast (inches)
    snow_amount: Optional[float] = None  # Snow amount (inches)
    wind_speed: Optional[str] = None
    wind_direction: Optional[str] = None
    conditions: Optional[str] = None
    detailed_forecast: Optional[str] = None
    
    # Multi-day data
    periods: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SPCOutlook:
    """SPC severe weather outlook."""
    day: int  # 1, 2, or 3
    valid_time: Optional[str]
    issue_time: Optional[str]
    outlook_type: str  # "categorical", "tornado", "wind", "hail"
    
    # County-to-risk mapping
    county_risks: Dict[str, SPCRisk] = field(default_factory=dict)
    
    # Raw polygon data for reference
    polygons: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class EROOutlook:
    """WPC Excessive Rainfall Outlook."""
    day: int  # 1, 2, or 3
    valid_time: Optional[str]
    issue_time: Optional[str]
    
    # County-to-risk mapping
    county_risks: Dict[str, EROCategory] = field(default_factory=dict)
    
    # Raw polygon data
    polygons: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TropicalSystem:
    """NHC tropical system data."""
    id: str
    name: str
    classification: str  # TD, TS, HU, etc.
    movement: Optional[str]
    intensity: Optional[int]  # Maximum sustained winds (mph)
    pressure: Optional[int]  # Central pressure (mb)
    lat: Optional[float]
    lon: Optional[float]
    
    # Forecast impacts
    ms_impacts: Optional[str] = None
    wind_threat: Optional[str] = None
    rain_threat: Optional[str] = None
    surge_threat: Optional[str] = None
    timing: Optional[str] = None


@dataclass
class DayForecast:
    """Forecast for a single day."""
    day_name: str  # e.g., "Monday", "Tonight"
    date: Optional[str] = None
    high_temp: Optional[int] = None
    low_temp: Optional[int] = None
    conditions: Optional[str] = None
    detailed: Optional[str] = None
    pop: Optional[int] = None
    wind_speed: Optional[str] = None
    wind_direction: Optional[str] = None


@dataclass
class RegionalSummary:
    """Weather summary for a region."""
    region: str
    anchor_city: str
    
    # Current conditions (from latest observation or first forecast period)
    current_temp: Optional[int] = None
    current_conditions: Optional[str] = None
    current_wind: Optional[str] = None
    current_humidity: Optional[int] = None
    
    # Today's forecast
    high_temp: Optional[int] = None
    low_temp: Optional[int] = None
    
    # Precipitation
    pop: Optional[int] = None
    expected_rainfall: Optional[float] = None
    
    # Extended forecast (7 days)
    daily_forecasts: List[DayForecast] = field(default_factory=list)
    
    # Hazards
    spc_risk_day1: SPCRisk = SPCRisk.NONE
    spc_risk_day2: SPCRisk = SPCRisk.NONE
    ero_risk_day1: EROCategory = EROCategory.NONE
    
    # Conditions
    conditions_summary: Optional[str] = None
    
    # Active alerts for this region
    alerts: List[Alert] = field(default_factory=list)


@dataclass
class WeatherBriefing:
    """Complete weather briefing for Mississippi."""
    generated_at: datetime
    valid_date: str
    time_of_day: str  # "Morning", "Afternoon", "Evening"
    
    # Alerts (official warnings)
    alerts: List[Alert] = field(default_factory=list)
    alerts_by_type: Dict[str, List[Alert]] = field(default_factory=dict)
    
    # Severe weather outlook
    spc_outlooks: List[SPCOutlook] = field(default_factory=list)
    severe_summary: Optional[str] = None
    
    # Heavy rain/flood outlook
    ero_outlooks: List[EROOutlook] = field(default_factory=list)
    rainfall_summary: Optional[str] = None
    
    # Tropical
    tropical_systems: List[TropicalSystem] = field(default_factory=list)
    tropical_summary: Optional[str] = None
    
    # Winter weather
    winter_summary: Optional[str] = None
    
    # Regional forecasts
    regional_summaries: List[RegionalSummary] = field(default_factory=list)
    
    # Statewide overview
    statewide_overview: Optional[str] = None
    
    # Data quality
    data_gaps: List[str] = field(default_factory=list)
    sources_used: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert briefing to dictionary for JSON serialization."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "valid_date": self.valid_date,
            "time_of_day": self.time_of_day,
            "alerts": [
                {
                    "event": a.event,
                    "headline": a.headline,
                    "description": a.description[:500] if a.description else None,
                    "instruction": a.instruction,
                    "severity": a.severity.value,
                    "affected_counties": a.affected_counties,
                    "onset": a.onset.isoformat() if a.onset else None,
                    "expires": a.expires.isoformat() if a.expires else None,
                }
                for a in self.alerts
            ],
            "alerts_by_type": {
                event_type: [
                    {"headline": a.headline, "counties": a.affected_counties}
                    for a in alerts
                ]
                for event_type, alerts in self.alerts_by_type.items()
            },
            "spc_outlooks": [
                {
                    "day": o.day,
                    "outlook_type": o.outlook_type,
                    "county_risks": {k: v.value for k, v in o.county_risks.items() if v != SPCRisk.NONE},
                }
                for o in self.spc_outlooks
            ],
            "severe_summary": self.severe_summary,
            "ero_outlooks": [
                {
                    "day": o.day,
                    "county_risks": {k: v.value for k, v in o.county_risks.items() if v != EROCategory.NONE},
                }
                for o in self.ero_outlooks
            ],
            "rainfall_summary": self.rainfall_summary,
            "tropical_systems": [
                {
                    "name": t.name,
                    "classification": t.classification,
                    "intensity": t.intensity,
                    "ms_impacts": t.ms_impacts,
                    "timing": t.timing,
                }
                for t in self.tropical_systems
            ],
            "tropical_summary": self.tropical_summary,
            "winter_summary": self.winter_summary,
            "regional_summaries": [
                {
                    "region": r.region,
                    "anchor_city": r.anchor_city,
                    "current_temp": r.current_temp,
                    "current_conditions": r.current_conditions,
                    "current_wind": r.current_wind,
                    "high_temp": r.high_temp,
                    "low_temp": r.low_temp,
                    "pop": r.pop,
                    "expected_rainfall": r.expected_rainfall,
                    "spc_risk_day1": r.spc_risk_day1.value,
                    "ero_risk_day1": r.ero_risk_day1.value,
                    "conditions": r.conditions_summary,
                    "alert_count": len(r.alerts),
                    "daily_forecasts": [
                        {
                            "day": d.day_name,
                            "date": d.date,
                            "high": d.high_temp,
                            "low": d.low_temp,
                            "conditions": d.conditions,
                            "pop": d.pop,
                        }
                        for d in r.daily_forecasts
                    ],
                }
                for r in self.regional_summaries
            ],
            "statewide_overview": self.statewide_overview,
            "data_gaps": self.data_gaps,
            "sources_used": self.sources_used,
        }
