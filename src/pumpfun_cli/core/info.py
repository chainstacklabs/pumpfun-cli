"""Fetch on-chain token info."""

from pathlib import Path

from pumpfun_cli.core.pumpswap import get_pumpswap_info
from pumpfun_cli.core.validate import invalid_pubkey_error, parse_pubkey
from pumpfun_cli.protocol.address import derive_bonding_curve
from pumpfun_cli.protocol.client import RpcClient
from pumpfun_cli.protocol.contracts import LAMPORTS_PER_SOL
from pumpfun_cli.protocol.curve import (
    get_bonding_progress,
    get_token_price_sol,
    is_graduated,
)
from pumpfun_cli.protocol.idl_parser import IDLParser

IDL_PATH = Path(__file__).parent.parent.parent.parent / "idl" / "pump_fun_idl.json"


async def get_token_info(rpc_url: str, mint_str: str, rpc_timeout: float = 30.0) -> dict:
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    bonding_curve = derive_bonding_curve(mint)
    client = RpcClient(rpc_url, timeout=rpc_timeout)
    idl = IDLParser(str(IDL_PATH))
    try:
        resp = await client.get_account_info(bonding_curve)
        if not resp.value:
            return {"error": "not_found", "message": f"No bonding curve found for {mint_str}"}
        state = idl.decode_account_data(resp.value.data, "BondingCurve", skip_discriminator=True)
        price = get_token_price_sol(state)
        progress = get_bonding_progress(state)
        graduated = is_graduated(state)

        result = {
            "mint": mint_str,
            "bonding_curve": str(bonding_curve),
            "price_sol": price,
            "bonding_progress": round(progress * 100, 1),
            "graduated": graduated,
            "real_sol_reserves": state["real_sol_reserves"] / LAMPORTS_PER_SOL,
            "virtual_sol_reserves": state["virtual_sol_reserves"] / LAMPORTS_PER_SOL,
            "virtual_token_reserves": state["virtual_token_reserves"],
            "creator": str(state.get("creator", "")),
            "is_mayhem_mode": state.get("is_mayhem_mode", False),
            "is_cashback_coin": state.get("is_cashback_coin", False),
        }

        if graduated:
            amm_info = await get_pumpswap_info(rpc_url, mint_str, rpc_timeout=rpc_timeout)
            if not amm_info.get("error"):
                result["price_sol"] = amm_info["price_sol"]
                result["pool_address"] = amm_info["pool_address"]
                result["base_reserves"] = amm_info["base_reserves"]
                result["quote_reserves_sol"] = amm_info["quote_reserves_sol"]
            else:
                result["pumpswap_warning"] = f"PumpSwap pool lookup failed: {amm_info['message']}"
                result["pumpswap_error"] = amm_info["error"]

        return result
    finally:
        await client.close()
