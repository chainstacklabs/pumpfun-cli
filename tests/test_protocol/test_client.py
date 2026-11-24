from unittest.mock import MagicMock

import pytest

from pumpfun_cli.protocol.client import RpcClient, TransactionExpiredError, TransactionFailedError


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
                    "meta": {
                        "err": None,
                        "fee": 5000,
                        "preBalances": [100, 1],
                        "postBalances": [95, 1],
                    },
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
        "pre_token_balances": None,
        "post_token_balances": None,
        "pre_balances": [100, 1],
        "post_balances": [95, 1],
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


def _waiting(client, statuses, heights=(), history=None):
    """Make `client`'s polls pop the next status; returns the signature it sends.

    `statuses` entries: None (not seen), "processed", "confirmed", ("confirmed", err)
    or an Exception to raise.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from solders.signature import Signature
    from solders.transaction_status import TransactionConfirmationStatus as S

    levels = {"processed": S.Processed, "confirmed": S.Confirmed}
    sig = Signature.default()
    queue, heights = list(statuses), list(heights)

    def status(entry):
        if entry is None:
            return None
        level, err = entry if isinstance(entry, tuple) else (entry, None)
        return SimpleNamespace(confirmation_status=levels[level], err=err)

    async def statuses_call(sigs, search_transaction_history=False):
        if search_transaction_history:
            return SimpleNamespace(value=[status(history)])
        entry = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(entry, Exception):
            raise entry
        return SimpleNamespace(value=[status(entry)])

    async def height_call(commitment=None):
        return SimpleNamespace(value=heights.pop(0) if len(heights) > 1 else heights[0])

    client.sender.send_transaction = AsyncMock(return_value=MagicMock(value=sig))
    client.rpc.get_signature_statuses = statuses_call
    client.rpc.get_block_height = height_call
    return sig


def _tx(sig):
    from types import SimpleNamespace

    return SimpleNamespace(signatures=[sig])


@pytest.fixture
def waiting(mocked):
    """(client, waiting(statuses, ...) -> signature) on a client closed afterwards."""
    return mocked, lambda *args, **kwargs: _waiting(mocked, *args, **kwargs)


@pytest.fixture
def no_wait(monkeypatch):
    import pumpfun_cli.protocol.client as client_module

    monkeypatch.setattr(client_module, "CONFIRM_POLL_SECONDS", 0)


@pytest.mark.asyncio
async def test_confirm_waits_until_the_transaction_lands(no_wait, waiting):
    client, wait = waiting
    sig = wait([None, "processed", "confirmed"], heights=[10])
    assert await client._send_and_confirm(_tx(sig), True, 100) == str(sig)


@pytest.mark.asyncio
async def test_a_landed_failure_raises_with_its_error_code(no_wait, waiting):
    err = {"InstructionError": [2, {"Custom": 6004}]}
    client, wait = waiting
    sig = wait([("confirmed", err)])
    with pytest.raises(TransactionFailedError) as info:
        await client._send_and_confirm(_tx(sig), True, 100)
    assert info.value.error_code == 6004


@pytest.mark.asyncio
async def test_past_its_blockhash_and_unseen_it_never_landed(no_wait, waiting):
    client, wait = waiting
    sig = wait([None], heights=[99, 101])
    with pytest.raises(TransactionExpiredError, match="nothing was spent") as info:
        await client._send_and_confirm(_tx(sig), True, 100)
    assert str(sig) in str(info.value)


@pytest.mark.asyncio
async def test_past_its_blockhash_but_in_history_it_landed(no_wait, waiting):
    """A node that lags can miss a landed transaction; history has the last word."""
    client, wait = waiting
    sig = wait([None], heights=[101], history="confirmed")
    assert await client._send_and_confirm(_tx(sig), True, 100) == str(sig)


@pytest.mark.asyncio
async def test_a_silent_rpc_makes_the_outcome_unknown(no_wait, waiting, monkeypatch):
    import pumpfun_cli.protocol.client as client_module

    monkeypatch.setattr(client_module, "CONFIRM_RPC_SILENCE_SECONDS", 0)
    client, wait = waiting
    sig = wait([TimeoutError(), TimeoutError()])
    with pytest.raises(RuntimeError, match="whether it landed is unknown") as info:
        await client._send_and_confirm(_tx(sig), True, 100)
    assert str(sig) in str(info.value)
    assert "tx-status" not in str(info.value)


@pytest.mark.asyncio
async def test_one_unanswered_poll_is_not_an_outcome(no_wait, waiting):
    client, wait = waiting
    sig = wait([TimeoutError(), "confirmed"])
    assert await client._send_and_confirm(_tx(sig), True, 100) == str(sig)


@pytest.mark.asyncio
async def test_fast_sends_without_waiting(no_wait, waiting):
    client, wait = waiting
    sig = wait([TimeoutError()])
    assert await client._send_and_confirm(_tx(sig), False, 100) == str(sig)


@pytest.mark.asyncio
async def test_get_transaction_non_json_is_a_runtime_error(respx_mock):
    import httpx

    respx_mock.post("https://rpc.test").mock(return_value=httpx.Response(200, text="<html>"))
    client = RpcClient("https://rpc.test")
    try:
        with pytest.raises(RuntimeError, match="not JSON"):
            await client.get_transaction(_SIG)
    finally:
        await client.close()


def _blockhash_rpc():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from solders.hash import Hash

    rpc = MagicMock()
    rpc.get_latest_blockhash = AsyncMock(
        return_value=SimpleNamespace(
            value=SimpleNamespace(blockhash=Hash.default(), last_valid_block_height=100)
        )
    )
    return rpc


def _transfer():
    from solders.keypair import Keypair
    from solders.system_program import TransferParams, transfer

    payer = Keypair()
    ix = transfer(TransferParams(from_pubkey=payer.pubkey(), to_pubkey=payer.pubkey(), lamports=1))
    return ix, payer


@pytest.fixture
async def mocked():
    """An RpcClient whose RPC calls are one mock; its real HTTP clients are closed afterwards."""
    client = RpcClient("http://secret-key.rpc")
    real = client.rpc, client.sender
    client.rpc = client.sender = _blockhash_rpc()
    yield client
    for http in real:
        await http.close()


@pytest.fixture
def sending(mocked):
    return (mocked, *_transfer())


@pytest.mark.asyncio
async def test_no_blockhash_means_nothing_was_sent(sending):
    from unittest.mock import AsyncMock

    from pumpfun_cli.protocol.client import TransactionNotSentError

    client, ix, payer = sending
    client.rpc.get_latest_blockhash = AsyncMock(side_effect=OSError("http://secret-key.rpc down"))
    with pytest.raises(TransactionNotSentError, match="nothing was sent") as info:
        await client.send_tx([ix], [payer])
    assert "secret-key" not in str(info.value)
    assert info.value.__context__ is None


@pytest.mark.asyncio
async def test_a_refused_send_is_not_sent_and_says_why(sending):
    from unittest.mock import AsyncMock

    from solana.rpc.core import RPCException

    from pumpfun_cli.protocol.client import TransactionNotSentError

    client, ix, payer = sending
    client.rpc.send_transaction = AsyncMock(side_effect=RPCException("Blockhash not found"))
    with pytest.raises(TransactionNotSentError, match="Blockhash not found"):
        await client.send_tx([ix], [payer])


@pytest.mark.asyncio
async def test_a_send_that_timed_out_may_still_land(sending):
    from unittest.mock import AsyncMock

    import httpx

    from pumpfun_cli.protocol.client import TransactionNotSentError

    client, ix, payer = sending
    client.rpc.send_transaction = AsyncMock(side_effect=httpx.ReadTimeout("http://secret-key.rpc"))
    with pytest.raises(RuntimeError, match="may still land") as info:
        await client.send_tx([ix], [payer])
    assert not isinstance(info.value, TransactionNotSentError)
    assert "secret-key" not in str(info.value) and info.value.__context__ is None


@pytest.mark.asyncio
async def test_a_send_gets_one_attempt():
    """A retry could turn a send that reached the node into a refusal."""
    from unittest.mock import AsyncMock

    import httpx2

    from pumpfun_cli.protocol.client import TransactionNotSentError

    client = RpcClient("http://secret-key.rpc")
    real_rpc, client.rpc = client.rpc, _blockhash_rpc()
    ix, payer = _transfer()
    refusal = httpx2.Response(
        200,
        json={"jsonrpc": "2.0", "id": 0, "error": {"code": -32602, "message": "refused"}},
        request=httpx2.Request("POST", "http://secret-key.rpc"),
    )
    post = AsyncMock(side_effect=[httpx2.ReadTimeout("http://secret-key.rpc"), refusal])
    client.sender._provider._post_request_once = post
    try:
        with pytest.raises(RuntimeError, match="may still land") as info:
            await client.send_tx([ix], [payer])
    finally:
        await real_rpc.close()
        await client.sender.close()
    assert not isinstance(info.value, TransactionNotSentError)
    assert post.await_count == 1


@pytest.mark.asyncio
async def test_a_send_with_no_answer_is_waited_on_until_it_lands(no_wait, waiting):
    import httpx

    client, wait = waiting
    sig = wait(["confirmed"])
    client.sender.send_transaction.side_effect = httpx.ReadTimeout("http://secret-key.rpc")
    assert await client._send_and_confirm(_tx(sig), True, 100) == str(sig)


@pytest.mark.asyncio
async def test_a_send_with_no_answer_that_never_lands_expires(no_wait, waiting):
    import httpx

    client, wait = waiting
    sig = wait([None], heights=[101])
    client.sender.send_transaction.side_effect = httpx.ReadTimeout("http://secret-key.rpc")
    with pytest.raises(TransactionExpiredError, match="safe to send again"):
        await client._send_and_confirm(_tx(sig), True, 100)
