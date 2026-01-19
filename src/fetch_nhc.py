"""
NHC (National Hurricane Center) fetcher for Mississippi Weather Desk.

Fetches active tropical system data when available.
"""

import logging
from typing import List, Optional
from math import radians, sin, cos, sqrt, atan2

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import TropicalSystem

logger = logging.getLogger(__name__)

# NHC endpoints
NHC_CURRENT_STORMS = "https://www.nhc.noaa.gov/CurrentStorms.json"
NHC_FORECAST_BASE = "https://www.nhc.noaa.gov"

USER_AGENT = "MississippiWeatherDesk/1.0 (myersgrouponline@gmail.com)"

# Mississippi bounding box for impact assessment
MS_CENTER_LAT = 32.5
MS_CENTER_LON = -89.75
MS_IMPACT_RADIUS_MILES = 400  # Consider impacts within this radius


def get_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    session.headers.update({
        "User-Agent": USER_AGENT,
    })
    
    return session


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points in miles.
    
    Args:
        lat1, lon1: First point coordinates
        lat2, lon2: Second point coordinates
        
    Returns:
        Distance in miles
    """
    R = 3959  # Earth's radius in miles
    
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    
    a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    return R * c


def assess_ms_impacts(lat: float, lon: float, intensity: int, classification: str) -> dict:
    """
    Assess potential Mississippi impacts from a tropical system.
    
    Args:
        lat: Storm latitude
        lon: Storm longitude
        intensity: Maximum sustained winds (mph)
        classification: Storm classification (TD, TS, HU, etc.)
        
    Returns:
        Dictionary with impact assessments
    """
    distance = haversine_distance(lat, lon, MS_CENTER_LAT, MS_CENTER_LON)
    
    impacts = {
        "distance_miles": round(distance),
        "within_impact_zone": distance <= MS_IMPACT_RADIUS_MILES,
        "summary": None,
        "wind_threat": None,
        "rain_threat": None,
        "surge_threat": None,
    }
    
    if distance > MS_IMPACT_RADIUS_MILES:
        impacts["summary"] = f"System is {round(distance)} miles from Mississippi - monitoring"
        return impacts
    
    # Assess threats based on distance and intensity
    if distance < 100:
        impacts["summary"] = "Direct threat to Mississippi"
        if intensity >= 74:
            impacts["wind_threat"] = "Hurricane-force winds possible"
            impacts["rain_threat"] = "Very heavy rainfall expected (5-15+ inches possible)"
            impacts["surge_threat"] = "Significant storm surge threat to coastal areas"
        elif intensity >= 39:
            impacts["wind_threat"] = "Tropical storm-force winds likely"
            impacts["rain_threat"] = "Heavy rainfall expected (3-8 inches possible)"
            impacts["surge_threat"] = "Storm surge possible along coast"
        else:
            impacts["wind_threat"] = "Gusty winds possible"
            impacts["rain_threat"] = "Moderate to heavy rainfall expected"
    elif distance < 200:
        impacts["summary"] = "Peripheral impacts possible for Mississippi"
        if intensity >= 74:
            impacts["wind_threat"] = "Tropical storm-force winds possible"
            impacts["rain_threat"] = "Heavy rainfall possible (2-6 inches)"
        else:
            impacts["wind_threat"] = "Gusty winds possible"
            impacts["rain_threat"] = "Moderate rainfall possible"
    else:
        impacts["summary"] = f"System {round(distance)} miles away - indirect impacts possible"
        impacts["rain_threat"] = "Some rainfall possible from outer bands"
    
    return impacts


def fetch_tropical_systems() -> List[TropicalSystem]:
    """
    Fetch active tropical systems from NHC.
    
    Returns:
        List of TropicalSystem objects for systems potentially affecting Mississippi.
    """
    logger.info("Fetching NHC tropical system data...")
    
    session = get_session()
    systems = []
    
    try:
        response = session.get(NHC_CURRENT_STORMS, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        active_storms = data.get("activeStorms", [])
        
        if not active_storms:
            logger.info("  No active tropical systems")
            return []
        
        logger.info(f"  Found {len(active_storms)} active tropical system(s)")
        
        for storm in active_storms:
            storm_id = storm.get("id", "")
            name = storm.get("name", "Unknown")
            classification = storm.get("classification", "")
            
            # Get position - may be in different formats
            lat = storm.get("latitude") or storm.get("lat")
            lon = storm.get("longitude") or storm.get("lon")
            
            # Convert string coordinates if needed
            if isinstance(lat, str):
                try:
                    lat = float(lat.replace("N", "").replace("S", "-"))
                except:
                    lat = None
            if isinstance(lon, str):
                try:
                    lon = float(lon.replace("W", "-").replace("E", ""))
                except:
                    lon = None
            
            intensity = storm.get("intensity") or storm.get("maxWind")
            if isinstance(intensity, str):
                try:
                    intensity = int(intensity.replace("kt", "").replace("mph", "").strip())
                except:
                    intensity = None
            
            pressure = storm.get("pressure") or storm.get("minPressure")
            if isinstance(pressure, str):
                try:
                    pressure = int(pressure.replace("mb", "").strip())
                except:
                    pressure = None
            
            movement = storm.get("movement") or storm.get("motion")
            
            # Assess Mississippi impacts
            impacts = {}
            if lat and lon:
                impacts = assess_ms_impacts(lat, lon, intensity or 0, classification)
            
            # Only include systems within impact zone or all if we can't determine
            if not impacts or impacts.get("within_impact_zone", True) or impacts.get("distance_miles", 0) < 600:
                system = TropicalSystem(
                    id=storm_id,
                    name=name,
                    classification=classification,
                    movement=movement,
                    intensity=intensity,
                    pressure=pressure,
                    lat=lat,
                    lon=lon,
                    ms_impacts=impacts.get("summary"),
                    wind_threat=impacts.get("wind_threat"),
                    rain_threat=impacts.get("rain_threat"),
                    surge_threat=impacts.get("surge_threat"),
                    timing=storm.get("advisoryDate"),
                )
                systems.append(system)
                logger.info(f"    {name} ({classification}): {impacts.get('summary', 'Assessing impacts')}")
        
        return systems
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch NHC data: {e}")
        return []
    except (KeyError, ValueError, TypeError) as e:
        logger.warning(f"Error parsing NHC data: {e}")
        return []


def has_tropical_threat() -> bool:
    """
    Quick check if there are any tropical systems potentially threatening Mississippi.
    
    Returns:
        True if there are systems within impact range.
    """
    systems = fetch_tropical_systems()
    return len(systems) > 0
