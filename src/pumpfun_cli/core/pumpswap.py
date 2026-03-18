"""PumpSwap AMM buy/sell execution and info."""

from pathlib import Path

from spl.token.instructions import get_associated_token_address

from pumpfun_cli.core.validate import invalid_pubkey_error, parse_pubkey
from pumpfun_cli.crypto import decrypt_keypair
from pumpfun_cli.protocol.address import derive_amm_user_volume_accumulator
from pumpfun_cli.protocol.client import RpcClient, TransactionFailedError
from pumpfun_cli.protocol.contracts import (
    ATA_RENT_LAMPORTS,
    LAMPORTS_PER_SOL,
    POOL_MAYHEM_MODE_MIN_SIZE,
    POOL_MAYHEM_MODE_OFFSET,
    PUMPSWAP_BUY_COMPUTE_UNITS,
    PUMPSWAP_PRIORITY_FEE,
    PUMPSWAP_SELL_COMPUTE_UNITS,
    PUMPSWAP_SLIPPAGE_ERROR_CODES,
    SOL_RENT_EXEMPT_MIN,
    TOKEN_DECIMALS,
)
from pumpfun_cli.protocol.instructions import (
    build_init_amm_user_volume_accumulator,
    build_pumpswap_buy_exact_quote_in_instructions,
    build_pumpswap_sell_instructions,
)
from pumpfun_cli.protocol.pumpswap import (
    get_fee_recipients,
    get_pool_balances,
    get_pool_by_mint,
    get_token_program_id,
    parse_pool_data,
)


def _estimate_buy_required_lamports(
    sol_lamports: int,
    priority_fee: int,
    compute_units: int,
) -> int:
    """Estimate total lamports required for a PumpSwap buy transaction."""
    fee_lamports = priority_fee * compute_units // 1_000_000
    return sol_lamports + fee_lamports + ATA_RENT_LAMPORTS + SOL_RENT_EXEMPT_MIN


def _handle_tx_error(exc: TransactionFailedError, slippage_codes: set[int]) -> dict:
    """Convert a TransactionFailedError into a structured error dict."""
    if exc.error_code in slippage_codes:
        return {
            "error": "slippage",
            "message": "Transaction failed: slippage tolerance exceeded.",
            "error_code": exc.error_code,
        }
    return {
        "error": "tx_error",
        "message": f"Transaction failed on-chain: {exc.raw_error}",
        "error_code": exc.error_code,
    }


async def buy_pumpswap(
    rpc_url: str,
    keystore_path: str,
    password: str,
    mint_str: str,
    sol_amount: float,
    slippage: int = 15,
    rpc_timeout: float = 30.0,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Buy tokens via PumpSwap AMM."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url, timeout=rpc_timeout)
    try:
        pool_address, pool_data = await get_pool_by_mint(client, mint)
        pool = parse_pool_data(pool_data)

        token_program_id = await get_token_program_id(client, mint)
        fee_recipient, fee_recipient_ata = await get_fee_recipients(client, pool_data)
        base_balance, quote_balance = await get_pool_balances(client, pool)

        if quote_balance <= 0 or base_balance <= 0:
            return {"error": "no_liquidity", "message": "Pool has no liquidity."}

        sol_lamports = int(sol_amount * LAMPORTS_PER_SOL)
        # Use buy_exact_quote_in: specify exact SOL to spend, minimum tokens to receive.
        # This avoids u64 overflow in the program's buy path on high-liquidity pools.
        spendable_quote_in = sol_lamports
        # Estimate minimum tokens out using constant-product AMM formula with fee discount
        effective_sol = sol_lamports * 99 // 100  # ~1% fee estimate
        estimated_tokens = base_balance * effective_sol // (quote_balance + effective_sol)
        min_base_amount_out = estimated_tokens * (100 - slippage) // 100

        # Pre-trade SOL balance validation
        eff_priority_fee = priority_fee if priority_fee is not None else PUMPSWAP_PRIORITY_FEE
        eff_compute_units = (
            compute_units if compute_units is not None else PUMPSWAP_BUY_COMPUTE_UNITS
        )
        required_lamports = _estimate_buy_required_lamports(
            sol_lamports, eff_priority_fee, eff_compute_units
        )
        wallet_balance = await client.get_balance(keypair.pubkey())

        if dry_run:
            spot_price = quote_balance / base_balance if base_balance > 0 else 0
            expected_tokens_human = estimated_tokens / (10**TOKEN_DECIMALS)
            effective_price = (
                sol_amount / expected_tokens_human if expected_tokens_human > 0 else 0
            )
            spot_price_sol = spot_price * (10**TOKEN_DECIMALS) / LAMPORTS_PER_SOL
            price_impact = (
                (effective_price - spot_price_sol) / spot_price_sol * 100
                if spot_price_sol > 0
                else 0
            )
            result = {
                "dry_run": True,
                "action": "buy",
                "venue": "pumpswap",
                "mint": mint_str,
                "sol_in": sol_amount,
                "expected_tokens": expected_tokens_human,
                "effective_price_sol": effective_price,
                "spot_price_sol": spot_price_sol,
                "price_impact_pct": round(price_impact, 4),
                "min_tokens_out": min_base_amount_out / (10**TOKEN_DECIMALS),
                "slippage_pct": slippage,
            }
            if wallet_balance < required_lamports:
                result["balance_warning"] = (
                    f"Wallet has {wallet_balance / LAMPORTS_PER_SOL:.6f} SOL"
                    f" but trade requires ~{required_lamports / LAMPORTS_PER_SOL:.6f} SOL"
                )
            return result

        if wallet_balance < required_lamports:
            return {
                "error": "insufficient_balance",
                "message": (
                    f"Insufficient SOL balance. Have {wallet_balance / LAMPORTS_PER_SOL:.6f}"
                    f" SOL, need ~{required_lamports / LAMPORTS_PER_SOL:.6f} SOL."
                ),
                "available_sol": wallet_balance / LAMPORTS_PER_SOL,
                "required_sol": required_lamports / LAMPORTS_PER_SOL,
            }

        # Wrap enough SOL to cover the spend plus a small buffer
        wrap_lamports = int(sol_amount * 1.1 * LAMPORTS_PER_SOL)
        if wrap_lamports < spendable_quote_in:
            wrap_lamports = spendable_quote_in

        ixs = build_pumpswap_buy_exact_quote_in_instructions(
            user=keypair.pubkey(),
            pool_address=pool_address,
            pool=pool,
            token_program_id=token_program_id,
            fee_recipient=fee_recipient,
            fee_recipient_ata=fee_recipient_ata,
            spendable_quote_in=spendable_quote_in,
            min_base_amount_out=min_base_amount_out,
            sol_wrap_lamports=wrap_lamports,
        )

        # Init user volume accumulator if it doesn't exist
        user_vol = derive_amm_user_volume_accumulator(keypair.pubkey())
        vol_resp = await client.get_account_info(user_vol)
        if not vol_resp.value:
            ixs.insert(0, build_init_amm_user_volume_accumulator(keypair.pubkey()))

        try:
            sig = await client.send_tx(
                ixs,
                [keypair],
                compute_units=compute_units
                if compute_units is not None
                else PUMPSWAP_BUY_COMPUTE_UNITS,
                priority_fee=priority_fee if priority_fee is not None else PUMPSWAP_PRIORITY_FEE,
                confirm=confirm,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, PUMPSWAP_SLIPPAGE_ERROR_CODES)
        result = {
            "action": "buy",
            "venue": "pumpswap",
            "mint": mint_str,
            "sol_spent": sol_amount,
            "tokens_received": estimated_tokens / (10**TOKEN_DECIMALS),
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    except RuntimeError as exc:
        return {"error": "pumpswap_error", "message": str(exc)}
    finally:
        await client.close()


async def sell_pumpswap(
    rpc_url: str,
    keystore_path: str,
    password: str,
    mint_str: str,
    amount_str: str,
    slippage: int = 15,
    rpc_timeout: float = 30.0,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Sell tokens via PumpSwap AMM."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url, timeout=rpc_timeout)
    try:
        pool_address, pool_data = await get_pool_by_mint(client, mint)
        pool = parse_pool_data(pool_data)

        token_program_id = await get_token_program_id(client, mint)
        fee_recipient, fee_recipient_ata = await get_fee_recipients(client, pool_data)

        user_token_ata = get_associated_token_address(
            keypair.pubkey(),
            mint,
            token_program_id,
        )

        if amount_str.lower() == "all":
            token_amount = await client.get_token_account_balance(user_token_ata)
        else:
            token_amount = int(float(amount_str) * (10**TOKEN_DECIMALS))
            # Pre-trade token balance validation for specific amounts
            actual_balance = await client.get_token_account_balance(user_token_ata)
            if actual_balance < token_amount:
                return {
                    "error": "insufficient_balance",
                    "message": (
                        f"Insufficient token balance. Have"
                        f" {actual_balance / (10**TOKEN_DECIMALS):.6f} tokens,"
                        f" need {token_amount / (10**TOKEN_DECIMALS):.6f} tokens."
                    ),
                    "available_tokens": actual_balance / (10**TOKEN_DECIMALS),
                    "required_tokens": token_amount / (10**TOKEN_DECIMALS),
                }

        if token_amount <= 0:
            return {"error": "no_tokens", "message": "No tokens to sell."}

        base_balance, quote_balance = await get_pool_balances(client, pool)
        # Integer arithmetic: expected_sol_lamports = token_amount * quote_balance / base_balance
        expected_sol_lamports = token_amount * quote_balance // base_balance
        min_sol_lamports = expected_sol_lamports * (100 - slippage) // 100

        if dry_run:
            spot_price = quote_balance / base_balance if base_balance > 0 else 0
            tokens_human = token_amount / (10**TOKEN_DECIMALS)
            sol_out_human = expected_sol_lamports / LAMPORTS_PER_SOL
            effective_price = sol_out_human / tokens_human if tokens_human > 0 else 0
            spot_price_sol = spot_price * (10**TOKEN_DECIMALS) / LAMPORTS_PER_SOL
            price_impact = (
                (effective_price - spot_price_sol) / spot_price_sol * 100
                if spot_price_sol > 0
                else 0
            )
            return {
                "dry_run": True,
                "action": "sell",
                "venue": "pumpswap",
                "mint": mint_str,
                "tokens_in": tokens_human,
                "expected_sol": sol_out_human,
                "effective_price_sol": effective_price,
                "spot_price_sol": spot_price_sol,
                "price_impact_pct": round(price_impact, 4),
                "min_sol_out": min_sol_lamports / LAMPORTS_PER_SOL,
                "slippage_pct": slippage,
            }

        ixs = build_pumpswap_sell_instructions(
            user=keypair.pubkey(),
            pool_address=pool_address,
            pool=pool,
            token_program_id=token_program_id,
            fee_recipient=fee_recipient,
            fee_recipient_ata=fee_recipient_ata,
            token_amount=token_amount,
            min_sol_out=min_sol_lamports,
        )

        try:
            sig = await client.send_tx(
                ixs,
                [keypair],
                compute_units=compute_units
                if compute_units is not None
                else PUMPSWAP_SELL_COMPUTE_UNITS,
                priority_fee=priority_fee if priority_fee is not None else PUMPSWAP_PRIORITY_FEE,
                confirm=confirm,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, PUMPSWAP_SLIPPAGE_ERROR_CODES)
        result = {
            "action": "sell",
            "venue": "pumpswap",
            "mint": mint_str,
            "tokens_sold": token_amount / (10**TOKEN_DECIMALS),
            "sol_received": expected_sol_lamports / LAMPORTS_PER_SOL,
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    except RuntimeError as exc:
        return {"error": "pumpswap_error", "message": str(exc)}
    finally:
        await client.close()


async def get_pumpswap_info(rpc_url: str, mint_str: str, rpc_timeout: float = 30.0) -> dict:
    """Fetch PumpSwap pool info for a graduated token."""
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url, timeout=rpc_timeout)
    try:
        pool_address, pool_data = await get_pool_by_mint(client, mint)
        pool = parse_pool_data(pool_data)

        base_balance, quote_balance = await get_pool_balances(client, pool)
        price = quote_balance / base_balance if base_balance > 0 else 0.0

        is_mayhem = len(pool_data) >= POOL_MAYHEM_MODE_MIN_SIZE and bool(
            pool_data[POOL_MAYHEM_MODE_OFFSET]
        )

        return {
            "pool_address": str(pool_address),
            "price_sol": price,
            "base_reserves": base_balance / (10**TOKEN_DECIMALS),
            "quote_reserves_sol": quote_balance / LAMPORTS_PER_SOL,
            "creator": str(pool["coin_creator"]),
            "mayhem_mode": is_mayhem,
        }
    except RuntimeError as exc:
        return {"error": "pumpswap_error", "message": str(exc)}
    finally:
        await client.close()
