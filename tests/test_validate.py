"""Tests for amount validation."""

import pytest
from pumpfun_cli.core.validate import validate_buy_amount, validate_sell_amount


class TestValidateBuyAmount:
    """Tests for validate_buy_amount function."""
    
    def test_valid_amount(self):
        """Test valid positive amounts."""
        assert validate_buy_amount(0.1) is None
        assert validate_buy_amount(1.0) is None
        assert validate_buy_amount(10.0) is None
        assert validate_buy_amount(100.0) is None
    
    def test_none_amount(self):
        """Test None amount."""
        result = validate_buy_amount(None)
        assert result is not None
        assert result["error"] == "invalid_amount"
        assert "cannot be None" in result["message"]
    
    def test_zero_amount(self):
        """Test zero amount."""
        result = validate_buy_amount(0)
        assert result is not None
        assert result["error"] == "invalid_amount"
        assert "must be positive" in result["message"]
    
    def test_negative_amount(self):
        """Test negative amounts."""
        result = validate_buy_amount(-1.0)
        assert result is not None
        assert result["error"] == "invalid_amount"
        assert "must be positive" in result["message"]
        
        result = validate_buy_amount(-0.5)
        assert result is not None
        assert "must be positive" in result["message"]
    
    def test_too_large_amount(self):
        """Test excessively large amounts."""
        result = validate_buy_amount(1001.0)
        assert result is not None
        assert result["error"] == "amount_too_large"
        assert "too large" in result["message"]
        
        result = validate_buy_amount(10000.0)
        assert result is not None
        assert "too large" in result["message"]
    
    def test_boundary_values(self):
        """Test boundary values."""
        # Exactly at boundary (should be valid)
        assert validate_buy_amount(1000.0) is None
        
        # Just over boundary (should be invalid)
        result = validate_buy_amount(1000.01)
        assert result is not None
        assert "too large" in result["message"]


class TestValidateSellAmount:
    """Tests for validate_sell_amount function."""
    
    def test_valid_amount(self):
        """Test valid positive amounts."""
        assert validate_sell_amount(1.0) is None
        assert validate_sell_amount(100.0) is None
        assert validate_sell_amount(1000.0) is None
    
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
    
    def test_negative_amount(self):
        """Test negative amounts."""
        result = validate_sell_amount(-1.0)
        assert result is not None
        assert result["error"] == "invalid_amount"
        assert "must be positive" in result["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
