"""Raydium CPMM trades and info for LaunchLab coins that have graduated.

The pool is found from the coin's LaunchLab pool: its platform config names
the CPMM AMM config, and the pool is derived from that and the two mints.
Amounts are in the pool's quote asset, the one the curve was priced in.
"""

from pathlib import Path

from solders.pubkey import Pubkey
from spl.token.instructions import create_idempotent_associated_token_account

from pumpfun_cli.core.amounts import (
    amount_fields,
    confirmed_token_delta,
    received_fields,
    to_raw,
)
from pumpfun_cli.core.launchlab import buy_shortfall, find_launchlab_pool
from pumpfun_cli.core.trade import DEFAULT_PRIORITY_FEE, _handle_tx_error
from pumpfun_cli.core.validate import invalid_pubkey_error, parse_pubkey
from pumpfun_cli.crypto import decrypt_keypair
from pumpfun_cli.protocol.address import find_ata
from pumpfun_cli.protocol.client import (
    RpcClient,
    TransactionFailedError,
    TransactionUnconfirmedError,
)
from pumpfun_cli.protocol.cpmm import (
    CPMM_SLIPPAGE_ERROR_CODES,
    FEE_RATE_DENOMINATOR,
    build_cpmm_swap_instruction,
    cpmm_pool_address,
    parse_cpmm_fee_rate,
    parse_cpmm_pool,
    swap_amount_out,
)
from pumpfun_cli.protocol.instructions import quote_settlement_account
from pumpfun_cli.protocol.launchlab import (
    MIGRATE_TO_CPMM,
    PLATFORM_CPSWAP_CONFIG_OFFSET,
    STATUS_TRADING,
    mint_transfer_fee,
    platform_name,
    withheld_fee,
)
from pumpfun_cli.protocol.quote import quote_symbol

CPMM_COMPUTE_UNITS = 150_000
_TOKEN_AMOUNT_OFFSET = 64


class _NoPool(Exception):
    """The coin has no CPMM pool to trade in; carries the result to return."""

    def __init__(self, result: dict):
        super().__init__(result["message"])
        self.result = result


async def _load_pool(client: RpcClient, mint: Pubkey, mint_str: str) -> dict:
    """The coin's CPMM pool with its reserves, fee and transfer fee.

    Raises:
        _NoPool: If the coin isn't a LaunchLab coin migrated to CPMM
        RuntimeError: If an account can't be read
    """
    found = await find_launchlab_pool(client, mint)
    if found is None:
        raise _NoPool({"error": "not_found", "message": f"No LaunchLab coin {mint_str}"})
    _, launch = found
    if launch["status"] == STATUS_TRADING:
        raise _NoPool(
            {
                "error": "not_graduated",
                "message": "Token is still on its LaunchLab bonding curve.",
            }
        )
    if launch["migrate_type"] != MIGRATE_TO_CPMM:
        raise _NoPool(
            {
                "error": "unsupported_venue",
                "message": "Token graduated to Raydium AMM v4, which this CLI does not trade.",
            }
        )
    platform = await client.get_account_info(launch["platform_config"])
    if not platform.value:
        raise RuntimeError(f"LaunchLab platform config {launch['platform_config']} unreadable")
    platform_data = bytes(platform.value.data)
    offset = PLATFORM_CPSWAP_CONFIG_OFFSET
    amm_config = Pubkey.from_bytes(platform_data[offset : offset + 32])
    address = cpmm_pool_address(amm_config, mint, launch["quote_mint"])
    pool_account = await client.get_account_info(address)
    if not pool_account.value:
        raise _NoPool(
            {
                "error": "migrating",
                "message": "Token's curve is complete but its CPMM pool is not open yet.",
            }
        )
    pool = parse_cpmm_pool(bytes(pool_account.value.data), mint)
    config, base_vault, quote_vault, base_mint = await client.get_multiple_accounts(
        [pool["amm_config"], pool["base_vault"], pool["quote_vault"], mint]
    )
    if None in (config, base_vault, quote_vault, base_mint):
        raise RuntimeError(f"CPMM pool {address}: config, vault or mint unreadable")

    def vault_amount(account) -> int:
        return int.from_bytes(
            bytes(account.data)[_TOKEN_AMOUNT_OFFSET : _TOKEN_AMOUNT_OFFSET + 8], "little"
        )

    return {
        **pool,
        "address": address,
        "platform": platform_name(platform_data),
        "fee_rate": parse_cpmm_fee_rate(bytes(config.data), pool["creator_fee_enabled"]),
        "transfer_fee": mint_transfer_fee(bytes(base_mint.data)),
        # The vaults also hold fees owed to the protocol, fund and creator.
        "base_reserve": vault_amount(base_vault) - pool["base_fees"],
        "quote_reserve": vault_amount(quote_vault) - pool["quote_fees"],
    }


def _price(pool: dict) -> float:
    if pool["base_reserve"] <= 0:
        return 0.0
    return (pool["quote_reserve"] / 10 ** pool["quote_decimals"]) / (
        pool["base_reserve"] / 10 ** pool["base_decimals"]
    )


def _pool_fields(pool: dict) -> dict:
    return {
        "venue": "cpmm",
        "platform": pool["platform"],
        "quote_mint": str(pool["quote_mint"]),
        "quote_symbol": quote_symbol(pool["quote_mint"]),
    }


def _impact(effective: float, spot: float) -> float:
    return round((effective - spot) / spot * 100, 4) if spot > 0 else 0


async def buy_cpmm(
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
    """Spend exactly `amount` of the pool's quote asset on Raydium CPMM (swap_base_input)."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url)
    try:
        pool = await _load_pool(client, mint, mint_str)
        if pool["base_reserve"] <= 0 or pool["quote_reserve"] <= 0:
            return {"error": "no_liquidity", "message": "Pool has no liquidity."}
        quote_mint = pool["quote_mint"]
        base_decimals, quote_decimals = pool["base_decimals"], pool["quote_decimals"]
        user = keypair.pubkey()

        amount_raw = to_raw(amount, quote_decimals)
        gross = swap_amount_out(
            pool["quote_reserve"], pool["base_reserve"], amount_raw, pool["fee_rate"]
        )
        tokens_out = gross - withheld_fee(gross, pool["transfer_fee"])
        min_tokens_out = max(1, tokens_out * (100 - slippage) // 100)

        eff_priority_fee = priority_fee if priority_fee is not None else DEFAULT_PRIORITY_FEE
        eff_compute_units = compute_units if compute_units is not None else CPMM_COMPUTE_UNITS
        shortfall = await buy_shortfall(
            client,
            user,
            quote_mint,
            pool["quote_token_program"],
            quote_decimals,
            amount_raw,
            eff_priority_fee * eff_compute_units // 1_000_000,
        )

        if dry_run:
            spot = _price(pool)
            expected = tokens_out / 10**base_decimals
            effective = amount / expected if expected > 0 else 0
            result = {
                "dry_run": True,
                "action": "buy",
                "mint": mint_str,
                **_pool_fields(pool),
                **amount_fields("quote_in", amount_raw, quote_decimals),
                **amount_fields("expected_tokens", tokens_out, base_decimals),
                "effective_price": effective,
                "spot_price": spot,
                "price_impact_pct": _impact(effective, spot),
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

        base_program = pool["base_token_program"]
        quote_account, open_ixs, close_ixs = quote_settlement_account(
            user, quote_mint, pool["quote_token_program"], funding=amount_raw
        )
        ixs = [
            *open_ixs,
            create_idempotent_associated_token_account(user, user, mint, base_program),
            build_cpmm_swap_instruction(
                buy=True,
                pool_address=pool["address"],
                pool=pool,
                user=user,
                user_base_token=find_ata(user, mint, base_program),
                user_quote_token=quote_account,
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
            return _handle_tx_error(exc, CPMM_SLIPPAGE_ERROR_CODES)
        received = await confirmed_token_delta(client, sig, user, mint) if confirm else None
        result = {
            "action": "buy",
            "mint": mint_str,
            **_pool_fields(pool),
            **amount_fields("quote_spent", amount_raw, quote_decimals),
            **received_fields("tokens_received", received, tokens_out, base_decimals),
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    except _NoPool as exc:
        return exc.result
    except TransactionUnconfirmedError as exc:
        # Sent, so the message's signature must reach the user.
        return {"error": "unconfirmed", "message": str(exc)}
    except (RuntimeError, ValueError) as exc:
        return {"error": "cpmm_error", "message": str(exc)}
    finally:
        await client.close()


async def sell_cpmm(
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
    """Sell tokens on Raydium CPMM (swap_base_input) for the pool's quote asset."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url)
    try:
        pool = await _load_pool(client, mint, mint_str)
        quote_mint = pool["quote_mint"]
        base_decimals, quote_decimals = pool["base_decimals"], pool["quote_decimals"]
        base_program = pool["base_token_program"]
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
        if pool["base_reserve"] <= 0 or pool["quote_reserve"] <= 0:
            return {"error": "no_liquidity", "message": "Pool has no liquidity."}

        arrived = token_amount - withheld_fee(token_amount, pool["transfer_fee"])
        quote_out = swap_amount_out(
            pool["base_reserve"], pool["quote_reserve"], arrived, pool["fee_rate"]
        )
        if quote_out <= 0:
            return {
                "error": "dust",
                "message": "Too few tokens: the pool would pay nothing for them.",
            }
        min_quote_out = max(1, quote_out * (100 - slippage) // 100)

        if dry_run:
            spot = _price(pool)
            effective = quote_out / 10**quote_decimals / (token_amount / 10**base_decimals)
            return {
                "dry_run": True,
                "action": "sell",
                "mint": mint_str,
                **_pool_fields(pool),
                **amount_fields("tokens_in", token_amount, base_decimals),
                **amount_fields("expected_quote", quote_out, quote_decimals),
                "effective_price": effective,
                "spot_price": spot,
                "price_impact_pct": _impact(effective, spot),
                **amount_fields("min_quote_out", min_quote_out, quote_decimals),
                "slippage_pct": slippage,
            }

        quote_account, open_ixs, close_ixs = quote_settlement_account(
            user, quote_mint, pool["quote_token_program"]
        )
        ixs = [
            *open_ixs,
            build_cpmm_swap_instruction(
                buy=False,
                pool_address=pool["address"],
                pool=pool,
                user=user,
                user_base_token=user_ata,
                user_quote_token=quote_account,
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
                compute_units=compute_units if compute_units is not None else CPMM_COMPUTE_UNITS,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, CPMM_SLIPPAGE_ERROR_CODES)
        result = {
            "action": "sell",
            "mint": mint_str,
            **_pool_fields(pool),
            **amount_fields("tokens_sold", token_amount, base_decimals),
            "quote_received": quote_out / 10**quote_decimals,
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    except _NoPool as exc:
        return exc.result
    except TransactionUnconfirmedError as exc:
        # Sent, so the message's signature must reach the user.
        return {"error": "unconfirmed", "message": str(exc)}
    except (RuntimeError, ValueError) as exc:
        return {"error": "cpmm_error", "message": str(exc)}
    finally:
        await client.close()


async def get_cpmm_info(rpc_url: str, mint_str: str, rpc_timeout: float = 30.0) -> dict:
    """The CPMM pool of a graduated LaunchLab coin: price, reserves, fee."""
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url, timeout=rpc_timeout)
    try:
        pool = await _load_pool(client, mint, mint_str)
        return {
            "pool_address": str(pool["address"]),
            "price": _price(pool),
            "base_reserves": pool["base_reserve"] / 10 ** pool["base_decimals"],
            "quote_reserves": pool["quote_reserve"] / 10 ** pool["quote_decimals"],
            "pool_fee_pct": pool["fee_rate"] * 100 / FEE_RATE_DENOMINATOR,
        }
    except _NoPool as exc:
        return exc.result
    except TransactionUnconfirmedError as exc:
        # Sent, so the message's signature must reach the user.
        return {"error": "unconfirmed", "message": str(exc)}
    except (RuntimeError, ValueError) as exc:
        return {"error": "cpmm_error", "message": str(exc)}
    finally:
        await client.close()
