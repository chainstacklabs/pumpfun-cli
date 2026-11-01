import pytest

from pumpfun_cli.protocol.client import RpcClient


def test_client_creation():
    client = RpcClient("https://example.com")
    assert client is not None


def test_client_requires_url():
    with pytest.raises(TypeError):
        RpcClient()


def test_send_tx_accepts_confirm_parameter():
    import inspect

    from pumpfun_cli.protocol.client import RpcClient

    sig = inspect.signature(RpcClient.send_tx)
    assert "confirm" in sig.parameters
    assert sig.parameters["confirm"].default is False


# --- TransactionFailedError tests ---


def test_transaction_failed_error_parses_slippage_code():
    """TransactionFailedError parses error_code and instruction_index from meta.err string."""
    from pumpfun_cli.protocol.client import TransactionFailedError

    err_str = "TransactionErrorInstructionError((0, Tagged(InstructionErrorCustom(6002))))"
    exc = TransactionFailedError(err_str)
    assert exc.error_code == 6002
    assert exc.instruction_index == 0
    assert exc.raw_error == err_str


def test_transaction_failed_error_parses_unknown_format():
    """TransactionFailedError with non-matching string has None for parsed fields."""
    from pumpfun_cli.protocol.client import TransactionFailedError

    err_str = "some unknown error format"
    exc = TransactionFailedError(err_str)
    assert exc.error_code is None
    assert exc.instruction_index is None
    assert exc.raw_error == err_str


def test_transaction_failed_error_inherits_runtime_error():
    """TransactionFailedError is a RuntimeError subclass."""
    from pumpfun_cli.protocol.client import TransactionFailedError

    exc = TransactionFailedError("test")
    assert isinstance(exc, RuntimeError)


# --- transaction version selection ---


def _ixs(n_accounts: int):
    from solders.instruction import AccountMeta, Instruction
    from solders.pubkey import Pubkey

    program = Pubkey.new_unique()
    metas = [AccountMeta(Pubkey.new_unique(), False, True) for _ in range(n_accounts)]
    return [Instruction(program, b"\x00" * 16, metas)]


def test_small_transaction_compiles_as_v0():
    from solders.hash import Hash
    from solders.message import MessageV0
    from solders.pubkey import Pubkey

    from pumpfun_cli.protocol.client import build_message

    msg = build_message(Pubkey.new_unique(), _ixs(10), Hash.default(), 100_000, 200_000)
    assert isinstance(msg, MessageV0)


def test_oversized_transaction_compiles_as_v1_with_budget_in_header():
    from solders.hash import Hash
    from solders.message import MessageV1
    from solders.pubkey import Pubkey

    from pumpfun_cli.protocol.client import TX_V0_MAX_BYTES, build_message, transaction_size

    msg = build_message(Pubkey.new_unique(), _ixs(40), Hash.default(), 300_000, 200_000)
    assert isinstance(msg, MessageV1)
    assert transaction_size(msg) > TX_V0_MAX_BYTES
    assert len(msg.instructions) == 1  # no ComputeBudget instructions in a v1 message


def test_transaction_beyond_v1_limit_is_refused():
    from solders.hash import Hash
    from solders.pubkey import Pubkey

    from pumpfun_cli.protocol.client import build_message

    with pytest.raises(ValueError):
        build_message(Pubkey.new_unique(), _ixs(125), Hash.default(), 300_000, 200_000)


def test_transaction_failed_error_parses_json_rpc_shape():
    from pumpfun_cli.protocol.client import TransactionFailedError

    exc = TransactionFailedError({"InstructionError": [3, {"Custom": 6042}]})
    assert (exc.instruction_index, exc.error_code) == (3, 6042)


# --- getTransaction is read as raw JSON, whatever the transaction version ---

_SIG = "5" * 87


@pytest.mark.asyncio
async def test_get_transaction_reads_v1_result(respx_mock):
    import httpx

    respx_mock.post("https://rpc.test").mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "slot": 7,
                    "blockTime": 99,
                    "version": 1,
                    "transaction": ["AAAA", "base64"],
                    "meta": {"err": None, "fee": 5000},
                },
            },
        )
    )
    client = RpcClient("https://rpc.test")
    try:
        result = await client.get_transaction(_SIG)
    finally:
        await client.close()
    assert result == {
        "slot": 7,
        "err": None,
        "fee": 5000,
        "block_time": 99,
        "pre_token_balances": [],
        "post_token_balances": [],
    }
    body = respx_mock.calls.last.request.content
    assert b'"maxSupportedTransactionVersion":1' in body.replace(b" ", b"")


@pytest.mark.asyncio
async def test_get_transaction_not_found(respx_mock):
    import httpx

    respx_mock.post("https://rpc.test").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": None})
    )
    client = RpcClient("https://rpc.test")
    try:
        assert await client.get_transaction(_SIG) is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_transaction_http_error_hides_the_url(respx_mock):
    import httpx

    url = "https://rpc.test/secret-api-key"
    respx_mock.post(url).mock(return_value=httpx.Response(429))
    client = RpcClient(url)
    try:
        with pytest.raises(RuntimeError) as info:
            await client.get_transaction(_SIG)
    finally:
        await client.close()
    assert "429" in str(info.value)
    assert "secret-api-key" not in str(info.value)
    assert info.value.__cause__ is None and info.value.__context__ is None


@pytest.mark.asyncio
async def test_failed_confirmation_reports_the_signature():
    from unittest.mock import AsyncMock, MagicMock

    from solders.signature import Signature

    sig = Signature.default()
    client = RpcClient("https://rpc.test")
    client.rpc = MagicMock()
    client.rpc.send_transaction = AsyncMock(return_value=MagicMock(value=sig))
    client.rpc.confirm_transaction = AsyncMock(side_effect=TimeoutError())
    with pytest.raises(RuntimeError, match=str(sig)):
        await client._send_and_confirm(MagicMock(), confirm=True)
