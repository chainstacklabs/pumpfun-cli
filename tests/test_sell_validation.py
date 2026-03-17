"""Tests for sell amount validation."""

import pytest
from pumpfun_cli.core.validate import validate_sell_amount


class TestValidateSellAmount:
    """Tests for validate_sell_amount function."""
    
    def test_valid_amounts(self):
        """Test valid positive amounts."""
        assert validate_sell_amount(1.0) is None
        assert validate_sell_amount(100.0) is None
        assert validate_sell_amount(1000.0) is None
        assert validate_sell_amount(0.01) is None
    
    def test_none_amount(self):
        """Test None amount."""
        result = validate_sell_amount(None)
        assert result is not None
        assert result["error"] == "invalid_amount"
        assert "cannot be None" in result["message"]
    
    def test_zero_amount(self):
        """Test zero amount."""
        result = validate_sell_amount(0)
        assert result is not None
        assert result["error"] == "invalid_amount"
        assert "must be positive" in result["message"]
    
    def test_negative_amounts(self):
        """Test negative amounts."""
        result = validate_sell_amount(-1.0)
        assert result is not None
        assert result["error"] == "invalid_amount"
        assert "must be positive" in result["message"]
        
        result = validate_sell_amount(-0.5)
        assert result is not None
    
    def test_very_small_amount(self):
        """Test very small but valid amounts."""
        assert validate_sell_amount(0.001) is None
        assert validate_sell_amount(0.0001) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
