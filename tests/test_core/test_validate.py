"""Tests for core/validate.py — pubkey validation helpers."""

from solders.pubkey import Pubkey


def test_parse_pubkey_valid():
    """Valid base58 address returns a Pubkey."""
    from pumpfun_cli.core.validate import parse_pubkey

    result = parse_pubkey("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    assert isinstance(result, Pubkey)
    assert str(result) == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def test_parse_pubkey_invalid_base58():
    """Non-base58 string returns None."""
    from pumpfun_cli.core.validate import parse_pubkey

    assert parse_pubkey("invalidmintaddress") is None


def test_parse_pubkey_empty_string():
    """Empty string returns None."""
    from pumpfun_cli.core.validate import parse_pubkey

    assert parse_pubkey("") is None


def test_parse_pubkey_wrong_length():
    """Too-short string returns None."""
    from pumpfun_cli.core.validate import parse_pubkey

    assert parse_pubkey("abc") is None


def test_parse_pubkey_unicode():
    """Unicode characters return None."""
    from pumpfun_cli.core.validate import parse_pubkey

    assert parse_pubkey("\u2603\u2764\u00e9") is None


def test_invalid_pubkey_error_format():
    """Error dict has correct keys and values."""
    from pumpfun_cli.core.validate import invalid_pubkey_error

    result = invalid_pubkey_error("badaddr", "mint address")
    assert result["error"] == "invalid_address"
    assert "badaddr" in result["message"]
    assert "mint address" in result["message"]
    assert "hint" in result
    assert "base58" in result["hint"].lower() or "Solana" in result["hint"]
