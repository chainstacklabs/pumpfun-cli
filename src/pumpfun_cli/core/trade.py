"""Buy and sell execution."""

from pathlib import Path

from solders.pubkey import Pubkey

from pumpfun_cli.core.validate import invalid_pubkey_error, parse_pubkey
from pumpfun_cli.crypto import decrypt_keypair
from pumpfun_cli.protocol.address import (
    derive_associated_bonding_curve,
    derive_bonding_curve,
)
from pumpfun_cli.protocol.client import RpcClient, TransactionFailedError
from pumpfun_cli.protocol.contracts import (
    ATA_RENT_LAMPORTS,
    LAMPORTS_PER_SOL,
    PUMP_SLIPPAGE_ERROR_CODES,
    SOL_RENT_EXEMPT_MIN,
    TOKEN_DECIMALS,
)
from pumpfun_cli.protocol.curve import (
    calculate_buy_tokens_out,
    calculate_sell_sol_out,
    get_token_price_sol,
)
from pumpfun_cli.protocol.idl_parser import IDLParser
from pumpfun_cli.protocol.instructions import (
    build_buy_exact_sol_in_instructions,
    build_claim_cashback_instruction,
    build_close_volume_accumulator_instruction,
    build_migrate_instruction,
    build_sell_instructions,
)
from pumpfun_cli.protocol.pumpswap import get_token_program_id

IDL_PATH = Path(__file__).parent.parent.parent.parent / "idl" / "pump_fun_idl.json"


def _coerce_pubkey(raw) -> Pubkey:
    """Coerce raw IDL pubkey value (bytes/list/str/Pubkey) to Pubkey."""
    if isinstance(raw, (list, bytes)):
        return Pubkey.from_bytes(bytes(raw))
    if isinstance(raw, str):
        return Pubkey.from_string(raw)
    return raw


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


async def buy_token(
    rpc_url: str,
    keystore_path: str,
    password: str,
    mint_str: str,
    sol_amount: float,
    slippage: int = 15,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
    dry_run: bool = False,
) -> dict:
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url)
    idl = IDLParser(str(IDL_PATH))
    try:
        bonding_curve = derive_bonding_curve(mint)
        token_program = await get_token_program_id(client, mint)
        assoc_bc = derive_associated_bonding_curve(mint, bonding_curve, token_program)

        resp = await client.get_account_info(bonding_curve)
        if not resp.value:
            return {"error": "not_found", "message": f"No bonding curve for {mint_str}"}
        state = idl.decode_account_data(resp.value.data, "BondingCurve", skip_discriminator=True)

        if state.get("complete"):
            return {"error": "graduated", "message": "Token has graduated to PumpSwap."}

        sol_lamports = int(sol_amount * LAMPORTS_PER_SOL)
        tokens_out = calculate_buy_tokens_out(state, sol_lamports)
        min_tokens_out = int(tokens_out * (100 - slippage) / 100)

        # Pre-trade SOL balance validation
        eff_priority_fee = priority_fee if priority_fee is not None else 200_000
        eff_compute_units = compute_units if compute_units is not None else 100_000
        required_lamports = _estimate_buy_required_lamports(
            sol_lamports, eff_priority_fee, eff_compute_units
        )
        wallet_balance = await client.get_balance(keypair.pubkey())

        if dry_run:
            spot_price = get_token_price_sol(state)
            expected_tokens_human = tokens_out / (10**TOKEN_DECIMALS)
            effective_price = (
                sol_amount / expected_tokens_human if expected_tokens_human > 0 else 0
            )
            price_impact = (
                (effective_price - spot_price) / spot_price * 100 if spot_price > 0 else 0
            )
            result = {
                "dry_run": True,
                "action": "buy",
                "venue": "bonding_curve",
                "mint": mint_str,
                "sol_in": sol_amount,
                "expected_tokens": expected_tokens_human,
                "effective_price_sol": effective_price,
                "spot_price_sol": spot_price,
                "price_impact_pct": round(price_impact, 4),
                "min_tokens_out": min_tokens_out / (10**TOKEN_DECIMALS),
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

        creator = _coerce_pubkey(state["creator"])
        is_mayhem = state.get("is_mayhem_mode", False)

        ixs = build_buy_exact_sol_in_instructions(
            idl=idl,
            mint=mint,
            user=keypair.pubkey(),
            bonding_curve=bonding_curve,
            assoc_bc=assoc_bc,
            creator=creator,
            is_mayhem=is_mayhem,
            spendable_sol_in=sol_lamports,
            min_tokens_out=min_tokens_out,
            token_program=token_program,
        )

        try:
            sig = await client.send_tx(
                ixs,
                [keypair],
                confirm=confirm,
                priority_fee=priority_fee if priority_fee is not None else 200_000,
                compute_units=compute_units if compute_units is not None else 100_000,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, PUMP_SLIPPAGE_ERROR_CODES)
        result = {
            "action": "buy",
            "mint": mint_str,
            "sol_spent": sol_amount,
            "tokens_received": tokens_out / (10**TOKEN_DECIMALS),
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
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
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url)
    idl = IDLParser(str(IDL_PATH))
    try:
        bonding_curve = derive_bonding_curve(mint)
        token_program = await get_token_program_id(client, mint)
        assoc_bc = derive_associated_bonding_curve(mint, bonding_curve, token_program)

        resp = await client.get_account_info(bonding_curve)
        if not resp.value:
            return {"error": "not_found", "message": f"No bonding curve for {mint_str}"}
        state = idl.decode_account_data(resp.value.data, "BondingCurve", skip_discriminator=True)

        if state.get("complete"):
            return {"error": "graduated", "message": "Token has graduated to PumpSwap."}

        from spl.token.instructions import get_associated_token_address

        user_ata = get_associated_token_address(keypair.pubkey(), mint, token_program)

        if amount_str.lower() == "all":
            token_amount = await client.get_token_account_balance(user_ata)
        else:
            token_amount = int(float(amount_str) * (10**TOKEN_DECIMALS))
            # Pre-trade token balance validation for specific amounts
            actual_balance = await client.get_token_account_balance(user_ata)
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

        sol_out = calculate_sell_sol_out(state, token_amount)
        min_sol = int(sol_out * (1 - slippage / 100))

        if dry_run:
            spot_price = get_token_price_sol(state)
            tokens_human = token_amount / (10**TOKEN_DECIMALS)
            sol_out_human = sol_out / LAMPORTS_PER_SOL
            effective_price = sol_out_human / tokens_human if tokens_human > 0 else 0
            price_impact = (
                (effective_price - spot_price) / spot_price * 100 if spot_price > 0 else 0
            )
            return {
                "dry_run": True,
                "action": "sell",
                "venue": "bonding_curve",
                "mint": mint_str,
                "tokens_in": tokens_human,
                "expected_sol": sol_out_human,
                "effective_price_sol": effective_price,
                "spot_price_sol": spot_price,
                "price_impact_pct": round(price_impact, 4),
                "min_sol_out": min_sol / LAMPORTS_PER_SOL,
                "slippage_pct": slippage,
            }

        creator = _coerce_pubkey(state["creator"])
        is_mayhem = state.get("is_mayhem_mode", False)
        is_cashback = state.get("is_cashback_coin", False)

        ixs = build_sell_instructions(
            idl=idl,
            mint=mint,
            user=keypair.pubkey(),
            bonding_curve=bonding_curve,
            assoc_bc=assoc_bc,
            creator=creator,
            is_mayhem=is_mayhem,
            token_amount=token_amount,
            min_sol_output=min_sol,
            is_cashback=is_cashback,
            token_program=token_program,
        )

        try:
            sig = await client.send_tx(
                ixs,
                [keypair],
                confirm=confirm,
                priority_fee=priority_fee if priority_fee is not None else 200_000,
                compute_units=compute_units if compute_units is not None else 100_000,
            )
        except TransactionFailedError as exc:
            return _handle_tx_error(exc, PUMP_SLIPPAGE_ERROR_CODES)
        result = {
            "action": "sell",
            "mint": mint_str,
            "tokens_sold": token_amount / (10**TOKEN_DECIMALS),
            "sol_received": sol_out / LAMPORTS_PER_SOL,
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    finally:
        await client.close()


async def claim_cashback(
    rpc_url: str,
    keystore_path: str,
    password: str,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    """Claim volume-based cashback rewards."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    client = RpcClient(rpc_url)
    idl = IDLParser(str(IDL_PATH))
    try:
        ix = build_claim_cashback_instruction(idl=idl, user=keypair.pubkey())
        sig = await client.send_tx(
            [ix],
            [keypair],
            confirm=confirm,
            priority_fee=priority_fee if priority_fee is not None else 200_000,
            compute_units=compute_units if compute_units is not None else 100_000,
        )
        result = {
            "action": "claim_cashback",
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
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
    idl = IDLParser(str(IDL_PATH))
    try:
        ix = build_close_volume_accumulator_instruction(idl=idl, user=keypair.pubkey())
        sig = await client.send_tx(
            [ix],
            [keypair],
            confirm=confirm,
            priority_fee=priority_fee if priority_fee is not None else 200_000,
            compute_units=compute_units if compute_units is not None else 100_000,
        )
        result = {
            "action": "close_volume_accumulator",
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
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
    """Trigger migration from bonding curve to PumpSwap AMM."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url)
    idl = IDLParser(str(IDL_PATH))
    try:
        # Verify bonding curve is complete
        bonding_curve = derive_bonding_curve(mint)
        resp = await client.get_account_info(bonding_curve)
        if not resp.value:
            return {"error": "not_found", "message": f"No bonding curve for {mint_str}"}
        state = idl.decode_account_data(resp.value.data, "BondingCurve", skip_discriminator=True)
        if not state.get("complete"):
            return {"error": "not_complete", "message": "Bonding curve is not complete yet."}

        # Read withdraw_authority from Global account
        from pumpfun_cli.protocol.contracts import PUMP_GLOBAL

        global_resp = await client.get_account_info(PUMP_GLOBAL)
        if not global_resp.value:
            return {"error": "global_not_found", "message": "Global account not found."}
        global_state = idl.decode_account_data(
            global_resp.value.data, "Global", skip_discriminator=True
        )
        withdraw_authority = _coerce_pubkey(global_state["withdraw_authority"])

        ix = build_migrate_instruction(
            idl=idl,
            mint=mint,
            user=keypair.pubkey(),
            withdraw_authority=withdraw_authority,
        )
        sig = await client.send_tx(
            [ix],
            [keypair],
            compute_units=compute_units if compute_units is not None else 400_000,
            confirm=confirm,
            priority_fee=priority_fee if priority_fee is not None else 200_000,
        )
        result = {
            "action": "migrate",
            "mint": mint_str,
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    finally:
        await client.close()


async def collect_creator_fees(
    rpc_url: str,
    keystore_path: str,
    password: str,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    """Collect creator fees from both pump.fun and PumpSwap vaults."""
    from spl.token.instructions import get_associated_token_address

    from pumpfun_cli.protocol.address import derive_amm_creator_vault, derive_creator_vault
    from pumpfun_cli.protocol.contracts import TOKEN_PROGRAM, WSOL_MINT
    from pumpfun_cli.protocol.instructions import (
        build_collect_coin_creator_fee_instruction,
        build_collect_creator_fee_instruction,
    )

    keypair = decrypt_keypair(Path(keystore_path), password)
    creator = keypair.pubkey()
    client = RpcClient(rpc_url)
    idl = IDLParser(str(IDL_PATH))
    try:
        instructions = []
        pump_balance = 0
        pumpswap_balance = 0

        # Check pump.fun creator vault
        vault = derive_creator_vault(creator)
        pump_balance = await client.get_balance(vault)

        if pump_balance > 0:
            instructions.append(build_collect_creator_fee_instruction(idl=idl, creator=creator))

        # Check PumpSwap creator vault
        amm_vault_authority = derive_amm_creator_vault(creator)
        amm_vault_ata = get_associated_token_address(amm_vault_authority, WSOL_MINT, TOKEN_PROGRAM)
        pumpswap_balance = await client.get_token_account_balance(amm_vault_ata)

        if pumpswap_balance > 0:
            instructions.append(build_collect_coin_creator_fee_instruction(creator=creator))

        if not instructions:
            return {"error": "no_fees", "message": "No creator fees to collect."}

        sig = await client.send_tx(
            instructions,
            [keypair],
            confirm=confirm,
            priority_fee=priority_fee if priority_fee is not None else 200_000,
            compute_units=compute_units if compute_units is not None else 100_000,
        )
        result = {
            "action": "collect_creator_fee",
            "pump_recovered_sol": pump_balance / LAMPORTS_PER_SOL,
            "pumpswap_recovered_sol": pumpswap_balance / LAMPORTS_PER_SOL,
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    finally:
        await client.close()
