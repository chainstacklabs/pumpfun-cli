"""Bonding-curve trades, payouts and migration.

Amounts are in the coin's quote asset: SOL for most coins, or whatever mint
the curve records (USDC and others). Every result names that asset in
`quote_mint` / `quote_symbol`.
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
from pumpfun_cli.core.validate import invalid_pubkey_error, parse_pubkey
from pumpfun_cli.crypto import decrypt_keypair
from pumpfun_cli.protocol.address import (
    derive_amm_creator_vault,
    derive_bonding_curve,
    derive_creator_vault,
    find_ata,
    find_user_volume_accumulator,
)
from pumpfun_cli.protocol.client import RpcClient, TransactionFailedError
from pumpfun_cli.protocol.contracts import (
    ATA_RENT_LAMPORTS,
    LAMPORTS_PER_SOL,
    PUMP_BUY_COMPUTE_UNITS,
    PUMP_NON_SOL_TRADE_COMPUTE_UNITS,
    PUMP_SELL_COMPUTE_UNITS,
    PUMP_SLIPPAGE_ERROR_CODES,
    SOL_RENT_EXEMPT_MIN,
    TOKEN_DECIMALS,
    WSOL_MINT,
)
from pumpfun_cli.protocol.curve import (
    calculate_buy_tokens_out,
    calculate_sell_quote_out,
    get_token_price,
    parse_bonding_curve,
)
from pumpfun_cli.protocol.instructions import (
    build_buy_exact_quote_in_v2_instruction,
    build_claim_cashback_v2_instruction,
    build_close_volume_accumulator_instruction,
    build_collect_coin_creator_fee_instruction,
    build_collect_creator_fee_v2_instruction,
    build_migrate_v2_instruction,
    build_sell_v2_instruction,
)
from pumpfun_cli.protocol.pumpswap import get_token_program_id
from pumpfun_cli.protocol.quote import (
    fetch_global,
    get_mint_info,
    is_sol,
    normalize_quote_mint,
    quote_symbol,
)

DEFAULT_PRIORITY_FEE = 200_000


def _estimate_buy_required_lamports(
    sol_lamports: int,
    priority_fee: int,
    compute_units: int,
) -> int:
    """Estimate total lamports required for a buy transaction."""
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


def _tx_result(action: str, sig: str, confirm: bool, **fields) -> dict:
    result = {
        "action": action,
        **fields,
        "signature": sig,
        "explorer": f"https://solscan.io/tx/{sig}",
    }
    if confirm:
        result["confirmed"] = True
    return result


async def _read_curve(client: RpcClient, mint: Pubkey) -> dict | None:
    """The coin's decoded bonding curve, or None if it has none."""
    resp = await client.get_account_info(derive_bonding_curve(mint))
    if not resp.value:
        return None
    return parse_bonding_curve(bytes(resp.value.data))


async def _resolve_quote_arg(
    client: RpcClient, quote_mint_str: str | None
) -> tuple[Pubkey, Pubkey]:
    """(quote mint, its token program) for an optional --quote-mint flag; SOL by default."""
    quote_mint = WSOL_MINT
    if quote_mint_str:
        parsed = parse_pubkey(quote_mint_str, "quote mint")
        if parsed is None:
            raise ValueError(f"Invalid quote mint: {quote_mint_str}")
        quote_mint = normalize_quote_mint(parsed)
    quote_program, _ = await get_mint_info(client, quote_mint)
    return quote_mint, quote_program


async def buy_token(
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
    """Spend exactly `amount` of the coin's quote asset on its bonding curve (buy_exact_quote_in_v2)."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url)
    try:
        state = await _read_curve(client, mint)
        if state is None:
            return {"error": "not_found", "message": f"No bonding curve for {mint_str}"}
        if state["complete"]:
            return {"error": "graduated", "message": "Token has graduated to PumpSwap."}
        if state["creator"] is None:
            return {
                "error": "legacy_curve",
                "message": "This coin's bonding curve predates the creator field and cannot be traded.",
            }

        quote_mint = state["quote_mint"]
        symbol = quote_symbol(quote_mint)
        quote_program, quote_decimals = await get_mint_info(client, quote_mint)
        base_program = await get_token_program_id(client, mint)
        user = keypair.pubkey()

        amount_raw = to_raw(amount, quote_decimals)
        tokens_out = calculate_buy_tokens_out(state, amount_raw)
        # The program rejects a zero floor (6020), so 100% slippage still asks for one unit.
        min_tokens_out = max(1, int(tokens_out * (100 - slippage) / 100))

        eff_priority_fee = priority_fee if priority_fee is not None else DEFAULT_PRIORITY_FEE
        default_units = (
            PUMP_BUY_COMPUTE_UNITS if is_sol(quote_mint) else PUMP_NON_SOL_TRADE_COMPUTE_UNITS
        )
        eff_compute_units = compute_units if compute_units is not None else default_units
        sol_spend = amount_raw if is_sol(quote_mint) else 0
        required_lamports = _estimate_buy_required_lamports(
            sol_spend, eff_priority_fee, eff_compute_units
        )
        wallet_balance = await client.get_balance(user)
        quote_balance = None
        if not is_sol(quote_mint):
            quote_balance = await client.get_token_account_balance(
                find_ata(user, quote_mint, quote_program)
            )

        shortfall = None
        if wallet_balance < required_lamports:
            shortfall = (
                f"Wallet has {wallet_balance / LAMPORTS_PER_SOL:.6f} SOL"
                f" but trade requires ~{required_lamports / LAMPORTS_PER_SOL:.6f} SOL"
            )
        elif quote_balance is not None and quote_balance < amount_raw:
            shortfall = (
                f"Wallet holds {quote_balance / 10**quote_decimals} {symbol}"
                f" but the buy spends {amount} {symbol}"
            )

        if dry_run:
            spot_price = get_token_price(state, quote_decimals)
            expected_tokens = tokens_out / 10**TOKEN_DECIMALS
            effective_price = amount / expected_tokens if expected_tokens > 0 else 0
            price_impact = (
                (effective_price - spot_price) / spot_price * 100 if spot_price > 0 else 0
            )
            result = {
                "dry_run": True,
                "action": "buy",
                "venue": "bonding_curve",
                "mint": mint_str,
                "quote_mint": str(quote_mint),
                "quote_symbol": symbol,
                **amount_fields("quote_in", amount_raw, quote_decimals),
                **amount_fields("expected_tokens", tokens_out, TOKEN_DECIMALS),
                "effective_price": effective_price,
                "spot_price": spot_price,
                "price_impact_pct": round(price_impact, 4),
                **amount_fields("min_tokens_out", min_tokens_out, TOKEN_DECIMALS),
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

        ixs = [create_idempotent_associated_token_account(user, user, mint, base_program)]
        ixs.append(
            build_buy_exact_quote_in_v2_instruction(
                mint=mint,
                creator=state["creator"],
                user=user,
                spendable_quote_in=amount_raw,
                min_tokens_out=min_tokens_out,
                quote_mint=quote_mint,
                base_token_program=base_program,
                quote_token_program=quote_program,
                is_mayhem_mode=state["is_mayhem_mode"],
            )
        )

        try:
            sig = await client.send_tx(
                ixs,
                [keypair],
                confirm=confirm,
                priority_fee=eff_priority_fee,
                compute_units=eff_compute_units,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, PUMP_SLIPPAGE_ERROR_CODES)
        received = await confirmed_token_delta(client, sig, user, mint) if confirm else None
        return _tx_result(
            "buy",
            sig,
            confirm,
            venue="bonding_curve",
            mint=mint_str,
            quote_mint=str(quote_mint),
            quote_symbol=symbol,
            **amount_fields("quote_spent", amount_raw, quote_decimals),
            **received_fields("tokens_received", received, tokens_out, TOKEN_DECIMALS),
        )
    finally:
        await client.close()


async def sell_token(
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
    """Sell tokens into the coin's bonding curve (sell_v2), paid in its quote asset."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url)
    try:
        state = await _read_curve(client, mint)
        if state is None:
            return {"error": "not_found", "message": f"No bonding curve for {mint_str}"}
        if state["complete"]:
            return {"error": "graduated", "message": "Token has graduated to PumpSwap."}
        if state["creator"] is None:
            return {
                "error": "legacy_curve",
                "message": "This coin's bonding curve predates the creator field and cannot be traded.",
            }

        quote_mint = state["quote_mint"]
        symbol = quote_symbol(quote_mint)
        quote_program, quote_decimals = await get_mint_info(client, quote_mint)
        base_program = await get_token_program_id(client, mint)
        user = keypair.pubkey()
        user_ata = find_ata(user, mint, base_program)

        if amount_str.lower() == "all":
            token_amount = await client.get_token_account_balance(user_ata)
        else:
            token_amount = to_raw(amount_str, TOKEN_DECIMALS)
            actual_balance = await client.get_token_account_balance(user_ata)
            if actual_balance < token_amount:
                return {
                    "error": "insufficient_balance",
                    "message": (
                        f"Insufficient token balance. Have"
                        f" {actual_balance / 10**TOKEN_DECIMALS:.6f} tokens,"
                        f" need {token_amount / 10**TOKEN_DECIMALS:.6f} tokens."
                    ),
                    "available_tokens": actual_balance / 10**TOKEN_DECIMALS,
                    "required_tokens": token_amount / 10**TOKEN_DECIMALS,
                }

        if token_amount <= 0:
            return {"error": "no_tokens", "message": "No tokens to sell."}

        quote_out = calculate_sell_quote_out(state, token_amount)
        min_quote_out = max(1, int(quote_out * (1 - slippage / 100)))

        if dry_run:
            spot_price = get_token_price(state, quote_decimals)
            tokens_human = token_amount / 10**TOKEN_DECIMALS
            quote_out_human = quote_out / 10**quote_decimals
            effective_price = quote_out_human / tokens_human if tokens_human > 0 else 0
            price_impact = (
                (effective_price - spot_price) / spot_price * 100 if spot_price > 0 else 0
            )
            return {
                "dry_run": True,
                "action": "sell",
                "venue": "bonding_curve",
                "mint": mint_str,
                "quote_mint": str(quote_mint),
                "quote_symbol": symbol,
                **amount_fields("tokens_in", token_amount, TOKEN_DECIMALS),
                **amount_fields("expected_quote", quote_out, quote_decimals),
                "effective_price": effective_price,
                "spot_price": spot_price,
                "price_impact_pct": round(price_impact, 4),
                **amount_fields("min_quote_out", min_quote_out, quote_decimals),
                "slippage_pct": slippage,
            }

        ixs = []
        # A SOL coin pays out in native SOL; its quote account is only seed-checked.
        if not is_sol(quote_mint):
            ixs.append(
                create_idempotent_associated_token_account(user, user, quote_mint, quote_program)
            )
        ixs.append(
            build_sell_v2_instruction(
                mint=mint,
                creator=state["creator"],
                user=user,
                token_amount=token_amount,
                min_quote_out=min_quote_out,
                quote_mint=quote_mint,
                base_token_program=base_program,
                quote_token_program=quote_program,
                is_mayhem_mode=state["is_mayhem_mode"],
            )
        )

        try:
            sig = await client.send_tx(
                ixs,
                [keypair],
                confirm=confirm,
                priority_fee=priority_fee if priority_fee is not None else DEFAULT_PRIORITY_FEE,
                compute_units=compute_units
                if compute_units is not None
                else (
                    PUMP_SELL_COMPUTE_UNITS
                    if is_sol(quote_mint)
                    else PUMP_NON_SOL_TRADE_COMPUTE_UNITS
                ),
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, PUMP_SLIPPAGE_ERROR_CODES)
        return _tx_result(
            "sell",
            sig,
            confirm,
            venue="bonding_curve",
            mint=mint_str,
            quote_mint=str(quote_mint),
            quote_symbol=symbol,
            **amount_fields("tokens_sold", token_amount, TOKEN_DECIMALS),
            quote_received=quote_out / 10**quote_decimals,
        )
    finally:
        await client.close()


async def claim_cashback(
    rpc_url: str,
    keystore_path: str,
    password: str,
    quote_mint_str: str | None = None,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    """Claim cashback accrued in one quote asset (SOL by default)."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    user = keypair.pubkey()
    client = RpcClient(rpc_url)
    try:
        quote_mint, quote_program = await _resolve_quote_arg(client, quote_mint_str)
        accumulator = await client.get_account_info(find_user_volume_accumulator(user))
        if not accumulator.value:
            return {
                "error": "no_accumulator",
                "message": "This wallet has no volume accumulator, so there is no cashback.",
            }
        ixs = []
        if not is_sol(quote_mint):
            ixs.append(
                create_idempotent_associated_token_account(user, user, quote_mint, quote_program)
            )
        ixs.append(
            build_claim_cashback_v2_instruction(
                user=user, quote_mint=quote_mint, quote_token_program=quote_program
            )
        )
        try:
            sig = await client.send_tx(
                ixs,
                [keypair],
                confirm=confirm,
                priority_fee=priority_fee if priority_fee is not None else DEFAULT_PRIORITY_FEE,
                compute_units=compute_units if compute_units is not None else 100_000,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, set())
        return _tx_result(
            "claim_cashback",
            sig,
            confirm,
            quote_mint=str(quote_mint),
            quote_symbol=quote_symbol(quote_mint),
        )
    finally:
        await client.close()


async def close_volume_accumulator(
    rpc_url: str,
    keystore_path: str,
    password: str,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    """Close volume accumulator account, recovering rent."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    client = RpcClient(rpc_url)
    try:
        ix = build_close_volume_accumulator_instruction(keypair.pubkey())
        try:
            sig = await client.send_tx(
                [ix],
                [keypair],
                confirm=confirm,
                priority_fee=priority_fee if priority_fee is not None else DEFAULT_PRIORITY_FEE,
                compute_units=compute_units if compute_units is not None else 100_000,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, set())
        return _tx_result("close_volume_accumulator", sig, confirm)
    finally:
        await client.close()


async def migrate_token(
    rpc_url: str,
    keystore_path: str,
    password: str,
    mint_str: str,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    """Move a complete bonding curve's liquidity into its PumpSwap pool (migrate_v2)."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url)
    try:
        state = await _read_curve(client, mint)
        if state is None:
            return {"error": "not_found", "message": f"No bonding curve for {mint_str}"}
        if not state["complete"]:
            return {"error": "not_complete", "message": "Bonding curve is not complete yet."}

        global_state = await fetch_global(client)
        quote_mint = state["quote_mint"]
        quote_program, _ = await get_mint_info(client, quote_mint)
        base_program = await get_token_program_id(client, mint)

        ix = build_migrate_v2_instruction(
            mint=mint,
            user=keypair.pubkey(),
            withdraw_authority=global_state["withdraw_authority"],
            quote_mint=quote_mint,
            base_token_program=base_program,
            quote_token_program=quote_program,
        )
        try:
            sig = await client.send_tx(
                [ix],
                [keypair],
                compute_units=compute_units if compute_units is not None else 400_000,
                confirm=confirm,
                priority_fee=priority_fee if priority_fee is not None else DEFAULT_PRIORITY_FEE,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, set())
        return _tx_result("migrate", sig, confirm, mint=mint_str)
    finally:
        await client.close()


async def collect_creator_fees(
    rpc_url: str,
    keystore_path: str,
    password: str,
    quote_mint_str: str | None = None,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    """Collect creator fees in one quote asset (SOL by default) from pump.fun and PumpSwap.

    Vaults are per creator and per quote asset, so fees earned in USDC are
    collected with a separate run.
    """
    keypair = decrypt_keypair(Path(keystore_path), password)
    creator = keypair.pubkey()
    client = RpcClient(rpc_url)
    try:
        quote_mint, quote_program = await _resolve_quote_arg(client, quote_mint_str)
        _, quote_decimals = await get_mint_info(client, quote_mint)
        instructions = []

        # pump.fun: a SOL vault holds lamports itself, and keeps its rent-exempt
        # minimum; any other quote sits in the vault's ATA.
        vault = derive_creator_vault(creator)
        if is_sol(quote_mint):
            rent_floor = await client.get_minimum_balance_for_rent_exemption(0)
            pump_balance = max(0, await client.get_balance(vault) - rent_floor)
        else:
            pump_balance = await client.get_token_account_balance(
                find_ata(vault, quote_mint, quote_program)
            )

        amm_vault = derive_amm_creator_vault(creator)
        pumpswap_balance = await client.get_token_account_balance(
            find_ata(amm_vault, quote_mint, quote_program)
        )

        if pump_balance <= 0 and pumpswap_balance <= 0:
            return {"error": "no_fees", "message": "No creator fees to collect."}

        if pumpswap_balance > 0 or not is_sol(quote_mint):
            # Both payouts land in the creator's token account for the quote asset.
            instructions.append(
                create_idempotent_associated_token_account(
                    creator, creator, quote_mint, quote_program
                )
            )
        if pump_balance > 0:
            instructions.append(
                build_collect_creator_fee_v2_instruction(
                    creator=creator, quote_mint=quote_mint, quote_token_program=quote_program
                )
            )
        if pumpswap_balance > 0:
            instructions.append(
                build_collect_coin_creator_fee_instruction(
                    creator=creator, quote_mint=quote_mint, quote_token_program=quote_program
                )
            )

        try:
            sig = await client.send_tx(
                instructions,
                [keypair],
                confirm=confirm,
                priority_fee=priority_fee if priority_fee is not None else DEFAULT_PRIORITY_FEE,
                compute_units=compute_units if compute_units is not None else 150_000,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, set())
        return _tx_result(
            "collect_creator_fee",
            sig,
            confirm,
            quote_mint=str(quote_mint),
            quote_symbol=quote_symbol(quote_mint),
            # Vault balances read before sending; fees landing in between are swept too.
            pump_recovered=pump_balance / 10**quote_decimals,
            pumpswap_recovered=pumpswap_balance / 10**quote_decimals,
        )
    finally:
        await client.close()
