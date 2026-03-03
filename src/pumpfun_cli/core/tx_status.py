"""Check transaction status on-chain."""

from solders.signature import Signature

from pumpfun_cli.protocol.client import RpcClient
from pumpfun_cli.protocol.contracts import LAMPORTS_PER_SOL


async def get_tx_status(rpc_url: str, signature: str) -> dict:
    """Fetch transaction status by signature.

    Returns a dict with status, slot, fee, etc. — or an error dict
    for invalid signatures or missing transactions.
    """
    try:
        Signature.from_string(signature)
    except (ValueError, Exception):
        return {
            "error": "invalid_signature",
            "message": "Invalid transaction signature. Must be a base58-encoded 64-byte signature.",
        }

    client = RpcClient(rpc_url)
    try:
        tx_data = await client.get_transaction(signature)
        if tx_data is None:
            return {
                "error": "not_found",
                "message": f"Transaction {signature} not found on-chain.",
            }

        err = tx_data["err"]
        status = "failed" if err else "confirmed"

        result: dict = {
            "signature": signature,
            "status": status,
            "slot": tx_data["slot"],
            "block_time": tx_data["block_time"],
            "fee_lamports": tx_data["fee"],
            "fee_sol": tx_data["fee"] / LAMPORTS_PER_SOL,
            "explorer": f"https://solscan.io/tx/{signature}",
        }

        if err:
            result["error"] = err

        return result
    finally:
        await client.close()
