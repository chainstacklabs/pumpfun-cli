"""Fetch on-chain token info."""

from pumpfun_cli.core.pumpswap import get_pumpswap_info
from pumpfun_cli.core.validate import invalid_pubkey_error, parse_pubkey
from pumpfun_cli.protocol.address import derive_bonding_curve
from pumpfun_cli.protocol.client import RpcClient
from pumpfun_cli.protocol.curve import (
    get_bonding_progress,
    get_token_price,
    is_graduated,
    parse_bonding_curve,
)
from pumpfun_cli.protocol.quote import fetch_global, get_mint_info, quote_symbol


async def get_token_info(rpc_url: str, mint_str: str, rpc_timeout: float = 30.0) -> dict:
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    bonding_curve = derive_bonding_curve(mint)
    client = RpcClient(rpc_url, timeout=rpc_timeout)
    try:
        resp = await client.get_account_info(bonding_curve)
        if not resp.value:
            return {"error": "not_found", "message": f"No bonding curve found for {mint_str}"}
        state = parse_bonding_curve(bytes(resp.value.data))
        quote_mint = state["quote_mint"]
        _, quote_decimals = await get_mint_info(client, quote_mint)
        global_state = await fetch_global(client)
        graduated = is_graduated(state)
        progress = get_bonding_progress(state, global_state["initial_real_token_reserves"])

        result = {
            "mint": mint_str,
            "bonding_curve": str(bonding_curve),
            "quote_mint": str(quote_mint),
            "quote_symbol": quote_symbol(quote_mint),
            "price": get_token_price(state, quote_decimals),
            "bonding_progress": round(progress * 100, 1),
            "graduated": graduated,
            "real_quote_reserves": state["real_quote_reserves"] / 10**quote_decimals,
            "virtual_quote_reserves": state["virtual_quote_reserves"] / 10**quote_decimals,
            "virtual_token_reserves": state["virtual_token_reserves"],
            "creator": str(state["creator"]) if state["creator"] else None,
            "is_mayhem_mode": state["is_mayhem_mode"],
            "is_cashback_coin": state["is_cashback_coin"],
            "is_holder_reward": bool(state["is_holder_reward"]),
            "creator_fee_bps": state["creator_fee_bps"] or 0,
        }

        if graduated:
            amm_info = await get_pumpswap_info(rpc_url, mint_str, rpc_timeout=rpc_timeout)
            if not amm_info.get("error"):
                result["price"] = amm_info["price"]
                result["pool_address"] = amm_info["pool_address"]
                result["base_reserves"] = amm_info["base_reserves"]
                result["quote_reserves"] = amm_info["quote_reserves"]
            else:
                result["pumpswap_warning"] = f"PumpSwap pool lookup failed: {amm_info['message']}"
                result["pumpswap_error"] = amm_info["error"]

        return result
    finally:
        await client.close()
