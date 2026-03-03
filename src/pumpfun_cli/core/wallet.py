"""Wallet management — create, import, export, show, balance, tokens, transfer, close ATAs."""

import json
from pathlib import Path

from solders.keypair import Keypair
from solders.pubkey import Pubkey

from pumpfun_cli.core.validate import invalid_pubkey_error, parse_pubkey
from pumpfun_cli.crypto import decrypt_keypair, encrypt_keypair, get_pubkey
from pumpfun_cli.protocol.contracts import LAMPORTS_PER_SOL


def create_wallet(password: str, keystore_path: str, force: bool = False) -> dict:
    path = Path(keystore_path)
    if path.exists() and not force:
        try:
            existing_pubkey = get_pubkey(path)
        except Exception:
            existing_pubkey = "unknown (file unreadable)"
        return {
            "error": "wallet_exists",
            "message": f"Wallet already exists at {keystore_path}.",
            "existing_pubkey": existing_pubkey,
        }
    keypair = Keypair()
    encrypt_keypair(keypair, password, path)
    return {"pubkey": str(keypair.pubkey()), "path": str(path)}


def import_wallet(
    keypair_json_path: str, password: str, keystore_path: str, force: bool = False
) -> dict:
    path = Path(keystore_path)
    if path.exists() and not force:
        try:
            existing_pubkey = get_pubkey(path)
        except Exception:
            existing_pubkey = "unknown (file unreadable)"
        return {
            "error": "wallet_exists",
            "message": f"Wallet already exists at {keystore_path}.",
            "existing_pubkey": existing_pubkey,
        }
    data = json.loads(Path(keypair_json_path).read_text())
    keypair = Keypair.from_bytes(bytes(data))
    encrypt_keypair(keypair, password, path)
    return {"pubkey": str(keypair.pubkey()), "path": str(path)}


def export_wallet(keystore_path: str, password: str, output_path: str):
    keypair = decrypt_keypair(Path(keystore_path), password)
    data = list(bytes(keypair))
    Path(output_path).write_text(json.dumps(data))


def show_wallet(keystore_path: str) -> dict:
    pubkey = get_pubkey(Path(keystore_path))
    return {"pubkey": pubkey, "path": keystore_path}


async def get_balance(rpc_url: str, pubkey_str: str, commitment: str = "confirmed") -> dict:
    from pumpfun_cli.protocol.client import RpcClient

    pubkey = parse_pubkey(pubkey_str, "public key")
    if pubkey is None:
        return invalid_pubkey_error(pubkey_str, "public key")
    client = RpcClient(rpc_url)
    try:
        lamports = await client.get_balance(pubkey, commitment=commitment)
        return {"pubkey": pubkey_str, "sol_balance": lamports / LAMPORTS_PER_SOL}
    finally:
        await client.close()


async def list_token_accounts(
    rpc_url: str,
    pubkey_str: str,
    commitment: str = "confirmed",
    show_empty: bool = True,
) -> dict:
    from pumpfun_cli.protocol.client import RpcClient
    from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM, TOKEN_PROGRAM

    pubkey = parse_pubkey(pubkey_str, "public key")
    if pubkey is None:
        return invalid_pubkey_error(pubkey_str, "public key")
    client = RpcClient(rpc_url)
    try:
        accounts = await client.get_token_accounts_by_owner(
            pubkey, TOKEN_PROGRAM, commitment=commitment
        )
        accounts += await client.get_token_accounts_by_owner(
            pubkey, TOKEN_2022_PROGRAM, commitment=commitment
        )
        if not show_empty:
            accounts = [a for a in accounts if a["amount"] != 0]
        return {"pubkey": pubkey_str, "token_accounts": accounts}
    finally:
        await client.close()


async def transfer_sol(
    rpc_url: str,
    keystore_path: str,
    password: str,
    recipient_str: str,
    sol_amount: float,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    from solders.system_program import TransferParams, transfer

    from pumpfun_cli.protocol.client import RpcClient

    keypair = decrypt_keypair(Path(keystore_path), password)
    recipient = parse_pubkey(recipient_str, "recipient address")
    if recipient is None:
        return invalid_pubkey_error(recipient_str, "recipient address")
    lamports = int(sol_amount * LAMPORTS_PER_SOL)
    client = RpcClient(rpc_url)
    try:
        ix = transfer(
            TransferParams(
                from_pubkey=keypair.pubkey(),
                to_pubkey=recipient,
                lamports=lamports,
            )
        )
        sig = await client.send_tx(
            [ix],
            [keypair],
            confirm=confirm,
            priority_fee=priority_fee if priority_fee is not None else 200_000,
            compute_units=compute_units if compute_units is not None else 100_000,
        )
        result = {
            "action": "transfer",
            "from": str(keypair.pubkey()),
            "to": recipient_str,
            "sol_amount": sol_amount,
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    finally:
        await client.close()


async def transfer_all_sol(
    rpc_url: str,
    keystore_path: str,
    password: str,
    recipient_str: str,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    """Transfer entire SOL balance minus transaction fees."""
    import math

    from solders.system_program import TransferParams, transfer

    from pumpfun_cli.protocol.client import RpcClient
    from pumpfun_cli.protocol.contracts import BASE_TX_FEE

    keypair = decrypt_keypair(Path(keystore_path), password)
    recipient = parse_pubkey(recipient_str, "recipient address")
    if recipient is None:
        return invalid_pubkey_error(recipient_str, "recipient address")

    pf = priority_fee if priority_fee is not None else 200_000
    cu = compute_units if compute_units is not None else 100_000

    client = RpcClient(rpc_url)
    try:
        balance = await client.get_balance(keypair.pubkey())
        total_fees = BASE_TX_FEE + math.ceil(pf * cu / 1_000_000)
        send_lamports = balance - total_fees
        if send_lamports <= 0:
            return {
                "error": "insufficient_balance",
                "message": "Balance too low to cover transaction fees.",
            }

        ix = transfer(
            TransferParams(
                from_pubkey=keypair.pubkey(),
                to_pubkey=recipient,
                lamports=send_lamports,
            )
        )
        sig = await client.send_tx(
            [ix],
            [keypair],
            confirm=confirm,
            priority_fee=pf,
            compute_units=cu,
        )
        result = {
            "action": "transfer",
            "from": str(keypair.pubkey()),
            "to": recipient_str,
            "sol_amount": send_lamports / LAMPORTS_PER_SOL,
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    finally:
        await client.close()


async def transfer_token(
    rpc_url: str,
    keystore_path: str,
    password: str,
    recipient_str: str,
    mint_str: str,
    amount_str: str,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    """Transfer SPL tokens to another wallet, creating recipient ATA if needed."""
    from spl.token.instructions import (
        TransferCheckedParams,
        create_idempotent_associated_token_account,
        get_associated_token_address,
        transfer_checked,
    )

    from pumpfun_cli.protocol.client import RpcClient
    from pumpfun_cli.protocol.contracts import TOKEN_DECIMALS
    from pumpfun_cli.protocol.pumpswap import get_token_program_id

    keypair = decrypt_keypair(Path(keystore_path), password)
    recipient = parse_pubkey(recipient_str, "recipient address")
    if recipient is None:
        return invalid_pubkey_error(recipient_str, "recipient address")
    mint = parse_pubkey(mint_str, "mint address")
    if mint is None:
        return invalid_pubkey_error(mint_str, "mint address")
    client = RpcClient(rpc_url)
    try:
        token_program = await get_token_program_id(client, mint)
        sender_ata = get_associated_token_address(keypair.pubkey(), mint, token_program)
        recipient_ata = get_associated_token_address(recipient, mint, token_program)

        if amount_str.lower() == "all":
            raw_amount = await client.get_token_account_balance(sender_ata)
        else:
            raw_amount = int(float(amount_str) * (10**TOKEN_DECIMALS))

        if raw_amount <= 0:
            return {"error": "no_tokens", "message": "No tokens to transfer."}

        instructions = [
            create_idempotent_associated_token_account(
                payer=keypair.pubkey(),
                owner=recipient,
                mint=mint,
                token_program_id=token_program,
            ),
            transfer_checked(
                TransferCheckedParams(
                    program_id=token_program,
                    source=sender_ata,
                    mint=mint,
                    dest=recipient_ata,
                    owner=keypair.pubkey(),
                    amount=raw_amount,
                    decimals=TOKEN_DECIMALS,
                )
            ),
        ]

        sig = await client.send_tx(
            instructions,
            [keypair],
            confirm=confirm,
            priority_fee=priority_fee if priority_fee is not None else 200_000,
            compute_units=compute_units if compute_units is not None else 100_000,
        )
        result = {
            "action": "transfer_token",
            "from": str(keypair.pubkey()),
            "to": recipient_str,
            "mint": mint_str,
            "amount": raw_amount / (10**TOKEN_DECIMALS),
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    finally:
        await client.close()


async def close_empty_atas(
    rpc_url: str,
    keystore_path: str,
    password: str,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    from solders.instruction import AccountMeta, Instruction

    from pumpfun_cli.protocol.client import RpcClient
    from pumpfun_cli.protocol.contracts import TOKEN_2022_PROGRAM, TOKEN_PROGRAM

    keypair = decrypt_keypair(Path(keystore_path), password)
    pubkey = keypair.pubkey()
    client = RpcClient(rpc_url)
    try:
        all_accounts = await client.get_token_accounts_by_owner(pubkey, TOKEN_PROGRAM)
        all_accounts += await client.get_token_accounts_by_owner(pubkey, TOKEN_2022_PROGRAM)
        empty = [a for a in all_accounts if a["amount"] == 0]
        if not empty:
            return {"closed": 0, "recovered_sol": 0.0, "signature": None}

        # Batch up to 20 close instructions per tx
        instructions = []
        for acc in empty[:20]:
            token_prog = Pubkey.from_string(acc["program"])
            ata = Pubkey.from_string(acc["address"])
            # SPL Token CloseAccount instruction (index 9)
            ix = Instruction(
                program_id=token_prog,
                accounts=[
                    AccountMeta(pubkey=ata, is_signer=False, is_writable=True),
                    AccountMeta(pubkey=pubkey, is_signer=False, is_writable=True),
                    AccountMeta(pubkey=pubkey, is_signer=True, is_writable=False),
                ],
                data=bytes([9]),
            )
            instructions.append(ix)

        sig = await client.send_tx(
            instructions,
            [keypair],
            confirm=confirm,
            priority_fee=priority_fee if priority_fee is not None else 200_000,
            compute_units=compute_units if compute_units is not None else 100_000,
        )
        # Each ATA holds ~0.00203928 SOL rent
        recovered = len(instructions) * 0.00203928
        result = {
            "closed": len(instructions),
            "recovered_sol": round(recovered, 6),
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
        }
        if confirm:
            result["confirmed"] = True
        return result
    finally:
        await client.close()


async def drain_wallet(
    rpc_url: str,
    keystore_path: str,
    password: str,
    recipient_str: str,
    confirm: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    """Close empty ATAs, warn about non-empty tokens, transfer all remaining SOL."""
    keypair = decrypt_keypair(Path(keystore_path), password)
    wallet_pubkey = str(keypair.pubkey())

    recipient = parse_pubkey(recipient_str, "recipient address")
    if recipient is None:
        return invalid_pubkey_error(recipient_str, "recipient address")

    if recipient_str == wallet_pubkey:
        return {"error": "self_transfer", "message": "Cannot drain wallet to itself."}

    # Step 1 — Check non-empty tokens
    token_result = await list_token_accounts(rpc_url, wallet_pubkey, show_empty=False)
    non_empty_tokens = token_result["token_accounts"]

    # Step 2 — Close empty ATAs
    try:
        ata_result = await close_empty_atas(
            rpc_url,
            keystore_path,
            password,
            confirm=confirm,
            priority_fee=priority_fee,
            compute_units=compute_units,
        )
    except Exception as e:
        ata_result = {
            "closed": 0,
            "recovered_sol": 0.0,
            "signature": None,
            "ata_error": str(e),
        }

    # Step 3 — Transfer all SOL
    sol_result = await transfer_all_sol(
        rpc_url,
        keystore_path,
        password,
        recipient_str,
        confirm=confirm,
        priority_fee=priority_fee,
        compute_units=compute_units,
    )

    return {
        "action": "drain",
        "wallet": wallet_pubkey,
        "recipient": recipient_str,
        "non_empty_token_accounts": non_empty_tokens,
        "atas_closed": ata_result["closed"],
        "ata_rent_recovered_sol": ata_result["recovered_sol"],
        "ata_signature": ata_result.get("signature"),
        "ata_error": ata_result.get("ata_error"),
        "sol_transferred": sol_result.get("sol_amount", 0),
        "sol_signature": sol_result.get("signature"),
        "sol_error": sol_result.get("error"),
    }
