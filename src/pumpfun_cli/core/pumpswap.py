"""PumpSwap AMM buy/sell execution and info.

Trades go to the canonical pool a pump.fun curve graduated into, derived from
the mint and the curve's quote mint. Amounts are in that pool's quote asset.
"""

from pathlib import Path

from solders.pubkey import Pubkey

from pumpfun_cli.core.amounts import (
    amount_fields,
    confirmed_token_delta,
    received_fields,
    to_raw,
)
from pumpfun_cli.core.validate import invalid_pubkey_error, parse_pubkey
from pumpfun_cli.crypto import decrypt_keypair
from pumpfun_cli.protocol.address import (
    derive_amm_user_volume_accumulator,
    derive_bonding_curve,
    find_ata,
)
from pumpfun_cli.protocol.client import RpcClient, TransactionFailedError
from pumpfun_cli.protocol.contracts import (
    ATA_RENT_LAMPORTS,
    LAMPORTS_PER_SOL,
    PUMPSWAP_BUY_COMPUTE_UNITS,
    PUMPSWAP_PRIORITY_FEE,
    PUMPSWAP_SELL_COMPUTE_UNITS,
    PUMPSWAP_SLIPPAGE_ERROR_CODES,
    SOL_RENT_EXEMPT_MIN,
    WSOL_MINT,
)
from pumpfun_cli.protocol.curve import parse_bonding_curve
from pumpfun_cli.protocol.instructions import (
    build_init_amm_user_volume_accumulator,
    build_pumpswap_buy_exact_quote_in_instructions,
    build_pumpswap_sell_instructions,
)
from pumpfun_cli.protocol.pumpswap import (
    PoolNotFoundError,
    get_global_config,
    get_pool_balances,
    get_pool_by_mint,
    parse_pool_data,
    pick_fee_recipients,
    pool_price,
    resolve_pool_tokens,
)
from pumpfun_cli.protocol.quote import is_sol, quote_symbol

_BPS = 10_000
# Headroom wrapped on top of a SOL buy, in percent. The throwaway WSOL account
# is closed in the same transaction, so whatever is not spent comes straight back.
_WSOL_FUNDING_BUFFER_PCT = 10


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


async def _load_pool(client: RpcClient, mint: Pubkey) -> tuple[Pubkey, dict, dict]:
    """(pool address, parsed pool, token programs and decimals) for a graduated coin.

    The pool's quote mint is the curve's, so the curve is read first when it
    still exists; a coin with no curve is looked up against SOL.

    Raises:
        RuntimeError: If the pool does not exist
    """
    quote_mint = WSOL_MINT
    resp = await client.get_account_info(derive_bonding_curve(mint))
    if resp.value:
        quote_mint = parse_bonding_curve(bytes(resp.value.data))["quote_mint"]
    pool_address, pool_data = await get_pool_by_mint(client, mint, quote_mint)
    pool = parse_pool_data(pool_data)
    tokens = await resolve_pool_tokens(client, pool)
    return pool_address, pool, tokens


def _total_fee_bps(config: dict) -> int:
    return config["lp_fee_bps"] + config["protocol_fee_bps"] + config["coin_creator_fee_bps"]


async def buy_pumpswap(
    rpc_url: str,
    keystore_path: str,
    password: str,
    mint_str: str,
    amount: float,
    slippage: int = 15,
    rpc_timeout: float = 30.0,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Spend exactly `amount` of the pool's quote asset on PumpSwap (buy_exact_quote_in)."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url, timeout=rpc_timeout)
    try:
        pool_address, pool, tokens = await _load_pool(client, mint)
        config = await get_global_config(client)
        base_balance, quote_balance = await get_pool_balances(client, pool)
        if quote_balance <= 0 or base_balance <= 0:
            return {"error": "no_liquidity", "message": "Pool has no liquidity."}

        quote_mint = pool["quote_mint"]
        symbol = quote_symbol(quote_mint)
        base_decimals = tokens["base_decimals"]
        quote_decimals = tokens["quote_decimals"]
        user = keypair.pubkey()

        amount_raw = to_raw(amount, quote_decimals)
        effective_in = amount_raw * (_BPS - _total_fee_bps(config)) // _BPS
        estimated_tokens = base_balance * effective_in // (quote_balance + effective_in)
        min_base_amount_out = max(1, estimated_tokens * (100 - slippage) // 100)

        eff_priority_fee = priority_fee if priority_fee is not None else PUMPSWAP_PRIORITY_FEE
        eff_compute_units = (
            compute_units if compute_units is not None else PUMPSWAP_BUY_COMPUTE_UNITS
        )
        wsol_funding = (
            amount_raw * (100 + _WSOL_FUNDING_BUFFER_PCT) // 100 if is_sol(quote_mint) else 0
        )
        fee_lamports = eff_priority_fee * eff_compute_units // 1_000_000
        required_lamports = (
            wsol_funding + fee_lamports + 2 * ATA_RENT_LAMPORTS + SOL_RENT_EXEMPT_MIN
        )
        wallet_balance = await client.get_balance(user)
        shortfall = None
        if wallet_balance < required_lamports:
            shortfall = (
                f"Wallet has {wallet_balance / LAMPORTS_PER_SOL:.6f} SOL"
                f" but trade requires ~{required_lamports / LAMPORTS_PER_SOL:.6f} SOL"
            )
        elif not is_sol(quote_mint):
            held = await client.get_token_account_balance(
                find_ata(user, quote_mint, tokens["quote_token_program"])
            )
            if held < amount_raw:
                shortfall = (
                    f"Wallet holds {held / 10**quote_decimals} {symbol}"
                    f" but the buy spends {amount} {symbol}"
                )

        if dry_run:
            spot_price = pool_price(base_balance, quote_balance, base_decimals, quote_decimals)
            expected_tokens = estimated_tokens / 10**base_decimals
            effective_price = amount / expected_tokens if expected_tokens > 0 else 0
            price_impact = (
                (effective_price - spot_price) / spot_price * 100 if spot_price > 0 else 0
            )
            result = {
                "dry_run": True,
                "action": "buy",
                "venue": "pumpswap",
                "mint": mint_str,
                "quote_mint": str(quote_mint),
                "quote_symbol": symbol,
                **amount_fields("quote_in", amount_raw, quote_decimals),
                **amount_fields("expected_tokens", estimated_tokens, base_decimals),
                "effective_price": effective_price,
                "spot_price": spot_price,
                "price_impact_pct": round(price_impact, 4),
                **amount_fields("min_tokens_out", min_base_amount_out, base_decimals),
                "slippage_pct": slippage,
            }
            if shortfall:
                result["balance_warning"] = shortfall
            return result

        if shortfall:
            return {
                "error": "insufficient_balance",
                "message": f"Insufficient balance. {shortfall}.",
                "available_sol": wallet_balance / LAMPORTS_PER_SOL,
                "required_sol": required_lamports / LAMPORTS_PER_SOL,
            }

        fee_recipient, buyback_recipient = pick_fee_recipients(config, pool["is_mayhem_mode"])
        ixs = build_pumpswap_buy_exact_quote_in_instructions(
            user=user,
            pool_address=pool_address,
            pool=pool,
            tokens=tokens,
            fee_recipient=fee_recipient,
            buyback_recipient=buyback_recipient,
            spendable_quote_in=amount_raw,
            min_base_amount_out=min_base_amount_out,
            wsol_funding=wsol_funding,
        )

        user_vol = derive_amm_user_volume_accumulator(user)
        vol_resp = await client.get_account_info(user_vol)
        if not vol_resp.value:
            ixs.insert(0, build_init_amm_user_volume_accumulator(user))

        try:
            sig = await client.send_tx(
                ixs,
                [keypair],
                compute_units=eff_compute_units,
                priority_fee=eff_priority_fee,
                confirm=confirm,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, PUMPSWAP_SLIPPAGE_ERROR_CODES)
        received = await confirmed_token_delta(client, sig, user, mint) if confirm else None
        result = {
            "action": "buy",
            "venue": "pumpswap",
            "mint": mint_str,
            "quote_mint": str(quote_mint),
            "quote_symbol": symbol,
            **amount_fields("quote_spent", amount_raw, quote_decimals),
            **received_fields("tokens_received", received, estimated_tokens, base_decimals),
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    except PoolNotFoundError as exc:
        # Same error as before, marked so a caller can tell "no pool" apart.
        return {"error": "pumpswap_error", "message": str(exc), "pool_missing": True}
    except (RuntimeError, ValueError) as exc:
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
    """Sell tokens on PumpSwap for the pool's quote asset."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url, timeout=rpc_timeout)
    try:
        pool_address, pool, tokens = await _load_pool(client, mint)
        quote_mint = pool["quote_mint"]
        symbol = quote_symbol(quote_mint)
        base_decimals = tokens["base_decimals"]
        quote_decimals = tokens["quote_decimals"]
        user = keypair.pubkey()
        user_token_ata = find_ata(user, mint, tokens["base_token_program"])

        if amount_str.lower() == "all":
            token_amount = await client.get_token_account_balance(user_token_ata)
        else:
            token_amount = to_raw(amount_str, base_decimals)
            actual_balance = await client.get_token_account_balance(user_token_ata)
            if actual_balance < token_amount:
                return {
                    "error": "insufficient_balance",
                    "message": (
                        f"Insufficient token balance. Have"
                        f" {actual_balance / 10**base_decimals:.6f} tokens,"
                        f" need {token_amount / 10**base_decimals:.6f} tokens."
                    ),
                    "available_tokens": actual_balance / 10**base_decimals,
                    "required_tokens": token_amount / 10**base_decimals,
                }

        if token_amount <= 0:
            return {"error": "no_tokens", "message": "No tokens to sell."}

        config = await get_global_config(client)
        base_balance, quote_balance = await get_pool_balances(client, pool)
        if base_balance <= 0 or quote_balance <= 0:
            return {"error": "no_liquidity", "message": "Pool has no liquidity."}
        gross_out = token_amount * quote_balance // (base_balance + token_amount)
        expected_quote = gross_out * (_BPS - _total_fee_bps(config)) // _BPS
        min_quote_out = max(1, expected_quote * (100 - slippage) // 100)

        if dry_run:
            spot_price = pool_price(base_balance, quote_balance, base_decimals, quote_decimals)
            tokens_human = token_amount / 10**base_decimals
            quote_out_human = expected_quote / 10**quote_decimals
            effective_price = quote_out_human / tokens_human if tokens_human > 0 else 0
            price_impact = (
                (effective_price - spot_price) / spot_price * 100 if spot_price > 0 else 0
            )
            return {
                "dry_run": True,
                "action": "sell",
                "venue": "pumpswap",
                "mint": mint_str,
                "quote_mint": str(quote_mint),
                "quote_symbol": symbol,
                **amount_fields("tokens_in", token_amount, base_decimals),
                **amount_fields("expected_quote", expected_quote, quote_decimals),
                "effective_price": effective_price,
                "spot_price": spot_price,
                "price_impact_pct": round(price_impact, 4),
                **amount_fields("min_quote_out", min_quote_out, quote_decimals),
                "slippage_pct": slippage,
            }

        fee_recipient, buyback_recipient = pick_fee_recipients(config, pool["is_mayhem_mode"])
        ixs = build_pumpswap_sell_instructions(
            user=user,
            pool_address=pool_address,
            pool=pool,
            tokens=tokens,
            fee_recipient=fee_recipient,
            buyback_recipient=buyback_recipient,
            token_amount=token_amount,
            min_quote_out=min_quote_out,
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
            "quote_mint": str(quote_mint),
            "quote_symbol": symbol,
            **amount_fields("tokens_sold", token_amount, base_decimals),
            "quote_received": expected_quote / 10**quote_decimals,
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    except PoolNotFoundError as exc:
        # Same error as before, marked so a caller can tell "no pool" apart.
        return {"error": "pumpswap_error", "message": str(exc), "pool_missing": True}
    except (RuntimeError, ValueError) as exc:
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
        pool_address, pool, tokens = await _load_pool(client, mint)
        base_balance, quote_balance = await get_pool_balances(client, pool)
        base_decimals = tokens["base_decimals"]
        quote_decimals = tokens["quote_decimals"]
        return {
            "pool_address": str(pool_address),
            "quote_mint": str(pool["quote_mint"]),
            "quote_symbol": quote_symbol(pool["quote_mint"]),
            "price": pool_price(base_balance, quote_balance, base_decimals, quote_decimals),
            "base_reserves": base_balance / 10**base_decimals,
            "quote_reserves": quote_balance / 10**quote_decimals,
            "creator": str(pool["coin_creator"]),
            "mayhem_mode": pool["is_mayhem_mode"],
            "cashback": pool["is_cashback_coin"],
        }
    except PoolNotFoundError as exc:
        # Same error as before, marked so a caller can tell "no pool" apart.
        return {"error": "pumpswap_error", "message": str(exc), "pool_missing": True}
    except (RuntimeError, ValueError) as exc:
        return {"error": "pumpswap_error", "message": str(exc)}
    finally:
        await client.close()
