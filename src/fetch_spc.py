"""
SPC (Storm Prediction Center) fetcher for Mississippi Weather Desk.

Fetches severe weather outlooks from NOAA GIS MapServer.
"""

import logging
import time
from typing import List, Dict, Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import SPCOutlook, SPCRisk

logger = logging.getLogger(__name__)

# SPC MapServer endpoints
SPC_MAPSERVER_BASE = "https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/SPC_wx_outlks/MapServer"

# Layer IDs for categorical outlooks
# These IDs are based on the standard SPC MapServer structure
CATEGORICAL_LAYERS = {
    1: {"day": 1, "name": "Day 1 Convective Outlook"},
    2: {"day": 2, "name": "Day 2 Convective Outlook"},
    3: {"day": 3, "name": "Day 3 Convective Outlook"},
}

USER_AGENT = "MississippiWeatherDesk/1.0 (myersgrouponline@gmail.com)"
REQUEST_DELAY = 0.5


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


def parse_spc_risk(label: str) -> SPCRisk:
    """
    Parse SPC risk label to SPCRisk enum.
    
    Args:
        label: Risk label from SPC (e.g., "SLGT", "MDT", "HIGH")
        
    Returns:
        SPCRisk enum value
    """
    if not label:
        return SPCRisk.NONE
    
    label_upper = label.upper().strip()
    
    # Map various label formats to risk levels
    risk_map = {
        "TSTM": SPCRisk.TSTM,
        "GENERAL THUNDER": SPCRisk.TSTM,
        "GENERAL THUNDERSTORM": SPCRisk.TSTM,
        "MRGL": SPCRisk.MRGL,
        "MARGINAL": SPCRisk.MRGL,
        "SLGT": SPCRisk.SLGT,
        "SLIGHT": SPCRisk.SLGT,
        "ENH": SPCRisk.ENH,
        "ENHANCED": SPCRisk.ENH,
        "MDT": SPCRisk.MDT,
        "MODERATE": SPCRisk.MDT,
        "HIGH": SPCRisk.HIGH,
    }
    
    return risk_map.get(label_upper, SPCRisk.NONE)


def fetch_spc_layer(layer_id: int, session: requests.Session) -> Optional[Dict[str, Any]]:
    """
    Fetch a specific SPC outlook layer from MapServer.
    
    Args:
        layer_id: The layer ID to fetch
        session: Requests session
        
    Returns:
        GeoJSON-like dictionary or None if failed
    """
    # Query the layer with geometry
    url = f"{SPC_MAPSERVER_BASE}/{layer_id}/query"
    
    params = {
        "where": "1=1",  # Get all features
        "outFields": "*",  # Get all attributes
        "geometryType": "esriGeometryEnvelope",
        "geometry": "-91.7,30.1,-88.0,35.0",  # Mississippi bounding box
        "spatialRel": "esriSpatialRelIntersects",
        "f": "json",
        "returnGeometry": "true",
    }
    
    try:
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            logger.warning(f"SPC layer {layer_id} error: {data['error']}")
            return None
            
        return data
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch SPC layer {layer_id}: {e}")
        return None


def convert_esri_to_geojson_ring(ring: List) -> List:
    """Convert ESRI ring format to GeoJSON format."""
    return [(pt[0], pt[1]) for pt in ring]


def fetch_spc_outlooks() -> List[SPCOutlook]:
    """
    Fetch SPC Day 1-3 categorical outlooks.
    
    Returns:
        List of SPCOutlook objects with polygon data.
    """
    logger.info("Fetching SPC severe weather outlooks...")
    
    session = get_session()
    outlooks = []
    
    for layer_id, layer_info in CATEGORICAL_LAYERS.items():
        day = layer_info["day"]
        logger.debug(f"Fetching Day {day} outlook (layer {layer_id})...")
        
        data = fetch_spc_layer(layer_id, session)
        time.sleep(REQUEST_DELAY)
        
        if not data:
            continue
        
        features = data.get("features", [])
        
        if not features:
            logger.debug(f"No Day {day} outlook polygons found")
            outlook = SPCOutlook(
                day=day,
                valid_time=None,
                issue_time=None,
                outlook_type="categorical",
                county_risks={},
                polygons=[],
            )
            outlooks.append(outlook)
            continue
        
        # Extract polygons
        polygons = []
        for feature in features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})
            
            # Get risk category
            # Different layers may use different attribute names
            risk_label = (
                attrs.get("dn") or 
                attrs.get("DN") or 
                attrs.get("LABEL") or 
                attrs.get("label") or
                attrs.get("CATEGORY") or
                ""
            )
            
            risk = parse_spc_risk(str(risk_label))
            
            # Convert geometry
            rings = geom.get("rings", [])
            if rings:
                polygon_data = {
                    "risk": risk,
                    "risk_label": risk_label,
                    "rings": [convert_esri_to_geojson_ring(r) for r in rings],
                    "attributes": attrs,
                }
                polygons.append(polygon_data)
        
        outlook = SPCOutlook(
            day=day,
            valid_time=None,
            issue_time=None,
            outlook_type="categorical",
            county_risks={},  # Will be populated by geo intersection
            polygons=polygons,
        )
        
        logger.info(f"  Day {day}: {len(polygons)} risk polygons found")
        outlooks.append(outlook)
    
    return outlooks


def get_max_risk_from_outlooks(outlooks: List[SPCOutlook], day: int = 1) -> SPCRisk:
    """
    Get the maximum SPC risk level from outlooks for a given day.
    
    Args:
        outlooks: List of SPCOutlook objects
        day: Day number (1, 2, or 3)
        
    Returns:
        Maximum SPCRisk found
    """
    risk_priority = {
        SPCRisk.NONE: 0,
        SPCRisk.TSTM: 1,
        SPCRisk.MRGL: 2,
        SPCRisk.SLGT: 3,
        SPCRisk.ENH: 4,
        SPCRisk.MDT: 5,
        SPCRisk.HIGH: 6,
    }
    
    max_risk = SPCRisk.NONE
    
    for outlook in outlooks:
        if outlook.day == day:
            for polygon in outlook.polygons:
                risk = polygon.get("risk", SPCRisk.NONE)
                if risk_priority.get(risk, 0) > risk_priority.get(max_risk, 0):
                    max_risk = risk
    
    return max_risk
