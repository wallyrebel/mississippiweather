"""
Weather analysis and briefing builder for Mississippi Weather Desk.

Aggregates data from all sources and builds a structured briefing.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import pytz

from .models import (
    Alert, GridForecast, SPCOutlook, EROOutlook, TropicalSystem,
    RegionalSummary, WeatherBriefing, SPCRisk, EROCategory, DayForecast
)
from .fetch_nws import fetch_active_alerts, fetch_anchor_forecasts, group_alerts_by_type
from .fetch_spc import fetch_spc_outlooks, get_max_risk_from_outlooks
from .fetch_wpc import fetch_ero_outlooks, get_max_ero_from_outlooks
from .fetch_nhc import fetch_tropical_systems
from .geo import (
    load_county_polygons, load_counties_config, get_counties_in_outlook,
    get_counties_by_region, get_highest_risk_by_region
)

logger = logging.getLogger(__name__)

CT_TIMEZONE = pytz.timezone("America/Chicago")


def get_time_of_day() -> str:
    """Get current time of day in Central Time."""
    now = datetime.now(CT_TIMEZONE)
    hour = now.hour
    
    if 4 <= hour < 11:
        return "Morning"
    elif 11 <= hour < 17:
        return "Afternoon"
    else:
        return "Evening"


def extract_daily_forecasts(periods: List[Dict[str, Any]]) -> List[DayForecast]:
    """
    Extract 7-day forecast from NWS periods.
    
    Args:
        periods: List of NWS forecast periods
        
    Returns:
        List of DayForecast objects (up to 7 days)
    """
    daily_forecasts = []
    
    # NWS gives us periods like "Today", "Tonight", "Monday", "Monday Night", etc.
    # We need to pair them up into daily forecasts
    i = 0
    while i < len(periods) and len(daily_forecasts) < 7:
        period = periods[i]
        day_name = period.get("name", "")
        
        # Create day forecast
        day_forecast = DayForecast(
            day_name=day_name.replace(" Night", "").replace("Tonight", "Today"),
            conditions=period.get("shortForecast"),
            detailed=period.get("detailedForecast"),
            wind_speed=period.get("windSpeed"),
            wind_direction=period.get("windDirection"),
        )
        
        # Get temperature
        temp = period.get("temperature")
        is_day = period.get("isDaytime", True)
        
        if is_day:
            day_forecast.high_temp = temp
        else:
            day_forecast.low_temp = temp
        
        # Get PoP
        pop = period.get("probabilityOfPrecipitation", {})
        if pop and pop.get("value") is not None:
            day_forecast.pop = pop["value"]
        
        # Check next period for night/day pair
        if i + 1 < len(periods):
            next_period = periods[i + 1]
            next_name = next_period.get("name", "")
            
            # If this is day and next is the corresponding night
            if is_day and ("Night" in next_name or next_name == "Tonight"):
                day_forecast.low_temp = next_period.get("temperature")
                
                # Also get night PoP if higher
                next_pop = next_period.get("probabilityOfPrecipitation", {})
                if next_pop and next_pop.get("value"):
                    if day_forecast.pop is None or next_pop["value"] > day_forecast.pop:
                        day_forecast.pop = next_pop["value"]
                
                i += 1  # Skip the night period
            # If this is night and next is the corresponding day  
            elif not is_day and "Night" not in next_name:
                day_forecast.high_temp = next_period.get("temperature")
                day_forecast.conditions = next_period.get("shortForecast")
                i += 1

        daily_forecasts.append(day_forecast)
        i += 1
    
    return daily_forecasts


def build_regional_summaries(
    forecasts: List[GridForecast],
    alerts: List[Alert],
    spc_outlooks: List[SPCOutlook],
    ero_outlooks: List[EROOutlook],
    counties_config: List[Dict[str, Any]]
) -> List[RegionalSummary]:
    """
    Build weather summaries for each region including 7-day forecasts.
    
    Args:
        forecasts: List of GridForecast objects for anchor points
        alerts: List of active alerts
        spc_outlooks: SPC outlooks
        ero_outlooks: ERO outlooks
        counties_config: County configuration
        
    Returns:
        List of RegionalSummary objects
    """
    summaries = []
    
    # Get counties by region
    counties_by_region = get_counties_by_region(counties_config)
    
    # Get SPC/ERO risks by county
    spc_county_risks = {}
    for outlook in spc_outlooks:
        if outlook.day == 1:
            spc_county_risks.update(outlook.county_risks)
    
    ero_county_risks = {}
    for outlook in ero_outlooks:
        if outlook.day == 1:
            ero_county_risks.update(outlook.county_risks)
    
    # Create summary for each forecast (anchor point)
    for forecast in forecasts:
        region = forecast.region
        
        # Get region-level SPC risk
        region_counties = counties_by_region.get(region, [])
        max_spc = SPCRisk.NONE
        max_ero = EROCategory.NONE
        
        for county in region_counties:
            county_spc = spc_county_risks.get(county, SPCRisk.NONE)
            county_ero = ero_county_risks.get(county, EROCategory.NONE)
            
            if isinstance(county_spc, SPCRisk):
                risk_order = [SPCRisk.NONE, SPCRisk.TSTM, SPCRisk.MRGL, SPCRisk.SLGT, SPCRisk.ENH, SPCRisk.MDT, SPCRisk.HIGH]
                if risk_order.index(county_spc) > risk_order.index(max_spc):
                    max_spc = county_spc
            
            if isinstance(county_ero, EROCategory):
                ero_order = [EROCategory.NONE, EROCategory.MRGL, EROCategory.SLGT, EROCategory.MDT, EROCategory.HIGH]
                if ero_order.index(county_ero) > ero_order.index(max_ero):
                    max_ero = county_ero
        
        # Get alerts for this region's counties
        region_alerts = []
        for alert in alerts:
            for affected in alert.affected_counties:
                if any(county.lower() in affected.lower() for county in region_counties):
                    region_alerts.append(alert)
                    break
        
        # Extract 7-day forecast from periods
        daily_forecasts = extract_daily_forecasts(forecast.periods)
        
        # Current conditions from first period
        current_temp = forecast.temperature_high if forecast.temperature_high else forecast.temperature_low
        current_wind = f"{forecast.wind_speed} {forecast.wind_direction}" if forecast.wind_speed else None
        
        summary = RegionalSummary(
            region=region,
            anchor_city=forecast.location_name,
            current_temp=current_temp,
            current_conditions=forecast.conditions,
            current_wind=current_wind,
            high_temp=forecast.temperature_high,
            low_temp=forecast.temperature_low,
            pop=forecast.pop,
            expected_rainfall=forecast.qpf,
            daily_forecasts=daily_forecasts,
            spc_risk_day1=max_spc,
            spc_risk_day2=SPCRisk.NONE,
            ero_risk_day1=max_ero,
            conditions_summary=forecast.conditions,
            alerts=region_alerts,
        )
        summaries.append(summary)
    
    return summaries


def build_severe_summary(
    spc_outlooks: List[SPCOutlook],
    counties_config: List[Dict[str, Any]]
) -> Optional[str]:
    """Build a text summary of severe weather potential."""
    
    risk_labels = {
        SPCRisk.NONE: None,
        SPCRisk.TSTM: "general thunderstorm risk",
        SPCRisk.MRGL: "marginal severe risk",
        SPCRisk.SLGT: "slight severe risk",
        SPCRisk.ENH: "enhanced severe risk",
        SPCRisk.MDT: "moderate severe risk",
        SPCRisk.HIGH: "HIGH severe risk",
    }
    
    summaries = []
    
    for outlook in spc_outlooks:
        if not outlook.county_risks:
            continue
        
        # Find highest risk
        max_risk = SPCRisk.NONE
        affected_counties = []
        
        for county, risk in outlook.county_risks.items():
            if risk != SPCRisk.NONE:
                affected_counties.append(county)
                risk_order = list(risk_labels.keys())
                if risk_order.index(risk) > risk_order.index(max_risk):
                    max_risk = risk
        
        if max_risk != SPCRisk.NONE:
            risk_text = risk_labels.get(max_risk, "severe risk")
            summaries.append(f"Day {outlook.day}: {risk_text.title()} for portions of Mississippi")
    
    if summaries:
        return " | ".join(summaries)
    
    # Check if there's at least general thunder
    max_overall = get_max_risk_from_outlooks(spc_outlooks, day=1)
    if max_overall != SPCRisk.NONE:
        return f"Day 1: {risk_labels.get(max_overall, 'thunder').title()} possible"
    
    return None


def build_rainfall_summary(
    ero_outlooks: List[EROOutlook],
    forecasts: List[GridForecast]
) -> Optional[str]:
    """Build a text summary of rainfall/flood potential."""
    
    # Check ERO
    max_ero = get_max_ero_from_outlooks(ero_outlooks, day=1)
    
    ero_text = None
    if max_ero != EROCategory.NONE:
        ero_labels = {
            EROCategory.MRGL: "marginal excessive rainfall risk",
            EROCategory.SLGT: "slight excessive rainfall risk",
            EROCategory.MDT: "moderate excessive rainfall risk",
            EROCategory.HIGH: "HIGH excessive rainfall risk",
        }
        ero_text = ero_labels.get(max_ero)
    
    # Check QPF from forecasts
    max_qpf = 0
    max_qpf_location = None
    
    for forecast in forecasts:
        if forecast.qpf and forecast.qpf > max_qpf:
            max_qpf = forecast.qpf
            max_qpf_location = forecast.location_name
    
    parts = []
    
    if ero_text:
        parts.append(ero_text.title())
    
    if max_qpf >= 1.0:
        parts.append(f"Up to {max_qpf:.1f} inches possible near {max_qpf_location}")
    elif max_qpf > 0:
        parts.append(f"Light rainfall amounts expected (up to {max_qpf:.1f} inches)")
    
    if parts:
        return ". ".join(parts)
    
    return None


def build_winter_summary(forecasts: List[GridForecast]) -> Optional[str]:
    """Build a text summary of winter weather potential."""
    
    max_snow = 0
    snow_location = None
    
    min_temp = None
    cold_location = None
    
    for forecast in forecasts:
        if forecast.snow_amount and forecast.snow_amount > max_snow:
            max_snow = forecast.snow_amount
            snow_location = forecast.location_name
        
        if forecast.temperature_low is not None:
            if min_temp is None or forecast.temperature_low < min_temp:
                min_temp = forecast.temperature_low
                cold_location = forecast.location_name
    
    parts = []
    
    if max_snow >= 0.5:
        parts.append(f"Snow possible: up to {max_snow:.1f} inches near {snow_location}")
    
    if min_temp is not None and min_temp <= 32:
        parts.append(f"Freezing temperatures expected (low of {min_temp}°F near {cold_location})")
    
    if parts:
        return ". ".join(parts)
    
    return None


def build_tropical_summary(systems: List[TropicalSystem]) -> Optional[str]:
    """Build a text summary of tropical threats."""
    
    if not systems:
        return None
    
    summaries = []
    
    for system in systems:
        name = system.name
        classification = system.classification
        
        if system.ms_impacts:
            summaries.append(f"{classification} {name}: {system.ms_impacts}")
        else:
            summaries.append(f"{classification} {name} being monitored")
    
    if summaries:
        return " | ".join(summaries)
    
    return None


def build_statewide_overview(
    alerts: List[Alert],
    regional_summaries: List[RegionalSummary],
    severe_summary: Optional[str],
    rainfall_summary: Optional[str],
    tropical_summary: Optional[str]
) -> str:
    """Build a statewide weather overview."""
    
    parts = []
    
    # Alert summary
    if alerts:
        alert_types = set(a.event for a in alerts)
        parts.append(f"{len(alerts)} active alert(s) including: {', '.join(sorted(alert_types))}")
    else:
        parts.append("No active weather alerts for Mississippi")
    
    # Temperature range
    highs = [s.high_temp for s in regional_summaries if s.high_temp is not None]
    lows = [s.low_temp for s in regional_summaries if s.low_temp is not None]
    
    if highs:
        parts.append(f"Highs ranging from {min(highs)}°F to {max(highs)}°F across the state")
    if lows:
        parts.append(f"Lows ranging from {min(lows)}°F to {max(lows)}°F")
    
    # Hazard summaries
    if tropical_summary:
        parts.append(f"Tropical: {tropical_summary}")
    if severe_summary:
        parts.append(f"Severe: {severe_summary}")
    if rainfall_summary:
        parts.append(f"Rainfall: {rainfall_summary}")
    
    return ". ".join(parts)


def build_briefing(config_dir: Path, data_dir: Path) -> WeatherBriefing:
    """
    Build complete weather briefing for Mississippi.
    
    Args:
        config_dir: Path to config directory
        data_dir: Path to data directory
        
    Returns:
        WeatherBriefing object with all data
    """
    logger.info("=" * 60)
    logger.info("Building Mississippi Weather Briefing")
    logger.info("=" * 60)
    
    now = datetime.now(CT_TIMEZONE)
    time_of_day = get_time_of_day()
    valid_date = now.strftime("%Y-%m-%d")
    
    # Track data sources used and gaps
    sources_used = []
    data_gaps = []
    
    # Load configuration
    counties_config = load_counties_config(config_dir / "ms_counties.json")
    anchors_path = config_dir / "anchors.json"
    counties_geojson_path = data_dir / "ms_counties.geojson"
    counties_geojson = load_county_polygons(counties_geojson_path)
    
    # Fetch NWS alerts
    try:
        alerts = fetch_active_alerts()
        sources_used.append("NWS Active Alerts API")
    except Exception as e:
        logger.error(f"Failed to fetch NWS alerts: {e}")
        alerts = []
        data_gaps.append("NWS alerts unavailable")
    
    alerts_by_type = group_alerts_by_type(alerts)
    
    # Fetch NWS forecasts for anchor points
    try:
        forecasts = fetch_anchor_forecasts(anchors_path)
        sources_used.append("NWS Gridpoint Forecast API")
    except Exception as e:
        logger.error(f"Failed to fetch NWS forecasts: {e}")
        forecasts = []
        data_gaps.append("NWS forecasts unavailable")
    
    # Fetch SPC outlooks
    try:
        spc_outlooks = fetch_spc_outlooks()
        sources_used.append("SPC Convective Outlooks (NOAA MapServer)")
        
        # Compute county intersections
        for outlook in spc_outlooks:
            if outlook.polygons:
                outlook.county_risks = get_counties_in_outlook(
                    outlook.polygons,
                    counties_geojson,
                    counties_config
                )
    except Exception as e:
        logger.error(f"Failed to fetch SPC outlooks: {e}")
        spc_outlooks = []
        data_gaps.append("SPC outlooks unavailable")
    
    # Fetch WPC ERO
    try:
        ero_outlooks = fetch_ero_outlooks()
        sources_used.append("WPC Excessive Rainfall Outlook (NOAA MapServer)")
        
        # Compute county intersections
        for outlook in ero_outlooks:
            if outlook.polygons:
                outlook.county_risks = get_counties_in_outlook(
                    outlook.polygons,
                    counties_geojson,
                    counties_config
                )
    except Exception as e:
        logger.error(f"Failed to fetch WPC ERO: {e}")
        ero_outlooks = []
        data_gaps.append("WPC ERO unavailable")
    
    # Fetch NHC tropical data
    try:
        tropical_systems = fetch_tropical_systems()
        if tropical_systems:
            sources_used.append("NHC Current Storms JSON")
    except Exception as e:
        logger.error(f"Failed to fetch NHC data: {e}")
        tropical_systems = []
        # Not a data gap if no storms - only log if fetch failed
        data_gaps.append("NHC data unavailable")
    
    # Build summaries
    severe_summary = build_severe_summary(spc_outlooks, counties_config)
    rainfall_summary = build_rainfall_summary(ero_outlooks, forecasts)
    winter_summary = build_winter_summary(forecasts)
    tropical_summary = build_tropical_summary(tropical_systems)
    
    regional_summaries = build_regional_summaries(
        forecasts, alerts, spc_outlooks, ero_outlooks, counties_config
    )
    
    statewide_overview = build_statewide_overview(
        alerts, regional_summaries, severe_summary, rainfall_summary, tropical_summary
    )
    
    # Build briefing
    briefing = WeatherBriefing(
        generated_at=now,
        valid_date=valid_date,
        time_of_day=time_of_day,
        alerts=alerts,
        alerts_by_type=alerts_by_type,
        spc_outlooks=spc_outlooks,
        severe_summary=severe_summary,
        ero_outlooks=ero_outlooks,
        rainfall_summary=rainfall_summary,
        tropical_systems=tropical_systems,
        tropical_summary=tropical_summary,
        winter_summary=winter_summary,
        regional_summaries=regional_summaries,
        statewide_overview=statewide_overview,
        data_gaps=data_gaps,
        sources_used=sources_used,
    )
    
    logger.info("=" * 60)
    logger.info(f"Briefing complete. {len(alerts)} alerts, {len(forecasts)} forecasts")
    logger.info(f"Sources: {', '.join(sources_used)}")
    if data_gaps:
        logger.warning(f"Data gaps: {', '.join(data_gaps)}")
    logger.info("=" * 60)
    
    return briefing
