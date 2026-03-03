"""Shared pubkey validation helpers."""

from solders.pubkey import Pubkey


def parse_pubkey(value: str, label: str = "address") -> Pubkey | None:
    """Attempt to parse a base58 Solana address. Returns None on failure."""
    try:
        return Pubkey.from_string(value)
    except (ValueError, Exception):
        return None


def invalid_pubkey_error(value: str, label: str = "address") -> dict:
    """Return a standard error dict for an invalid pubkey."""
    return {
        "error": "invalid_address",
        "message": f"Invalid {label}: {value}",
        "hint": "Provide a valid base58 Solana address.",
    }
