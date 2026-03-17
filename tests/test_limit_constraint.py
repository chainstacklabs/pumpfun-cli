"""Tests for limit constraint validation."""

import pytest


def validate_limit_constraint(limit: int | None) -> dict | None:
    """
    Validate limit constraint is >= 1.
    
    Returns error dict if invalid, None if valid.
    """
    if limit is None:
        return None  # None is valid (no constraint)
    
    if limit < 1:
        return {
            "error": "invalid_limit",
            "message": f"Limit must be >= 1, got {limit}",
            "hint": "Provide a positive integer (e.g., 1, 10, 100)"
        }
    
    return None


class TestLimitConstraint:
    """Tests for limit constraint validation."""
    
    def test_valid_limits(self):
        """Test valid limit values."""
        assert validate_limit_constraint(1) is None
        assert validate_limit_constraint(10) is None
        assert validate_limit_constraint(100) is None
        assert validate_limit_constraint(1000) is None
    
    def test_none_limit(self):
        """Test None limit (should be valid)."""
        assert validate_limit_constraint(None) is None
    
    def test_zero_limit(self):
        """Test zero limit."""
        result = validate_limit_constraint(0)
        assert result is not None
        assert result["error"] == "invalid_limit"
        assert "must be >= 1" in result["message"]
    
    def test_negative_limits(self):
        """Test negative limits."""
        result = validate_limit_constraint(-1)
        assert result is not None
        assert "must be >= 1" in result["message"]
        
        result = validate_limit_constraint(-100)
        assert result is not None
    
    def test_boundary_value(self):
        """Test boundary value (1)."""
        assert validate_limit_constraint(1) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
