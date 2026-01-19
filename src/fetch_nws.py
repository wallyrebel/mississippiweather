"""
NWS API fetcher for Mississippi Weather Desk.

Fetches active alerts and grid-based forecasts from the National Weather Service API.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Alert, AlertSeverity, AlertCertainty, GridForecast

logger = logging.getLogger(__name__)

# NWS API configuration
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "MississippiWeatherDesk/1.0 (myersgrouponline@gmail.com)"

# Rate limiting: NWS recommends no more than 1 request per second
REQUEST_DELAY = 1.0


def get_session() -> requests.Session:
    """Create a requests session with retry logic and proper headers."""
    session = requests.Session()
    
    # Retry configuration
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Required headers for NWS API
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json",
    })
    
    return session


def fetch_active_alerts() -> List[Alert]:
    """
    Fetch all active weather alerts for Mississippi.
    
    Returns:
        List of Alert objects for active alerts in MS.
    """
    logger.info("Fetching active NWS alerts for Mississippi...")
    
    session = get_session()
    url = f"{NWS_API_BASE}/alerts/active?area=MS"
    
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        alerts = []
        features = data.get("features", [])
        
        logger.info(f"Found {len(features)} active alerts")
        
        for feature in features:
            props = feature.get("properties", {})
            
            # Parse severity
            severity_str = props.get("severity", "Unknown")
            try:
                severity = AlertSeverity(severity_str)
            except ValueError:
                severity = AlertSeverity.UNKNOWN
            
            # Parse certainty
            certainty_str = props.get("certainty", "Unknown")
            try:
                certainty = AlertCertainty(certainty_str)
            except ValueError:
                certainty = AlertCertainty.UNKNOWN
            
            # Parse times
            onset = None
            if props.get("onset"):
                try:
                    onset = datetime.fromisoformat(props["onset"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass
            
            expires = None
            if props.get("expires"):
                try:
                    expires = datetime.fromisoformat(props["expires"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass
            
            # Extract affected zones and counties
            affected_zones = props.get("affectedZones", [])
            
            # Parse county names from areaDesc
            area_desc = props.get("areaDesc", "")
            affected_counties = [c.strip() for c in area_desc.split(";") if c.strip()]
            
            alert = Alert(
                id=props.get("id", ""),
                event=props.get("event", "Unknown"),
                headline=props.get("headline", ""),
                description=props.get("description", ""),
                instruction=props.get("instruction"),
                severity=severity,
                certainty=certainty,
                onset=onset,
                expires=expires,
                affected_zones=affected_zones,
                affected_counties=affected_counties,
                sender=props.get("senderName", ""),
                message_type=props.get("messageType", ""),
            )
            alerts.append(alert)
        
        return alerts
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch NWS alerts: {e}")
        return []


def get_point_metadata(lat: float, lon: float, session: requests.Session) -> Optional[Dict[str, Any]]:
    """
    Get NWS grid point metadata for a lat/lon.
    
    Args:
        lat: Latitude
        lon: Longitude
        session: Requests session
        
    Returns:
        Dictionary with gridId, gridX, gridY, and forecast URLs.
    """
    url = f"{NWS_API_BASE}/points/{lat},{lon}"
    
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        props = data.get("properties", {})
        
        return {
            "gridId": props.get("gridId"),
            "gridX": props.get("gridX"),
            "gridY": props.get("gridY"),
            "forecastUrl": props.get("forecast"),
            "forecastHourlyUrl": props.get("forecastHourly"),
            "forecastGridDataUrl": props.get("forecastGridData"),
        }
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to get point metadata for {lat},{lon}: {e}")
        return None


def fetch_grid_forecast(
    location_name: str,
    region: str,
    lat: float,
    lon: float,
    session: Optional[requests.Session] = None
) -> Optional[GridForecast]:
    """
    Fetch NWS grid forecast for a specific location.
    
    Args:
        location_name: Name of the location (city)
        region: Region name
        lat: Latitude
        lon: Longitude
        session: Optional requests session
        
    Returns:
        GridForecast object or None if fetch fails.
    """
    if session is None:
        session = get_session()
    
    logger.debug(f"Fetching forecast for {location_name} ({lat}, {lon})")
    
    # Get grid point metadata
    metadata = get_point_metadata(lat, lon, session)
    if not metadata or not metadata.get("gridId"):
        return None
    
    time.sleep(REQUEST_DELAY)  # Rate limiting
    
    # Create base forecast object
    forecast = GridForecast(
        location_name=location_name,
        region=region,
        lat=lat,
        lon=lon,
        grid_id=metadata["gridId"],
        grid_x=metadata["gridX"],
        grid_y=metadata["gridY"],
    )
    
    # Fetch detailed forecast
    forecast_url = metadata.get("forecastUrl")
    if forecast_url:
        try:
            response = session.get(forecast_url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            periods = data.get("properties", {}).get("periods", [])
            forecast.periods = periods
            
            # Extract key data from first period (today/tonight)
            if periods:
                first = periods[0]
                forecast.conditions = first.get("shortForecast")
                forecast.detailed_forecast = first.get("detailedForecast")
                forecast.wind_speed = first.get("windSpeed")
                forecast.wind_direction = first.get("windDirection")
                
                # Get temperature (daytime high or nighttime low)
                temp = first.get("temperature")
                if first.get("isDaytime"):
                    forecast.temperature_high = temp
                else:
                    forecast.temperature_low = temp
                
                # Also check second period for the other temp
                if len(periods) > 1:
                    second = periods[1]
                    temp2 = second.get("temperature")
                    if second.get("isDaytime"):
                        forecast.temperature_high = temp2
                    else:
                        forecast.temperature_low = temp2
                
                # Extract PoP from detailed forecast if available
                pop = first.get("probabilityOfPrecipitation", {})
                if pop and pop.get("value") is not None:
                    forecast.pop = pop["value"]
                        
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch forecast for {location_name}: {e}")
    
    time.sleep(REQUEST_DELAY)  # Rate limiting
    
    # Fetch gridpoint data for QPF, snow, etc.
    grid_data_url = metadata.get("forecastGridDataUrl")
    if grid_data_url:
        try:
            response = session.get(grid_data_url, timeout=30)
            response.raise_for_status()
            data = response.json()
            props = data.get("properties", {})
            
            # Extract QPF (quantitative precipitation forecast)
            qpf_data = props.get("quantitativePrecipitation", {})
            if qpf_data and qpf_data.get("values"):
                # Sum first 24 hours of QPF
                total_mm = 0
                for val in qpf_data["values"][:24]:
                    if val.get("value") is not None:
                        total_mm += val["value"]
                # Convert mm to inches
                forecast.qpf = round(total_mm / 25.4, 2)
            
            # Extract snow amount
            snow_data = props.get("snowfallAmount", {})
            if snow_data and snow_data.get("values"):
                # Sum first 24 hours
                total_mm = 0
                for val in snow_data["values"][:24]:
                    if val.get("value") is not None:
                        total_mm += val["value"]
                # Convert mm to inches
                forecast.snow_amount = round(total_mm / 25.4, 1)
            
            # Extract max PoP if not already set
            if forecast.pop is None:
                pop_data = props.get("probabilityOfPrecipitation", {})
                if pop_data and pop_data.get("values"):
                    max_pop = 0
                    for val in pop_data["values"][:24]:
                        if val.get("value") is not None:
                            max_pop = max(max_pop, val["value"])
                    forecast.pop = max_pop
                    
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch grid data for {location_name}: {e}")
    
    return forecast


def fetch_anchor_forecasts(anchors_path: Path) -> List[GridForecast]:
    """
    Fetch forecasts for all anchor points.
    
    Args:
        anchors_path: Path to anchors.json configuration file.
        
    Returns:
        List of GridForecast objects for each anchor.
    """
    logger.info("Fetching forecasts for regional anchor points...")
    
    with open(anchors_path) as f:
        anchors_data = json.load(f)
    
    anchors = anchors_data.get("anchors", [])
    forecasts = []
    session = get_session()
    
    for anchor in anchors:
        forecast = fetch_grid_forecast(
            location_name=anchor["city"],
            region=anchor["region"],
            lat=anchor["lat"],
            lon=anchor["lon"],
            session=session,
        )
        
        if forecast:
            forecasts.append(forecast)
            logger.info(f"  ✓ {anchor['city']}: {forecast.conditions}")
        else:
            logger.warning(f"  ✗ Failed to get forecast for {anchor['city']}")
        
        time.sleep(REQUEST_DELAY)  # Rate limiting between anchors
    
    return forecasts


def group_alerts_by_type(alerts: List[Alert]) -> Dict[str, List[Alert]]:
    """
    Group alerts by event type.
    
    Args:
        alerts: List of Alert objects.
        
    Returns:
        Dictionary mapping event type to list of alerts.
    """
    grouped: Dict[str, List[Alert]] = {}
    
    for alert in alerts:
        event_type = alert.event
        if event_type not in grouped:
            grouped[event_type] = []
        grouped[event_type].append(alert)
    
    return grouped


def get_alert_counties(alerts: List[Alert]) -> List[str]:
    """
    Get unique list of counties affected by alerts.
    
    Args:
        alerts: List of Alert objects.
        
    Returns:
        Sorted list of unique county names.
    """
    counties = set()
    for alert in alerts:
        for county in alert.affected_counties:
            # Clean up county name
            county = county.strip()
            if county:
                counties.add(county)
    
    return sorted(list(counties))
