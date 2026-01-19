"""
WPC (Weather Prediction Center) fetcher for Mississippi Weather Desk.

Fetches Excessive Rainfall Outlook (ERO) and QPF guidance from NOAA services.
"""

import logging
import time
from typing import List, Dict, Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import EROOutlook, EROCategory

logger = logging.getLogger(__name__)

# WPC MapServer endpoints
WPC_MAPSERVER_BASE = "https://mapservices.weather.noaa.gov/vector/rest/services/outlooks"

# ERO (Excessive Rainfall Outlook) layers
ERO_SERVICE = f"{WPC_MAPSERVER_BASE}/wpc_qpf/MapServer"

# Layer IDs may vary - these are common layer configurations
ERO_LAYERS = {
    1: {"day": 1, "name": "Day 1 ERO"},
    2: {"day": 2, "name": "Day 2 ERO"},  
    3: {"day": 3, "name": "Day 3 ERO"},
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


def parse_ero_category(label: str) -> EROCategory:
    """
    Parse ERO category label to EROCategory enum.
    
    Args:
        label: Category label from WPC
        
    Returns:
        EROCategory enum value
    """
    if not label:
        return EROCategory.NONE
    
    label_upper = label.upper().strip()
    
    category_map = {
        "MRGL": EROCategory.MRGL,
        "MARGINAL": EROCategory.MRGL,
        "SLGT": EROCategory.SLGT,
        "SLIGHT": EROCategory.SLGT,
        "MDT": EROCategory.MDT,
        "MODERATE": EROCategory.MDT,
        "HIGH": EROCategory.HIGH,
    }
    
    return category_map.get(label_upper, EROCategory.NONE)


def fetch_ero_layer(layer_id: int, session: requests.Session) -> Optional[Dict[str, Any]]:
    """
    Fetch a specific ERO layer from WPC MapServer.
    
    Args:
        layer_id: The layer ID to fetch
        session: Requests session
        
    Returns:
        JSON response dictionary or None if failed
    """
    url = f"{ERO_SERVICE}/{layer_id}/query"
    
    # Mississippi bounding box
    params = {
        "where": "1=1",
        "outFields": "*",
        "geometryType": "esriGeometryEnvelope",
        "geometry": "-91.7,30.1,-88.0,35.0",
        "spatialRel": "esriSpatialRelIntersects",
        "f": "json",
        "returnGeometry": "true",
    }
    
    try:
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            logger.debug(f"WPC layer {layer_id} error: {data.get('error')}")
            return None
            
        return data
        
    except requests.exceptions.RequestException as e:
        logger.debug(f"Failed to fetch WPC layer {layer_id}: {e}")
        return None


def discover_ero_layers(session: requests.Session) -> Dict[int, Dict]:
    """
    Discover available ERO-related layers from WPC MapServer.
    
    Returns:
        Dictionary mapping layer IDs to layer info.
    """
    # Try to get service metadata
    url = f"{ERO_SERVICE}?f=json"
    
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        layers = data.get("layers", [])
        ero_layers = {}
        
        for layer in layers:
            name = layer.get("name", "").lower()
            layer_id = layer.get("id")
            
            # Look for ERO or excessive rainfall layers
            if "ero" in name or "excessive" in name or "rainfall" in name:
                # Try to determine the day
                day = 1
                if "day 2" in name or "day2" in name:
                    day = 2
                elif "day 3" in name or "day3" in name:
                    day = 3
                    
                ero_layers[layer_id] = {"day": day, "name": layer.get("name")}
                
        return ero_layers
        
    except requests.exceptions.RequestException as e:
        logger.debug(f"Could not discover WPC layers: {e}")
        return {}


def fetch_ero_outlooks() -> List[EROOutlook]:
    """
    Fetch WPC Excessive Rainfall Outlooks for Days 1-3.
    
    Returns:
        List of EROOutlook objects.
    """
    logger.info("Fetching WPC Excessive Rainfall Outlooks...")
    
    session = get_session()
    outlooks = []
    
    # First try to discover available layers
    available_layers = discover_ero_layers(session)
    
    if available_layers:
        layers_to_fetch = available_layers
    else:
        # Fall back to default layer IDs
        layers_to_fetch = ERO_LAYERS
    
    for layer_id, layer_info in layers_to_fetch.items():
        day = layer_info.get("day", 1)
        
        data = fetch_ero_layer(layer_id, session)
        time.sleep(REQUEST_DELAY)
        
        if not data:
            continue
            
        features = data.get("features", [])
        
        if not features:
            outlook = EROOutlook(
                day=day,
                valid_time=None,
                issue_time=None,
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
            
            # Get category
            category_label = (
                attrs.get("CATEGORY") or
                attrs.get("category") or
                attrs.get("LABEL") or
                attrs.get("label") or
                attrs.get("dn") or
                ""
            )
            
            category = parse_ero_category(str(category_label))
            
            rings = geom.get("rings", [])
            if rings:
                polygon_data = {
                    "category": category,
                    "category_label": category_label,
                    "rings": rings,
                    "attributes": attrs,
                }
                polygons.append(polygon_data)
        
        outlook = EROOutlook(
            day=day,
            valid_time=None,
            issue_time=None,
            county_risks={},
            polygons=polygons,
        )
        
        logger.info(f"  Day {day} ERO: {len(polygons)} risk polygons found")
        outlooks.append(outlook)
    
    # If no outlooks found, return empty list but log it
    if not outlooks:
        logger.info("  No ERO data available (this is normal when no excessive rain is expected)")
        # Add empty outlooks for days 1-3
        for day in [1, 2, 3]:
            outlooks.append(EROOutlook(
                day=day,
                valid_time=None,
                issue_time=None,
                county_risks={},
                polygons=[],
            ))
    
    return outlooks


def fetch_qpf_guidance() -> Optional[Dict[str, Any]]:
    """
    Fetch QPF (Quantitative Precipitation Forecast) guidance if available.
    
    This is a supplementary data source; NWS gridpoint QPF is primary.
    
    Returns:
        QPF data dictionary or None if not available.
    """
    logger.debug("Attempting to fetch WPC QPF guidance...")
    
    # WPC QPF often requires specific image/grid products
    # For this implementation, we rely primarily on NWS gridpoint QPF
    # This function is a placeholder for future enhancement
    
    return None


def get_max_ero_from_outlooks(outlooks: List[EROOutlook], day: int = 1) -> EROCategory:
    """
    Get the maximum ERO category from outlooks for a given day.
    
    Args:
        outlooks: List of EROOutlook objects
        day: Day number (1, 2, or 3)
        
    Returns:
        Maximum EROCategory found
    """
    category_priority = {
        EROCategory.NONE: 0,
        EROCategory.MRGL: 1,
        EROCategory.SLGT: 2,
        EROCategory.MDT: 3,
        EROCategory.HIGH: 4,
    }
    
    max_category = EROCategory.NONE
    
    for outlook in outlooks:
        if outlook.day == day:
            for polygon in outlook.polygons:
                category = polygon.get("category", EROCategory.NONE)
                if category_priority.get(category, 0) > category_priority.get(max_category, 0):
                    max_category = category
    
    return max_category
