"""
Geospatial utilities for Mississippi Weather Desk.

Handles polygon intersection to determine which counties are affected by 
SPC/WPC outlook polygons.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import geospatial libraries
try:
    from shapely.geometry import shape, Point, Polygon, MultiPolygon
    from shapely.ops import unary_union
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False
    logger.warning("Shapely not available - polygon intersection disabled")

try:
    import geopandas as gpd
    GEOPANDAS_AVAILABLE = True
except ImportError:
    GEOPANDAS_AVAILABLE = False
    logger.warning("GeoPandas not available - will use fallback methods")


def load_county_polygons(geojson_path: Path) -> Optional[Dict[str, Any]]:
    """
    Load Mississippi county polygons from GeoJSON file.
    
    Args:
        geojson_path: Path to the GeoJSON file
        
    Returns:
        Parsed GeoJSON dictionary or None if file doesn't exist
    """
    if not geojson_path.exists():
        logger.warning(f"County GeoJSON not found: {geojson_path}")
        return None
    
    try:
        with open(geojson_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load county GeoJSON: {e}")
        return None


def load_counties_config(config_path: Path) -> List[Dict[str, Any]]:
    """
    Load county configuration with centroids.
    
    Args:
        config_path: Path to ms_counties.json
        
    Returns:
        List of county dictionaries
    """
    try:
        with open(config_path) as f:
            data = json.load(f)
            return data.get("counties", [])
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load counties config: {e}")
        return []


def point_in_polygon(point: Tuple[float, float], polygon_rings: List[List]) -> bool:
    """
    Simple ray-casting algorithm to check if point is in polygon.
    
    This is a fallback when Shapely is not available.
    
    Args:
        point: (lon, lat) tuple
        polygon_rings: List of rings, each ring is a list of (lon, lat) tuples
        
    Returns:
        True if point is inside polygon
    """
    if not polygon_rings:
        return False
    
    # Use the outer ring (first ring)
    ring = polygon_rings[0]
    if not ring:
        return False
    
    x, y = point
    n = len(ring)
    inside = False
    
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        
        j = i
    
    return inside


def intersect_counties_with_polygon_shapely(
    polygon_rings: List[List],
    counties_geojson: Dict[str, Any]
) -> List[str]:
    """
    Find counties that intersect with a polygon using Shapely.
    
    Args:
        polygon_rings: List of polygon rings in ESRI format
        counties_geojson: County boundaries GeoJSON
        
    Returns:
        List of county names that intersect
    """
    if not SHAPELY_AVAILABLE:
        return []
    
    try:
        # Convert ESRI rings to Shapely polygon
        if len(polygon_rings) == 1:
            outlook_poly = Polygon(polygon_rings[0])
        else:
            # Outer ring + holes
            outlook_poly = Polygon(polygon_rings[0], polygon_rings[1:])
        
        if not outlook_poly.is_valid:
            outlook_poly = outlook_poly.buffer(0)  # Fix invalid geometries
        
        intersecting = []
        
        for feature in counties_geojson.get("features", []):
            props = feature.get("properties", {})
            county_name = props.get("NAME") or props.get("name") or props.get("COUNTY")
            
            if not county_name:
                continue
            
            geom = feature.get("geometry")
            if not geom:
                continue
            
            try:
                county_shape = shape(geom)
                if county_shape.intersects(outlook_poly):
                    intersecting.append(county_name)
            except Exception as e:
                logger.debug(f"Error checking intersection for {county_name}: {e}")
        
        return intersecting
        
    except Exception as e:
        logger.warning(f"Shapely intersection failed: {e}")
        return []


def intersect_counties_with_point_check(
    polygon_rings: List[List],
    counties: List[Dict[str, Any]]
) -> List[str]:
    """
    Fallback: Check if county centroids fall within polygon.
    
    Args:
        polygon_rings: List of polygon rings
        counties: List of county dictionaries with lat/lon
        
    Returns:
        List of county names whose centroids are in the polygon
    """
    intersecting = []
    
    for county in counties:
        lat = county.get("lat")
        lon = county.get("lon")
        name = county.get("name")
        
        if lat is None or lon is None or not name:
            continue
        
        # Use point-in-polygon check with centroid
        if point_in_polygon((lon, lat), polygon_rings):
            intersecting.append(name)
    
    return intersecting


def get_counties_in_outlook(
    outlook_polygons: List[Dict[str, Any]],
    counties_geojson: Optional[Dict[str, Any]],
    counties_config: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Determine which counties are affected by outlook polygons.
    
    Args:
        outlook_polygons: List of polygon data with risk levels
        counties_geojson: County boundary GeoJSON (optional)
        counties_config: County config with centroids
        
    Returns:
        Dictionary mapping county names to their risk levels
    """
    county_risks = {}
    
    for polygon_data in outlook_polygons:
        rings = polygon_data.get("rings", [])
        risk = polygon_data.get("risk") or polygon_data.get("category")
        
        if not rings or not risk:
            continue
        
        # Try Shapely intersection first
        if SHAPELY_AVAILABLE and counties_geojson:
            counties_hit = intersect_counties_with_polygon_shapely(rings, counties_geojson)
        else:
            # Fallback to centroid check
            counties_hit = intersect_counties_with_point_check(rings, counties_config)
        
        # Update county risks (keep highest risk)
        for county in counties_hit:
            current = county_risks.get(county)
            if current is None or should_upgrade_risk(current, risk):
                county_risks[county] = risk
    
    return county_risks


def should_upgrade_risk(current: Any, new: Any) -> bool:
    """
    Determine if new risk level is higher than current.
    
    Works with both SPCRisk and EROCategory enums.
    """
    from .models import SPCRisk, EROCategory
    
    # Define priority for SPC
    spc_priority = {
        SPCRisk.NONE: 0, SPCRisk.TSTM: 1, SPCRisk.MRGL: 2,
        SPCRisk.SLGT: 3, SPCRisk.ENH: 4, SPCRisk.MDT: 5, SPCRisk.HIGH: 6,
    }
    
    # Define priority for ERO
    ero_priority = {
        EROCategory.NONE: 0, EROCategory.MRGL: 1,
        EROCategory.SLGT: 2, EROCategory.MDT: 3, EROCategory.HIGH: 4,
    }
    
    # Get priority values
    current_pri = spc_priority.get(current, ero_priority.get(current, 0))
    new_pri = spc_priority.get(new, ero_priority.get(new, 0))
    
    return new_pri > current_pri


def get_counties_by_region(
    counties: List[Dict[str, Any]]
) -> Dict[str, List[str]]:
    """
    Group counties by region.
    
    Args:
        counties: List of county dictionaries
        
    Returns:
        Dictionary mapping region names to list of county names
    """
    by_region: Dict[str, List[str]] = {}
    
    for county in counties:
        region = county.get("region", "Unknown")
        name = county.get("name")
        
        if not name:
            continue
            
        if region not in by_region:
            by_region[region] = []
        by_region[region].append(name)
    
    return by_region


def get_highest_risk_by_region(
    county_risks: Dict[str, Any],
    counties: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Get the highest risk level for each region.
    
    Args:
        county_risks: Dictionary mapping county names to risk levels
        counties: List of county dictionaries
        
    Returns:
        Dictionary mapping region names to highest risk level
    """
    from .models import SPCRisk, EROCategory
    
    region_risks: Dict[str, Any] = {}
    
    # Build county-to-region mapping
    county_to_region = {c["name"]: c["region"] for c in counties if c.get("name")}
    
    for county, risk in county_risks.items():
        region = county_to_region.get(county, "Unknown")
        current = region_risks.get(region)
        
        if current is None or should_upgrade_risk(current, risk):
            region_risks[region] = risk
    
    return region_risks
