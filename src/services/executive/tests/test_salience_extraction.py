"""Unit tests for salience extraction from SalienceResult proto.

Tests verify that _extract_salience() correctly reads from the SalienceResult
proto structure with 3 scalars + vector map (Issue #174).
"""

import pytest
from unittest.mock import MagicMock
from gladys_executive.server import ExecutiveServicer


class TestSalienceExtraction:
    """Test _extract_salience() with SalienceResult proto structure."""

    def test_extract_all_salience_fields(self):
        """Verify _extract_salience correctly reads all 8 values from SalienceResult proto."""
        # Create mock SalienceResult proto with all fields
        salience = MagicMock()
        salience.threat = 0.8
        salience.salience = 0.75
        salience.habituation = 0.1
        salience.vector = {
            "novelty": 0.9,
            "opportunity": 0.7,
            "goal_relevance": 0.6,
            "actionability": 0.8,
            "social": 0.3,
        }

        result = ExecutiveServicer._extract_salience(salience)

        # Assert all 3 scalars extracted correctly
        assert result["threat"] == 0.8
        assert result["salience"] == 0.75
        assert result["habituation"] == 0.1

        # Assert all 5 vector dimensions extracted correctly
        assert result["novelty"] == 0.9
        assert result["opportunity"] == 0.7
        assert result["goal_relevance"] == 0.6
        assert result["actionability"] == 0.8
        assert result["social"] == 0.3

    def test_extract_with_missing_dimensions(self):
        """Missing vector dimensions should default to 0.0."""
        salience = MagicMock()
        salience.threat = 0.5
        salience.salience = 0.6
        salience.habituation = 0.2
        # Only provide 2 of 5 dimensions (dict.get() already returns default for missing keys)
        salience.vector = {
            "novelty": 0.9,
            "social": 0.3,
        }

        result = ExecutiveServicer._extract_salience(salience)

        # Scalars present
        assert result["threat"] == 0.5
        assert result["salience"] == 0.6
        assert result["habituation"] == 0.2

        # Present dimensions
        assert result["novelty"] == 0.9
        assert result["social"] == 0.3

        # Missing dimensions should default to 0.0
        assert result["opportunity"] == 0.0
        assert result["goal_relevance"] == 0.0
        assert result["actionability"] == 0.0

    def test_extract_with_empty_proto(self):
        """Empty/None proto should return empty dict."""
        result = ExecutiveServicer._extract_salience(None)
        assert result == {}

    def test_extract_with_zero_values(self):
        """Zero values should be extracted (not treated as missing)."""
        salience = MagicMock()
        salience.threat = 0.0
        salience.salience = 0.0
        salience.habituation = 0.0
        salience.vector = {
            "novelty": 0.0,
            "opportunity": 0.0,
            "goal_relevance": 0.0,
            "actionability": 0.0,
            "social": 0.0,
        }

        result = ExecutiveServicer._extract_salience(salience)

        # All values should be 0.0, not missing
        assert result["threat"] == 0.0
        assert result["salience"] == 0.0
        assert result["habituation"] == 0.0
        assert result["novelty"] == 0.0
        assert result["opportunity"] == 0.0
        assert result["goal_relevance"] == 0.0
        assert result["actionability"] == 0.0
        assert result["social"] == 0.0

    def test_extract_with_boundary_values(self):
        """Test with min/max boundary values (0.0, 1.0)."""
        salience = MagicMock()
        salience.threat = 1.0
        salience.salience = 0.0
        salience.habituation = 1.0
        salience.vector = {
            "novelty": 1.0,
            "opportunity": 0.0,
            "goal_relevance": 1.0,
            "actionability": 0.0,
            "social": 1.0,
        }

        result = ExecutiveServicer._extract_salience(salience)

        assert result["threat"] == 1.0
        assert result["salience"] == 0.0
        assert result["habituation"] == 1.0
        assert result["novelty"] == 1.0
        assert result["opportunity"] == 0.0
        assert result["goal_relevance"] == 1.0
        assert result["actionability"] == 0.0
        assert result["social"] == 1.0
