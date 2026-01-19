"""
Tests for SPC outlook parsing.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import SPCRisk, SPCOutlook
from src.fetch_spc import parse_spc_risk, get_max_risk_from_outlooks


class TestParseSPCRisk:
    """Tests for SPC risk label parsing."""
    
    def test_standard_labels(self):
        """Test standard SPC risk labels."""
        assert parse_spc_risk("TSTM") == SPCRisk.TSTM
        assert parse_spc_risk("MRGL") == SPCRisk.MRGL
        assert parse_spc_risk("SLGT") == SPCRisk.SLGT
        assert parse_spc_risk("ENH") == SPCRisk.ENH
        assert parse_spc_risk("MDT") == SPCRisk.MDT
        assert parse_spc_risk("HIGH") == SPCRisk.HIGH
    
    def test_full_labels(self):
        """Test full-word risk labels."""
        assert parse_spc_risk("Marginal") == SPCRisk.MRGL
        assert parse_spc_risk("Slight") == SPCRisk.SLGT
        assert parse_spc_risk("Enhanced") == SPCRisk.ENH
        assert parse_spc_risk("Moderate") == SPCRisk.MDT
    
    def test_case_insensitive(self):
        """Test that parsing is case-insensitive."""
        assert parse_spc_risk("mrgl") == SPCRisk.MRGL
        assert parse_spc_risk("SLGT") == SPCRisk.SLGT
        assert parse_spc_risk("Enh") == SPCRisk.ENH
    
    def test_empty_and_none(self):
        """Test empty and None inputs."""
        assert parse_spc_risk("") == SPCRisk.NONE
        assert parse_spc_risk(None) == SPCRisk.NONE
    
    def test_unknown_label(self):
        """Test unknown labels return NONE."""
        assert parse_spc_risk("UNKNOWN") == SPCRisk.NONE
        assert parse_spc_risk("foo") == SPCRisk.NONE
        assert parse_spc_risk("EXTREME") == SPCRisk.NONE


class TestGetMaxRiskFromOutlooks:
    """Tests for getting maximum risk from outlooks."""
    
    def test_empty_outlooks(self):
        """Test with no outlooks."""
        result = get_max_risk_from_outlooks([], day=1)
        assert result == SPCRisk.NONE
    
    def test_single_outlook_single_polygon(self):
        """Test with one outlook containing one polygon."""
        outlook = SPCOutlook(
            day=1,
            valid_time=None,
            issue_time=None,
            outlook_type="categorical",
            polygons=[{"risk": SPCRisk.SLGT}],
        )
        
        result = get_max_risk_from_outlooks([outlook], day=1)
        assert result == SPCRisk.SLGT
    
    def test_multiple_polygons_returns_highest(self):
        """Test that highest risk is returned from multiple polygons."""
        outlook = SPCOutlook(
            day=1,
            valid_time=None,
            issue_time=None,
            outlook_type="categorical",
            polygons=[
                {"risk": SPCRisk.MRGL},
                {"risk": SPCRisk.ENH},
                {"risk": SPCRisk.SLGT},
            ],
        )
        
        result = get_max_risk_from_outlooks([outlook], day=1)
        assert result == SPCRisk.ENH
    
    def test_filters_by_day(self):
        """Test that only matching day is considered."""
        outlooks = [
            SPCOutlook(
                day=1,
                valid_time=None,
                issue_time=None,
                outlook_type="categorical",
                polygons=[{"risk": SPCRisk.MRGL}],
            ),
            SPCOutlook(
                day=2,
                valid_time=None,
                issue_time=None,
                outlook_type="categorical",
                polygons=[{"risk": SPCRisk.ENH}],
            ),
        ]
        
        result_day1 = get_max_risk_from_outlooks(outlooks, day=1)
        result_day2 = get_max_risk_from_outlooks(outlooks, day=2)
        
        assert result_day1 == SPCRisk.MRGL
        assert result_day2 == SPCRisk.ENH
    
    def test_high_is_highest(self):
        """Test that HIGH is properly ranked highest."""
        outlook = SPCOutlook(
            day=1,
            valid_time=None,
            issue_time=None,
            outlook_type="categorical",
            polygons=[
                {"risk": SPCRisk.MDT},
                {"risk": SPCRisk.HIGH},
                {"risk": SPCRisk.ENH},
            ],
        )
        
        result = get_max_risk_from_outlooks([outlook], day=1)
        assert result == SPCRisk.HIGH
