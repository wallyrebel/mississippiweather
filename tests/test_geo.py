"""
Tests for geospatial utilities.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.geo import point_in_polygon, get_counties_by_region


class TestPointInPolygon:
    """Tests for point-in-polygon algorithm."""
    
    def test_point_inside_simple_square(self):
        """Test point inside a simple square polygon."""
        # Square from (0,0) to (10,10)
        square = [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]
        
        # Point at center
        assert point_in_polygon((5, 5), square) == True
        
        # Point in corner area
        assert point_in_polygon((1, 1), square) == True
        assert point_in_polygon((9, 9), square) == True
    
    def test_point_outside_simple_square(self):
        """Test point outside a simple square polygon."""
        square = [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]
        
        # Points outside
        assert point_in_polygon((15, 5), square) == False
        assert point_in_polygon((-5, 5), square) == False
        assert point_in_polygon((5, 15), square) == False
        assert point_in_polygon((5, -5), square) == False
    
    def test_point_in_triangle(self):
        """Test point in a triangular polygon."""
        # Triangle with vertices at (0,0), (10,0), (5,10)
        triangle = [[(0, 0), (10, 0), (5, 10), (0, 0)]]
        
        # Center of triangle
        assert point_in_polygon((5, 3), triangle) == True
        
        # Outside triangle
        assert point_in_polygon((1, 8), triangle) == False
        assert point_in_polygon((9, 8), triangle) == False
    
    def test_empty_polygon(self):
        """Test with empty polygon."""
        assert point_in_polygon((5, 5), []) == False
        assert point_in_polygon((5, 5), [[]]) == False
    
    def test_mississippi_bounds(self):
        """Test with approximate Mississippi bounding box."""
        # Simplified Mississippi polygon (very rough approximation)
        ms_polygon = [[
            (-91.6, 30.2),  # SW corner
            (-88.1, 30.2),  # SE corner
            (-88.1, 35.0),  # NE corner
            (-91.6, 35.0),  # NW corner
            (-91.6, 30.2),  # Close polygon
        ]]
        
        # Jackson, MS (approximately)
        assert point_in_polygon((-90.18, 32.30), ms_polygon) == True
        
        # Point in Alabama
        assert point_in_polygon((-86.5, 33.0), ms_polygon) == False
        
        # Point in Louisiana
        assert point_in_polygon((-92.5, 31.0), ms_polygon) == False


class TestGetCountiesByRegion:
    """Tests for county-region grouping."""
    
    def test_empty_counties(self):
        """Test with empty county list."""
        result = get_counties_by_region([])
        assert result == {}
    
    def test_single_county(self):
        """Test with a single county."""
        counties = [
            {"name": "Hinds", "region": "Central"}
        ]
        
        result = get_counties_by_region(counties)
        
        assert len(result) == 1
        assert "Central" in result
        assert result["Central"] == ["Hinds"]
    
    def test_multiple_regions(self):
        """Test with counties in multiple regions."""
        counties = [
            {"name": "Hinds", "region": "Central"},
            {"name": "DeSoto", "region": "Northwest"},
            {"name": "Rankin", "region": "Central"},
            {"name": "Harrison", "region": "Gulf Coast West"},
        ]
        
        result = get_counties_by_region(counties)
        
        assert len(result) == 3
        assert result["Central"] == ["Hinds", "Rankin"]
        assert result["Northwest"] == ["DeSoto"]
        assert result["Gulf Coast West"] == ["Harrison"]
    
    def test_missing_name(self):
        """Test that counties without names are skipped."""
        counties = [
            {"name": "Hinds", "region": "Central"},
            {"region": "Northwest"},  # Missing name
            {"name": "", "region": "Delta"},  # Empty name
        ]
        
        result = get_counties_by_region(counties)
        
        assert len(result) == 1
        assert "Central" in result
    
    def test_missing_region(self):
        """Test that counties without region are group under 'Unknown'."""
        counties = [
            {"name": "TestCounty"}  # No region
        ]
        
        result = get_counties_by_region(counties)
        
        assert "Unknown" in result
        assert result["Unknown"] == ["TestCounty"]
