"""
Tests for NWS API fetcher.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Alert, AlertSeverity, AlertCertainty
from src.fetch_nws import group_alerts_by_type, get_alert_counties


class TestGroupAlertsByType:
    """Tests for alert grouping functionality."""
    
    def test_empty_alerts(self):
        """Test grouping with no alerts."""
        result = group_alerts_by_type([])
        assert result == {}
    
    def test_single_alert(self):
        """Test grouping with a single alert."""
        alert = Alert(
            id="test-1",
            event="Tornado Warning",
            headline="Tornado Warning for Test County",
            description="A tornado warning has been issued.",
            instruction="Take shelter immediately.",
            severity=AlertSeverity.EXTREME,
            certainty=AlertCertainty.OBSERVED,
            onset=datetime.now(),
            expires=datetime.now(),
            affected_zones=["MSZ001"],
            affected_counties=["Test County"],
            sender="NWS Jackson",
            message_type="Alert",
        )
        
        result = group_alerts_by_type([alert])
        
        assert "Tornado Warning" in result
        assert len(result["Tornado Warning"]) == 1
        assert result["Tornado Warning"][0].id == "test-1"
    
    def test_multiple_alerts_same_type(self):
        """Test grouping multiple alerts of the same type."""
        alerts = [
            Alert(
                id=f"test-{i}",
                event="Flood Warning",
                headline=f"Flood Warning {i}",
                description="Flooding expected.",
                instruction="Avoid flooded areas.",
                severity=AlertSeverity.SEVERE,
                certainty=AlertCertainty.LIKELY,
                onset=None,
                expires=None,
                affected_zones=[f"MSZ00{i}"],
                affected_counties=[f"County {i}"],
                sender="NWS",
                message_type="Alert",
            )
            for i in range(3)
        ]
        
        result = group_alerts_by_type(alerts)
        
        assert len(result) == 1
        assert "Flood Warning" in result
        assert len(result["Flood Warning"]) == 3
    
    def test_multiple_alert_types(self):
        """Test grouping alerts of different types."""
        alerts = [
            Alert(
                id="tornado-1",
                event="Tornado Warning",
                headline="Tornado Warning",
                description="",
                instruction="",
                severity=AlertSeverity.EXTREME,
                certainty=AlertCertainty.OBSERVED,
                onset=None,
                expires=None,
                affected_zones=[],
                affected_counties=["County A"],
                sender="NWS",
                message_type="Alert",
            ),
            Alert(
                id="flood-1",
                event="Flood Warning",
                headline="Flood Warning",
                description="",
                instruction="",
                severity=AlertSeverity.SEVERE,
                certainty=AlertCertainty.LIKELY,
                onset=None,
                expires=None,
                affected_zones=[],
                affected_counties=["County B"],
                sender="NWS",
                message_type="Alert",
            ),
            Alert(
                id="tornado-2",
                event="Tornado Warning",
                headline="Tornado Warning 2",
                description="",
                instruction="",
                severity=AlertSeverity.EXTREME,
                certainty=AlertCertainty.OBSERVED,
                onset=None,
                expires=None,
                affected_zones=[],
                affected_counties=["County C"],
                sender="NWS",
                message_type="Alert",
            ),
        ]
        
        result = group_alerts_by_type(alerts)
        
        assert len(result) == 2
        assert len(result["Tornado Warning"]) == 2
        assert len(result["Flood Warning"]) == 1


class TestGetAlertCounties:
    """Tests for extracting counties from alerts."""
    
    def test_empty_alerts(self):
        """Test with no alerts."""
        result = get_alert_counties([])
        assert result == []
    
    def test_single_alert_single_county(self):
        """Test with one alert affecting one county."""
        alert = Alert(
            id="test",
            event="Test",
            headline="",
            description="",
            instruction="",
            severity=AlertSeverity.MINOR,
            certainty=AlertCertainty.POSSIBLE,
            onset=None,
            expires=None,
            affected_zones=[],
            affected_counties=["Hinds County"],
            sender="NWS",
            message_type="Alert",
        )
        
        result = get_alert_counties([alert])
        assert result == ["Hinds County"]
    
    def test_multiple_counties_deduplicated(self):
        """Test that duplicate counties are removed."""
        alerts = [
            Alert(
                id="test-1",
                event="Test",
                headline="",
                description="",
                instruction="",
                severity=AlertSeverity.MINOR,
                certainty=AlertCertainty.POSSIBLE,
                onset=None,
                expires=None,
                affected_zones=[],
                affected_counties=["Hinds County", "Rankin County"],
                sender="NWS",
                message_type="Alert",
            ),
            Alert(
                id="test-2",
                event="Test",
                headline="",
                description="",
                instruction="",
                severity=AlertSeverity.MINOR,
                certainty=AlertCertainty.POSSIBLE,
                onset=None,
                expires=None,
                affected_zones=[],
                affected_counties=["Hinds County", "Madison County"],
                sender="NWS",
                message_type="Alert",
            ),
        ]
        
        result = get_alert_counties(alerts)
        
        assert len(result) == 3
        assert "Hinds County" in result
        assert "Rankin County" in result
        assert "Madison County" in result
    
    def test_sorted_output(self):
        """Test that counties are sorted alphabetically."""
        alert = Alert(
            id="test",
            event="Test",
            headline="",
            description="",
            instruction="",
            severity=AlertSeverity.MINOR,
            certainty=AlertCertainty.POSSIBLE,
            onset=None,
            expires=None,
            affected_zones=[],
            affected_counties=["Yazoo", "Adams", "Lincoln"],
            sender="NWS",
            message_type="Alert",
        )
        
        result = get_alert_counties([alert])
        
        assert result == ["Adams", "Lincoln", "Yazoo"]
