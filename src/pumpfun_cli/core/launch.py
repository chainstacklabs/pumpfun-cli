"""Token launch — create_v2 with IPFS metadata upload."""

import os
from pathlib import Path

import httpx
from solders.keypair import Keypair

from pumpfun_cli.crypto import decrypt_keypair
from pumpfun_cli.protocol.address import derive_associated_bonding_curve, derive_bonding_curve
from pumpfun_cli.protocol.client import RpcClient
from pumpfun_cli.protocol.contracts import LAMPORTS_PER_SOL
from pumpfun_cli.protocol.idl_parser import IDLParser
from pumpfun_cli.protocol.instructions import (
    build_buy_instructions,
    build_create_instructions,
    build_extend_account_instruction,
)

IDL_PATH = Path(__file__).parent.parent.parent.parent / "idl" / "pump_fun_idl.json"


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


async def launch_token(
    rpc_url: str,
    keystore_path: str,
    password: str,
    name: str,
    ticker: str,
    description: str,
    image_path: str | None = None,
    initial_buy_sol: float | None = None,
    is_mayhem: bool = False,
    is_cashback: bool = False,
    priority_fee: int | None = None,
    compute_units: int | None = None,
) -> dict:
    """Launch a new token on pump.fun using create_v2."""
    wallet = decrypt_keypair(Path(keystore_path), password)
    client = RpcClient(rpc_url)
    idl = IDLParser(str(IDL_PATH))
    try:
        # 1. Upload metadata to IPFS
        uri = await upload_metadata(name, ticker, description, image_path)
        if not uri:
            return {"error": "ipfs_failed", "message": "Failed to get metadata URI from IPFS."}

        # 2. Generate mint keypair
        mint_keypair = Keypair()
        mint = mint_keypair.pubkey()

        # 3. Build create_v2 instruction
        instructions = build_create_instructions(
            idl=idl,
            mint=mint,
            user=wallet.pubkey(),
            name=name,
            symbol=ticker,
            uri=uri,
            is_mayhem=is_mayhem,
            is_cashback=is_cashback,
        )

        # 4. Add extend_account instruction (required for frontend visibility)
        bonding_curve = derive_bonding_curve(mint)
        extend_ix = build_extend_account_instruction(idl, bonding_curve, wallet.pubkey())
        instructions.append(extend_ix)

        # 5. Optionally add initial buy
        if initial_buy_sol and initial_buy_sol > 0:
            sol_lamports = int(initial_buy_sol * LAMPORTS_PER_SOL)
            assoc_bc = derive_associated_bonding_curve(mint, bonding_curve)
            buy_ixs = build_buy_instructions(
                idl=idl,
                mint=mint,
                user=wallet.pubkey(),
                bonding_curve=bonding_curve,
                assoc_bc=assoc_bc,
                creator=wallet.pubkey(),
                is_mayhem=is_mayhem,
                token_amount=1,  # Minimum — contract handles actual amount
                max_sol_cost=sol_lamports,
            )
            instructions.extend(buy_ixs)

        # 6. Send transaction (sign with both wallet and mint keypair)
        sig = await client.send_tx(
            instructions,
            [wallet, mint_keypair],
            compute_units=compute_units if compute_units is not None else 250_000,
            priority_fee=priority_fee if priority_fee is not None else 500_000,
        )
        return {
            "action": "launch",
            "name": name,
            "ticker": ticker,
            "mint": str(mint),
            "metadata_uri": uri,
            "is_cashback": is_cashback,
            "initial_buy_sol": initial_buy_sol,
            "signature": sig,
            "explorer": f"https://solscan.io/tx/{sig}",
            "pump_url": f"https://pump.fun/coin/{mint}",
        }
    finally:
        await client.close()
