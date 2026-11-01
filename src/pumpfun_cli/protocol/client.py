"""Stateless Solana RPC client for CLI usage."""

import re

import httpx
from solana.rpc.async_api import AsyncClient
from solana.rpc.core import TokenAccountOpts, TxOptsModel
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.message import MessageV0, MessageV1, TransactionConfig
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction

from pumpfun_cli.protocol.contracts import TX_V1_LOADED_ACCOUNTS_DATA_LIMIT

DEFAULT_RPC_TIMEOUT = 30.0

# Serialized size limits: a v0 transaction must fit one 1232-byte packet, a v1
# transaction may carry up to 4096 bytes.
TX_V0_MAX_BYTES = 1232
TX_V1_MAX_BYTES = 4096


def transaction_size(msg: MessageV0 | MessageV1) -> int:
    """Serialized size of a transaction carrying `msg` once signed."""
    signatures = msg.header.num_required_signatures
    return len(bytes(msg)) + 1 + 64 * signatures


def build_message(
    payer: Pubkey,
    instructions: list[Instruction],
    blockhash: Hash,
    compute_units: int,
    priority_fee: int,
) -> MessageV0 | MessageV1:
    """Compile a v0 message, or a v1 message when the v0 one would not fit a packet.

    A PumpSwap buy on a cashback pool, or a launch that buys in the same
    transaction, carries more accounts than v0 allows without lookup tables.
    v1 raises the limit and states the compute budget in its header, so it
    carries no ComputeBudget instructions; `priority_fee` (micro-lamports per
    compute unit) becomes the total in lamports v1 expects.

    Raises:
        ValueError: If the transaction is too large even for v1
    """
    budget_ixs = [set_compute_unit_limit(compute_units), set_compute_unit_price(priority_fee)]
    msg_v0 = MessageV0.try_compile(payer, budget_ixs + instructions, [], blockhash)
    if transaction_size(msg_v0) <= TX_V0_MAX_BYTES:
        return msg_v0
    msg_v1 = MessageV1.try_compile(
        payer,
        instructions,
        blockhash,
        TransactionConfig(
            compute_unit_limit=compute_units,
            priority_fee=priority_fee * compute_units // 1_000_000,
            loaded_accounts_data_size_limit=TX_V1_LOADED_ACCOUNTS_DATA_LIMIT,
        ),
    )
    size = transaction_size(msg_v1)
    if size > TX_V1_MAX_BYTES:
        raise ValueError(f"Transaction is {size} bytes, over the {TX_V1_MAX_BYTES}-byte limit")
    return msg_v1


# Matches both the solders repr and the JSON-RPC shape of a custom program error.
_ERR_PATTERNS = (
    r"InstructionError\(\((\d+),.*InstructionErrorCustom\((\d+)\)",
    r"'InstructionError': \[(\d+), \{'Custom': (\d+)\}\]",
)


class TransactionFailedError(RuntimeError):
    """Raised when a confirmed transaction fails on-chain."""

    error_code: int | None
    instruction_index: int | None
    raw_error: str

    def __init__(self, err_obj: object) -> None:
        self.raw_error = str(err_obj)
        self.instruction_index = None
        self.error_code = None
        for pattern in _ERR_PATTERNS:
            match = re.search(pattern, self.raw_error)
            if match:
                self.instruction_index = int(match.group(1))
                self.error_code = int(match.group(2))
                break
        super().__init__(self.raw_error)


class RpcClient:
    """Simplified Solana RPC client — no background tasks, no lifecycle."""

    def __init__(self, rpc_url: str, timeout: float = DEFAULT_RPC_TIMEOUT):
        self.rpc_url = rpc_url
        self.timeout = timeout
        self.rpc = AsyncClient(rpc_url, timeout=timeout)

    async def get_blockhash(self) -> Hash:
        resp = await self.rpc.get_latest_blockhash()
        return resp.value.blockhash

    async def get_account_info(self, pubkey: Pubkey):
        return await self.rpc.get_account_info(pubkey)

    async def get_multiple_accounts(self, pubkeys: list[Pubkey]):
        resp = await self.rpc.get_multiple_accounts(pubkeys)
        return resp.value

    async def get_balance(self, pubkey: Pubkey, commitment: str | None = None) -> int:
        kwargs = {}
        if commitment is not None:
            kwargs["commitment"] = commitment
        resp = await self.rpc.get_balance(pubkey, **kwargs)
        return resp.value

    async def get_minimum_balance_for_rent_exemption(self, size: int) -> int:
        resp = await self.rpc.get_minimum_balance_for_rent_exemption(size)
        return resp.value

    async def get_token_account_balance(self, token_account: Pubkey) -> int:
        try:
            resp = await self.rpc.get_token_account_balance(token_account)
        except Exception:
            return 0
        if resp.value:
            return int(resp.value.amount)
        return 0

    async def get_token_accounts_by_owner(
        self,
        owner: Pubkey,
        token_program: Pubkey,
        commitment: str | None = None,
    ) -> list[dict]:
        try:
            kwargs = {}
            if commitment is not None:
                kwargs["commitment"] = commitment
            resp = await self.rpc.get_token_accounts_by_owner_json_parsed(
                owner, TokenAccountOpts(program_id=token_program), **kwargs
            )
        except Exception:
            return []
        results = []
        for item in resp.value:
            info = item.account.data.parsed["info"]
            results.append(
                {
                    "address": str(item.pubkey),
                    "mint": info["mint"],
                    "amount": int(info["tokenAmount"]["amount"]),
                    "decimals": info["tokenAmount"]["decimals"],
                    "ui_amount": info["tokenAmount"].get("uiAmount", 0),
                    "program": str(token_program),
                }
            )
        return results

    async def get_program_accounts(
        self,
        program_id: Pubkey,
        filters: list,
    ):
        resp = await self.rpc.get_program_accounts(program_id, encoding="base64", filters=filters)
        return resp.value

    async def _send_and_confirm(self, tx: VersionedTransaction, confirm: bool) -> str:
        resp = await self.rpc.send_transaction(tx, opts=TxOptsModel(skip_preflight=True))
        signature = str(resp.value)
        if confirm:
            try:
                await self.rpc.confirm_transaction(
                    resp.value, commitment="confirmed", sleep_seconds=1
                )
                status = await self.get_transaction(signature)
            except Exception as exc:  # noqa: BLE001 - the send already happened
                raise RuntimeError(
                    f"Sent {signature} but could not confirm it ({type(exc).__name__}). "
                    f"Check it with: pumpfun tx-status {signature}"
                ) from None
            if status and status["err"]:
                raise TransactionFailedError(status["err"])
        return signature

    async def send_tx(
        self,
        instructions: list[Instruction],
        signers: list[Keypair],
        compute_units: int = 100_000,
        priority_fee: int = 200_000,
        confirm: bool = False,
    ) -> str:
        """Sign and send a transaction. `priority_fee` is in micro-lamports per compute unit.

        Sent as v0 when it fits, otherwise as v1; see `build_message`.
        """
        blockhash = await self.get_blockhash()
        msg = build_message(
            signers[0].pubkey(), instructions, blockhash, compute_units, priority_fee
        )
        return await self._send_and_confirm(VersionedTransaction(msg, signers), confirm)

    async def get_transaction(self, signature_str: str) -> dict | None:
        """Fetch a confirmed transaction's outcome by signature.

        Reads the raw JSON-RPC result rather than a typed response, so a
        transaction in any version is reported the same way.

        Returns a dict with slot, err, fee, block_time — or None if not found.
        """
        Signature.from_string(signature_str)  # reject a malformed signature before any I/O
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature_str,
                {
                    "encoding": "base64",
                    "commitment": "confirmed",
                    "maxSupportedTransactionVersion": 1,
                },
            ],
        }
        # Errors are rebuilt without the request: RPC URLs usually carry an API key.
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                resp = await http.post(self.rpc_url, json=payload)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"getTransaction failed: {type(exc).__name__}") from None
        if resp.is_error:
            raise RuntimeError(f"getTransaction failed: HTTP {resp.status_code}")
        body = resp.json()
        if body.get("error"):
            raise RuntimeError(f"getTransaction failed: {body['error'].get('message')}")
        result = body.get("result")
        if result is None:
            return None
        meta = result.get("meta") or {}
        return {
            "slot": result.get("slot"),
            "err": meta.get("err"),
            "fee": meta.get("fee"),
            "block_time": result.get("blockTime"),
        }

    async def close(self):
        await self.rpc.close()
