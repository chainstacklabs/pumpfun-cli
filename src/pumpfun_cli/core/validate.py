"""Shared pubkey and amount validation helpers."""

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


def validate_buy_amount(sol_amount: float) -> dict | None:
    """
    Validate buy amount is positive.
    
    Returns error dict if invalid, None if valid.
    """
    if sol_amount is None:
        return {
            "error": "invalid_amount",
            "message": "Buy amount cannot be None",
            "hint": "Provide a positive SOL amount (e.g., 0.1)"
        }
    
    if sol_amount <= 0:
        return {
            "error": "invalid_amount",
            "message": f"Buy amount must be positive, got {sol_amount}",
            "hint": "Provide a positive SOL amount (e.g., 0.1, 1.0, 10.0)"
        }
    
    if sol_amount > 1000:  # Reasonable upper limit
        return {
            "error": "amount_too_large",
            "message": f"Buy amount {sol_amount} SOL seems too large",
            "hint": "Double-check the amount. Maximum recommended is 1000 SOL"
        }
    
    return None


def validate_sell_amount(token_amount: float) -> dict | None:
    """
    Validate sell amount is positive.
    
    Returns error dict if invalid, None if valid.
    """
    if token_amount is None:
        return {
            "error": "invalid_amount",
            "message": "Sell amount cannot be None",
            "hint": "Provide a positive token amount"
        }
    
    if token_amount <= 0:
        return {
            "error": "invalid_amount",
            "message": f"Sell amount must be positive, got {token_amount}",
            "hint": "Provide a positive token amount"
        }
    
    return None
