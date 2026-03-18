"""Stateless Solana RPC client for CLI usage."""

from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TokenAccountOpts, TxOpts
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

DEFAULT_RPC_TIMEOUT = 30.0

_ERR_PATTERN = r"InstructionError\(\((\d+),.*InstructionErrorCustom\((\d+)\)"


class TransactionFailedError(RuntimeError):
    """Raised when a confirmed transaction fails on-chain."""

    error_code: int | None
    instruction_index: int | None
    raw_error: str

    def __init__(self, err_obj: object) -> None:
        import re

        self.raw_error = str(err_obj)
        match = re.search(_ERR_PATTERN, self.raw_error)
        if match:
            self.instruction_index = int(match.group(1))
            self.error_code = int(match.group(2))
        else:
            self.instruction_index = None
            self.error_code = None
        super().__init__(self.raw_error)


class RpcClient:
    """Simplified Solana RPC client — no background tasks, no lifecycle."""

    def __init__(self, rpc_url: str, timeout: float = DEFAULT_RPC_TIMEOUT):
        self.rpc = AsyncClient(rpc_url, timeout=timeout)

    async def get_blockhash(self) -> Hash:
        resp = await self.rpc.get_latest_blockhash()
        return resp.value.blockhash

    async def get_account_info(self, pubkey: Pubkey):
        return await self.rpc.get_account_info(pubkey)

    async def get_balance(self, pubkey: Pubkey, commitment: str | None = None) -> int:
        kwargs = {}
        if commitment is not None:
            kwargs["commitment"] = commitment
        resp = await self.rpc.get_balance(pubkey, **kwargs)
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

    async def send_tx(
        self,
        instructions: list[Instruction],
        signers: list[Keypair],
        compute_units: int = 100_000,
        priority_fee: int = 200_000,
        confirm: bool = False,
    ) -> str:
        budget_ixs = [
            set_compute_unit_limit(compute_units),
            set_compute_unit_price(priority_fee),
        ]
        all_ixs = budget_ixs + instructions
        blockhash = await self.get_blockhash()
        msg = MessageV0.try_compile(signers[0].pubkey(), all_ixs, [], blockhash)
        tx = VersionedTransaction(msg, signers)
        resp = await self.rpc.send_transaction(tx, opts=TxOpts(skip_preflight=True))
        if confirm:
            await self.rpc.confirm_transaction(resp.value, commitment="confirmed", sleep_seconds=1)
            tx_resp = await self.rpc.get_transaction(
                resp.value, max_supported_transaction_version=0
            )
            if tx_resp.value and tx_resp.value.transaction.meta.err:
                raise TransactionFailedError(tx_resp.value.transaction.meta.err)
        return str(resp.value)

    async def get_transaction(self, signature_str: str) -> dict | None:
        """Fetch a confirmed transaction by signature string.

        Returns a dict with slot, err, fee, block_time — or None if not found.
        """
        from solders.signature import Signature

        sig = Signature.from_string(signature_str)
        resp = await self.rpc.get_transaction(sig, max_supported_transaction_version=0)
        if resp.value is None:
            return None
        return {
            "slot": resp.value.slot,
            "err": resp.value.transaction.meta.err,
            "fee": resp.value.transaction.meta.fee,
            "block_time": resp.value.block_time,
        }

    async def close(self):
        await self.rpc.close()
