"""Raydium LaunchLab bonding-curve trades and info, for any launchpad on it.

A coin's pool is keyed by its base and quote mints. The SOL pool is derived
first; a coin priced in anything else is found by searching LaunchLab's pools
for its mint. Amounts are in the pool's quote asset.
"""

from pathlib import Path

from solana.rpc.models import MemcmpOpts
from solders.pubkey import Pubkey
from spl.token.instructions import create_idempotent_associated_token_account

from pumpfun_cli.core.amounts import (
    amount_fields,
    confirmed_token_delta,
    received_fields,
    to_raw,
)
from pumpfun_cli.core.trade import DEFAULT_PRIORITY_FEE, _handle_tx_error
from pumpfun_cli.core.validate import invalid_pubkey_error, parse_pubkey
from pumpfun_cli.crypto import decrypt_keypair
from pumpfun_cli.protocol.address import find_ata
from pumpfun_cli.protocol.client import RpcClient, TransactionFailedError
from pumpfun_cli.protocol.contracts import (
    ATA_RENT_LAMPORTS,
    LAMPORTS_PER_SOL,
    SOL_RENT_EXEMPT_MIN,
    WSOL_MINT,
)
from pumpfun_cli.protocol.instructions import quote_settlement_account
from pumpfun_cli.protocol.launchlab import (
    CONSTANT_PRODUCT_CURVE,
    FEE_RATE_DENOMINATOR,
    LAUNCHLAB_PROGRAM,
    LAUNCHLAB_SLIPPAGE_ERROR_CODES,
    MIGRATE_TO_CPMM,
    POOL_BASE_MINT_OFFSET,
    POOL_STATE_SIZE,
    STATUS_TRADING,
    build_launchlab_swap_instruction,
    buy_amount_out,
    curve_type,
    derive_launchlab_pool,
    mint_transfer_fee,
    parse_fee_rate,
    parse_pool_state,
    platform_name,
    sell_amount_out,
    spot_price,
    transfer_fee_bps,
)
from pumpfun_cli.protocol.quote import is_sol, quote_symbol

LAUNCHLAB_COMPUTE_UNITS = 150_000


async def find_launchlab_pool(client: RpcClient, mint: Pubkey) -> tuple[Pubkey, dict] | None:
    """The coin's LaunchLab pool and its decoded state, or None if it has none.

    Raises:
        RuntimeError: If the pool search fails, e.g. on an RPC that refuses
            getProgramAccounts
    """
    address = derive_launchlab_pool(mint, WSOL_MINT)
    resp = await client.get_account_info(address)
    if resp.value and resp.value.owner == LAUNCHLAB_PROGRAM:
        return address, parse_pool_state(bytes(resp.value.data))
    try:
        found = await client.get_program_accounts(
            LAUNCHLAB_PROGRAM,
            [POOL_STATE_SIZE, MemcmpOpts(offset=POOL_BASE_MINT_OFFSET, bytes=str(mint))],
        )
    except Exception as exc:  # noqa: BLE001 - any RPC refusal means the same
        raise RuntimeError(
            f"No SOL-priced LaunchLab pool for {mint}, and pools in other quote assets"
            f" could not be searched ({type(exc).__name__}): this RPC may not serve"
            " getProgramAccounts"
        ) from None
    for item in found:
        return item.pubkey, parse_pool_state(bytes(item.account.data))
    return None


async def _load_market(client: RpcClient, mint: Pubkey) -> dict | None:
    """The pool with everything a trade or quote needs, or None without a pool.

    Adds `address`, `fee_rate` (parts per million), `transfer_fee`
    ((bps, max) of the coin), `platform`, and both token programs.
    """
    found = await find_launchlab_pool(client, mint)
    if found is None:
        return None
    address, pool = found
    global_config, platform_config, base_mint, quote_mint = await client.get_multiple_accounts(
        [pool["global_config"], pool["platform_config"], mint, pool["quote_mint"]]
    )
    if None in (global_config, platform_config, base_mint, quote_mint):
        raise RuntimeError(f"LaunchLab pool {address}: config or mint accounts unreadable")
    if curve_type(bytes(global_config.data)) != CONSTANT_PRODUCT_CURVE:
        raise RuntimeError(f"LaunchLab pool {address} uses a curve type this CLI does not price")
    return {
        **pool,
        "address": address,
        "fee_rate": parse_fee_rate(bytes(global_config.data), bytes(platform_config.data)),
        "transfer_fee": mint_transfer_fee(bytes(base_mint.data)),
        "platform": platform_name(bytes(platform_config.data)),
        "base_token_program": base_mint.owner,
        "quote_token_program": quote_mint.owner,
    }


async def buy_shortfall(
    client: RpcClient,
    user: Pubkey,
    quote_mint: Pubkey,
    quote_token_program: Pubkey,
    quote_decimals: int,
    amount_raw: int,
    fee_lamports: int,
) -> dict | None:
    """What a buy spending `amount_raw` of the quote is short of, or None.

    SOL covers the fee, the coin's token account and, on a SOL pool, the spend
    plus the throwaway WSOL account until it closes. A non-SOL quote must
    already be in the wallet's account for it. Returns `message` plus the
    available and required amounts of whichever asset is short.
    """
    sol = is_sol(quote_mint)
    required = (
        (amount_raw if sol else 0) + fee_lamports + 2 * ATA_RENT_LAMPORTS + SOL_RENT_EXEMPT_MIN
    )
    balance = await client.get_balance(user)
    if balance < required:
        return {
            "message": f"Wallet has {balance / LAMPORTS_PER_SOL:.6f} SOL"
            f" but trade requires ~{required / LAMPORTS_PER_SOL:.6f} SOL",
            "available_sol": balance / LAMPORTS_PER_SOL,
            "required_sol": required / LAMPORTS_PER_SOL,
        }
    if sol:
        return None
    held = await client.get_token_account_balance(find_ata(user, quote_mint, quote_token_program))
    if held >= amount_raw:
        return None
    symbol = quote_symbol(quote_mint)
    return {
        "message": f"Wallet holds {held / 10**quote_decimals} {symbol}"
        f" but the buy spends {amount_raw / 10**quote_decimals} {symbol}",
        **amount_fields("available_quote", held, quote_decimals),
        **amount_fields("required_quote", amount_raw, quote_decimals),
    }


def _not_found(mint_str: str) -> dict:
    return {"error": "not_found", "message": f"No LaunchLab pool for {mint_str}"}


def _graduated(market: dict) -> dict:
    where = "Raydium CPMM" if market["migrate_type"] == MIGRATE_TO_CPMM else "Raydium AMM v4"
    return {
        "error": "graduated",
        "message": f"Token has graduated from its LaunchLab curve to {where}.",
        "migrate_type": "cpmm" if market["migrate_type"] == MIGRATE_TO_CPMM else "amm_v4",
    }


def _market_fields(market: dict) -> dict:
    return {
        "venue": "launchlab",
        "platform": market["platform"],
        "quote_mint": str(market["quote_mint"]),
        "quote_symbol": quote_symbol(market["quote_mint"]),
    }


async def buy_launchlab(
    rpc_url: str,
    keystore_path: str,
    password: str,
    mint_str: str,
    amount: float,
    slippage: int = 15,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Spend exactly `amount` of the pool's quote asset on a LaunchLab curve (buy_exact_in)."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url)
    try:
        market = await _load_market(client, mint)
        if market is None:
            return _not_found(mint_str)
        if market["status"] != STATUS_TRADING:
            return _graduated(market)

        quote_mint = market["quote_mint"]
        base_decimals, quote_decimals = market["base_decimals"], market["quote_decimals"]
        user = keypair.pubkey()

        amount_raw = to_raw(amount, quote_decimals)
        tokens_out = buy_amount_out(market, amount_raw, market["fee_rate"], market["transfer_fee"])
        min_tokens_out = max(1, tokens_out * (100 - slippage) // 100)

        eff_priority_fee = priority_fee if priority_fee is not None else DEFAULT_PRIORITY_FEE
        eff_compute_units = compute_units if compute_units is not None else LAUNCHLAB_COMPUTE_UNITS
        shortfall = await buy_shortfall(
            client,
            user,
            quote_mint,
            market["quote_token_program"],
            quote_decimals,
            amount_raw,
            eff_priority_fee * eff_compute_units // 1_000_000,
        )

        if dry_run:
            spot = spot_price(market)
            expected = tokens_out / 10**base_decimals
            effective_price = amount / expected if expected > 0 else 0
            result = {
                "dry_run": True,
                "action": "buy",
                "mint": mint_str,
                **_market_fields(market),
                **amount_fields("quote_in", amount_raw, quote_decimals),
                **amount_fields("expected_tokens", tokens_out, base_decimals),
                "effective_price": effective_price,
                "spot_price": spot,
                "price_impact_pct": round((effective_price - spot) / spot * 100, 4)
                if spot > 0
                else 0,
                **amount_fields("min_tokens_out", min_tokens_out, base_decimals),
                "slippage_pct": slippage,
            }
            if shortfall:
                result["balance_warning"] = shortfall["message"]
            return result

        if shortfall:
            return {
                **shortfall,
                "error": "insufficient_balance",
                "message": f"Insufficient balance. {shortfall['message']}.",
            }

        base_program = market["base_token_program"]
        quote_account, open_ixs, close_ixs = quote_settlement_account(
            user, quote_mint, market["quote_token_program"], funding=amount_raw
        )
        ixs = [
            create_idempotent_associated_token_account(user, user, mint, base_program),
            *open_ixs,
            build_launchlab_swap_instruction(
                buy=True,
                pool_address=market["address"],
                pool=market,
                user=user,
                user_base_token=find_ata(user, mint, base_program),
                user_quote_token=quote_account,
                base_token_program=base_program,
                quote_token_program=market["quote_token_program"],
                amount_in=amount_raw,
                minimum_amount_out=min_tokens_out,
            ),
            *close_ixs,
        ]
        try:
            sig = await client.send_tx(
                ixs,
                [keypair],
                confirm=confirm,
                priority_fee=eff_priority_fee,
                compute_units=eff_compute_units,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, LAUNCHLAB_SLIPPAGE_ERROR_CODES)
        received = await confirmed_token_delta(client, sig, user, mint) if confirm else None
        result = {
            "action": "buy",
            "mint": mint_str,
            **_market_fields(market),
            **amount_fields("quote_spent", amount_raw, quote_decimals),
            **received_fields("tokens_received", received, tokens_out, base_decimals),
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    except (RuntimeError, ValueError) as exc:
        return {"error": "launchlab_error", "message": str(exc)}
    finally:
        await client.close()


async def sell_launchlab(
    rpc_url: str,
    keystore_path: str,
    password: str,
    mint_str: str,
    amount_str: str,
    slippage: int = 15,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Sell tokens into a LaunchLab curve (sell_exact_in), paid in its quote asset."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url)
    try:
        market = await _load_market(client, mint)
        if market is None:
            return _not_found(mint_str)
        if market["status"] != STATUS_TRADING:
            return _graduated(market)

        quote_mint = market["quote_mint"]
        base_decimals, quote_decimals = market["base_decimals"], market["quote_decimals"]
        base_program = market["base_token_program"]
        user = keypair.pubkey()
        user_ata = find_ata(user, mint, base_program)

        held = await client.get_token_account_balance(user_ata)
        if amount_str.lower() == "all":
            token_amount = held
        else:
            token_amount = to_raw(amount_str, base_decimals)
            if held < token_amount:
                return {
                    "error": "insufficient_balance",
                    "message": (
                        f"Insufficient token balance. Have {held / 10**base_decimals:.6f}"
                        f" tokens, need {token_amount / 10**base_decimals:.6f} tokens."
                    ),
                    "available_tokens": held / 10**base_decimals,
                    "required_tokens": token_amount / 10**base_decimals,
                }
        if token_amount <= 0:
            return {"error": "no_tokens", "message": "No tokens to sell."}

        quote_out = sell_amount_out(
            market, token_amount, market["fee_rate"], market["transfer_fee"]
        )
        if quote_out <= 0:
            # The program refuses a sell that pays nothing.
            return {
                "error": "dust",
                "message": "Too few tokens: the curve would pay nothing for them.",
            }
        min_quote_out = max(1, quote_out * (100 - slippage) // 100)

        if dry_run:
            spot = spot_price(market)
            tokens_human = token_amount / 10**base_decimals
            effective_price = quote_out / 10**quote_decimals / tokens_human
            return {
                "dry_run": True,
                "action": "sell",
                "mint": mint_str,
                **_market_fields(market),
                **amount_fields("tokens_in", token_amount, base_decimals),
                **amount_fields("expected_quote", quote_out, quote_decimals),
                "effective_price": effective_price,
                "spot_price": spot,
                "price_impact_pct": round((effective_price - spot) / spot * 100, 4)
                if spot > 0
                else 0,
                **amount_fields("min_quote_out", min_quote_out, quote_decimals),
                "slippage_pct": slippage,
            }

        quote_account, open_ixs, close_ixs = quote_settlement_account(
            user, quote_mint, market["quote_token_program"]
        )
        ixs = [
            *open_ixs,
            build_launchlab_swap_instruction(
                buy=False,
                pool_address=market["address"],
                pool=market,
                user=user,
                user_base_token=user_ata,
                user_quote_token=quote_account,
                base_token_program=base_program,
                quote_token_program=market["quote_token_program"],
                amount_in=token_amount,
                minimum_amount_out=min_quote_out,
            ),
            *close_ixs,
        ]
        try:
            sig = await client.send_tx(
                ixs,
                [keypair],
                confirm=confirm,
                priority_fee=priority_fee if priority_fee is not None else DEFAULT_PRIORITY_FEE,
                compute_units=compute_units
                if compute_units is not None
                else LAUNCHLAB_COMPUTE_UNITS,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, LAUNCHLAB_SLIPPAGE_ERROR_CODES)
        result = {
            "action": "sell",
            "mint": mint_str,
            **_market_fields(market),
            **amount_fields("tokens_sold", token_amount, base_decimals),
            "quote_received": quote_out / 10**quote_decimals,
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    except (RuntimeError, ValueError) as exc:
        return {"error": "launchlab_error", "message": str(exc)}
    finally:
        await client.close()


async def get_launchlab_info(rpc_url: str, mint_str: str, rpc_timeout: float = 30.0) -> dict:
    """On-chain info for a LaunchLab coin: price, progress, reserves, fees."""
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url, timeout=rpc_timeout)
    try:
        market = await _load_market(client, mint)
        if market is None:
            return _not_found(mint_str)
        quote_decimals = market["quote_decimals"]
        progress = (
            market["real_base"] / market["total_base_sell"] if market["total_base_sell"] else 0.0
        )
        graduated = market["status"] != STATUS_TRADING
        result = {
            "mint": mint_str,
            **_market_fields(market),
            "platform_config": str(market["platform_config"]),
            "launchlab_pool": str(market["address"]),
            "price": spot_price(market),
            "bonding_progress": round(min(progress, 1.0) * 100, 1),
            "graduated": graduated,
            "real_quote_reserves": market["real_quote"] / 10**quote_decimals,
            "creator": str(market["creator"]),
            "curve_fee_pct": market["fee_rate"] * 100 / FEE_RATE_DENOMINATOR,
            "transfer_fee_bps": transfer_fee_bps(market["transfer_fee"]),
        }
        if graduated:
            result["migrate_type"] = _graduated(market)["migrate_type"]
        return result
    except (RuntimeError, ValueError) as exc:
        return {"error": "launchlab_error", "message": str(exc)}
    finally:
        await client.close()
