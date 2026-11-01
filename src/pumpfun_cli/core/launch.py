"""Token launch — create_v2 with IPFS metadata upload."""

import os
from pathlib import Path

import httpx
from solders.keypair import Keypair
from spl.token.instructions import create_idempotent_associated_token_account

from pumpfun_cli.core.validate import parse_pubkey
from pumpfun_cli.crypto import decrypt_keypair
from pumpfun_cli.protocol.address import derive_bonding_curve, find_ata, find_holder_rewards
from pumpfun_cli.protocol.client import RpcClient, TransactionFailedError
from pumpfun_cli.protocol.contracts import (
    LAUNCH_COMPUTE_UNITS,
    TOKEN_2022_PROGRAM,
    TOKEN_DECIMALS,
    WSOL_MINT,
)
from pumpfun_cli.protocol.instructions import (
    build_buy_exact_quote_in_v2_instruction,
    build_create_v2_instruction,
    build_extend_account_instruction,
)
from pumpfun_cli.protocol.quote import (
    check_creator_fee,
    check_mayhem_quote,
    fetch_global,
    fetch_quote_control,
    get_mint_info,
    is_sol,
    normalize_quote_mint,
    opening_quote_reserves,
    quote_symbol,
)

_BPS = 10_000


async def upload_metadata(
    name: str,
    symbol: str,
    description: str,
    image_path: str | None = None,
) -> str:
    """Upload token metadata to pump.fun's IPFS endpoint. Returns metadata URI."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        files = {}
        data = {
            "name": name,
            "symbol": symbol,
            "description": description,
            "showName": "true",
        }
        if image_path and os.path.exists(image_path):
            files["file"] = (os.path.basename(image_path), open(image_path, "rb"), "image/png")
        resp = await client.post(
            "https://pump.fun/api/ipfs",
            data=data,
            files=files if files else None,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"IPFS upload failed (HTTP {resp.status_code}): {resp.text[:200]}")
        result = resp.json()
        return result.get("metadataUri") or result.get("metadata_uri") or result.get("uri", "")


def opening_buy_tokens(
    global_state: dict, amount_raw: int, opening_reserves: int, creator_fee_bps: int | None
) -> int:
    """Tokens an opening buy of `amount_raw` quote units receives, after fees.

    Priced against the reserves the curve opens with. At opening-buy sizes the
    curvature is below the slippage margin, so the estimate is linear.
    """
    creator_rate = (
        global_state.get("creator_fee_basis_points", 0)
        if creator_fee_bps is None
        else creator_fee_bps
    )
    fee_bps = global_state.get("fee_basis_points", 0) + creator_rate
    reaching_curve = amount_raw * (_BPS - fee_bps) // _BPS
    return reaching_curve * global_state["initial_virtual_token_reserves"] // opening_reserves


async def launch_token(
    rpc_url: str,
    keystore_path: str,
    password: str,
    name: str,
    ticker: str,
    description: str,
    image_path: str | None = None,
    initial_buy: float | None = None,
    is_mayhem: bool = False,
    quote_mint_str: str | None = None,
    creator_fee_bps: int | None = None,
    is_holder_reward: bool = False,
    slippage: int = 15,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    """Launch a new coin with create_v2, optionally buying it in the same transaction.

    With `initial_buy`, create and buy go out as one transaction (v1, since
    together they exceed v0), so nobody can buy in between.
    `initial_buy` is in the quote asset, which the wallet must already hold
    when it is not SOL.
    """
    wallet = decrypt_keypair(Path(keystore_path), password)
    user = wallet.pubkey()
    quote_mint = WSOL_MINT
    if quote_mint_str:
        parsed = parse_pubkey(quote_mint_str, "quote mint")
        if parsed is None:
            return {
                "error": "invalid_quote_mint",
                "message": f"Invalid quote mint: {quote_mint_str}",
            }
        quote_mint = normalize_quote_mint(parsed)

    client = RpcClient(rpc_url)
    try:
        # Refuse anything the program would reject or silently ignore before
        # uploading metadata or spending a fee.
        check_mayhem_quote(quote_mint, is_mayhem)
        global_state = await fetch_global(client)
        if is_holder_reward and not global_state.get("is_holder_reward_enabled", False):
            return {
                "error": "holder_reward_disabled",
                "message": "pump.fun is not accepting holder-reward coins right now.",
            }
        registry = {}
        if not is_sol(quote_mint) or creator_fee_bps:
            registry = await fetch_quote_control(client)
        check_creator_fee(global_state, registry, quote_mint, creator_fee_bps)
        opening_reserves = opening_quote_reserves(registry, quote_mint, global_state)
        quote_program, quote_decimals = await get_mint_info(client, quote_mint)
        symbol = quote_symbol(quote_mint)

        amount_raw = int((initial_buy or 0) * 10**quote_decimals)
        if amount_raw > 0 and not is_sol(quote_mint):
            held = await client.get_token_account_balance(
                find_ata(user, quote_mint, quote_program)
            )
            if held < amount_raw:
                return {
                    "error": "insufficient_balance",
                    "message": (
                        f"Wallet holds {held / 10**quote_decimals} {symbol}"
                        f" but the opening buy spends {initial_buy} {symbol}."
                    ),
                }

        uri = await upload_metadata(name, ticker, description, image_path)
        if not uri:
            return {"error": "ipfs_failed", "message": "Failed to get metadata URI from IPFS."}

        mint_keypair = Keypair()
        mint = mint_keypair.pubkey()
        bonding_curve = derive_bonding_curve(mint)

        instructions = [
            build_create_v2_instruction(
                mint=mint,
                user=user,
                creator=user,
                name=name,
                symbol=ticker,
                uri=uri,
                is_mayhem_mode=is_mayhem,
                creator_fee_bps=creator_fee_bps,
                is_holder_reward=True if is_holder_reward else None,
                quote_mint=quote_mint,
                quote_token_program=quote_program,
            ),
            build_extend_account_instruction(bonding_curve, user),
        ]

        expected_tokens = 0
        if amount_raw > 0:
            expected_tokens = opening_buy_tokens(
                global_state, amount_raw, opening_reserves, creator_fee_bps
            )
            # A holder-reward coin's curve carries a PDA instead of the creator,
            # and the buy's creator vault derives from what the curve carries.
            curve_creator = find_holder_rewards(mint) if is_holder_reward else user
            instructions += [
                create_idempotent_associated_token_account(user, user, mint, TOKEN_2022_PROGRAM),
                build_buy_exact_quote_in_v2_instruction(
                    mint=mint,
                    creator=curve_creator,
                    user=user,
                    spendable_quote_in=amount_raw,
                    min_tokens_out=max(1, expected_tokens * (100 - slippage) // 100),
                    quote_mint=quote_mint,
                    base_token_program=TOKEN_2022_PROGRAM,
                    quote_token_program=quote_program,
                    is_mayhem_mode=is_mayhem,
                ),
            ]

        eff_compute_units = compute_units if compute_units is not None else LAUNCH_COMPUTE_UNITS
        eff_priority_fee = priority_fee if priority_fee is not None else 500_000
        try:
            # Create and buy together exceed a v0 transaction, so send_tx goes v1
            # and the coin is bought by the transaction that creates it.
            sig = await client.send_tx(
                instructions,
                [wallet, mint_keypair],
                compute_units=eff_compute_units,
                priority_fee=eff_priority_fee,
                confirm=confirm,
            )
        except TransactionFailedError as exc:
            return {
                "error": "tx_error",
                "message": f"Transaction failed on-chain: {exc.raw_error}",
                "error_code": exc.error_code,
                "mint": str(mint),
            }
        result = {
            "action": "launch",
            "name": name,
            "ticker": ticker,
            "mint": str(mint),
            "metadata_uri": uri,
            "quote_mint": str(quote_mint),
            "quote_symbol": symbol,
            "is_mayhem_mode": is_mayhem,
            "is_holder_reward": is_holder_reward,
            "creator_fee_bps": creator_fee_bps or 0,
            "initial_buy": initial_buy,
            "expected_tokens": expected_tokens / 10**TOKEN_DECIMALS,
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
            "pump_url": f"https://pump.fun/coin/{mint}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    finally:
        await client.close()
