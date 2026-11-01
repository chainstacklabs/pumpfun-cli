"""Launch: guards run before anything is uploaded or sent, then create (and buy)."""

from unittest.mock import AsyncMock, patch

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.core.launch import launch_token, opening_buy_tokens
from pumpfun_cli.protocol.address import find_ata, find_holder_rewards
from pumpfun_cli.protocol.contracts import (
    BUY_EXACT_QUOTE_IN_V2_DISCRIMINATOR,
    CREATE_V2_DISCRIMINATOR,
    EXTEND_ACCOUNT_DISCRIMINATOR,
    PUMP_GLOBAL,
    PUMP_PROGRAM,
    TOKEN_2022_PROGRAM,
    USDC_MINT,
)
from pumpfun_cli.protocol.quote import decode_global
from tests.test_core.helpers import (
    T22_QUOTE,
    FakeClient,
    add_quote_control,
    build_global_data,
)


def _chain(**global_overrides):
    client = FakeClient()
    client.add(PUMP_GLOBAL, build_global_data(**global_overrides))
    add_quote_control(client, {T22_QUOTE: 7_000_000})
    client.add_mint(T22_QUOTE, 6, TOKEN_2022_PROGRAM)
    return client


async def _launch(client, tmp_keystore, **kwargs):
    upload = AsyncMock(return_value="https://ipfs.io/ipfs/x")
    with (
        patch("pumpfun_cli.core.launch.RpcClient", return_value=client),
        patch("pumpfun_cli.core.launch.upload_metadata", upload),
    ):
        result = await launch_token(
            "http://rpc", tmp_keystore, "testpass", "Name", "TKR", "d", **kwargs
        )
    return result, upload


def _pump(client):
    return [i for i in client.sent[0]["instructions"] if i.program_id == PUMP_PROGRAM]


async def test_create_only(tmp_keystore):
    client = _chain()
    result, upload = await _launch(client, tmp_keystore)
    assert result["action"] == "launch"
    assert result["quote_symbol"] == "SOL"
    upload.assert_awaited_once()
    ixs = _pump(client)
    assert [bytes(i.data[:8]) for i in ixs] == [
        CREATE_V2_DISCRIMINATOR,
        EXTEND_ACCOUNT_DISCRIMINATOR,
    ]
    assert len(client.sent[0]["signers"]) == 2


async def test_create_and_buy_in_one_transaction(tmp_keystore):
    client = _chain()
    result, _ = await _launch(client, tmp_keystore, initial_buy=0.5, slippage=10)
    assert len(client.sent) == 1
    buy = _pump(client)[-1]
    assert bytes(buy.data[:8]) == BUY_EXACT_QUOTE_IN_V2_DISCRIMINATOR
    spend = int.from_bytes(bytes(buy.data[8:16]), "little")
    floor = int.from_bytes(bytes(buy.data[16:24]), "little")
    expected = opening_buy_tokens(decode_global(build_global_data()), spend, 30_000_000_000, None)
    assert spend == 500_000_000
    assert floor == expected * 90 // 100
    assert result["expected_tokens"] == expected / 1e6


async def test_holder_reward_buy_targets_the_holder_rewards_vault(tmp_keystore):
    from pumpfun_cli.protocol.address import derive_creator_vault

    client = _chain()
    await _launch(client, tmp_keystore, initial_buy=0.1, is_holder_reward=True)
    create, _, buy = _pump(client)
    mint = create.accounts[0].pubkey
    assert bytes(create.data)[-1] == 1
    assert buy.accounts[16].pubkey == derive_creator_vault(find_holder_rewards(mint))


async def test_custom_quote_with_creator_fee(tmp_keystore):
    from pathlib import Path

    from pumpfun_cli.crypto import decrypt_keypair

    user = decrypt_keypair(Path(tmp_keystore), "testpass").pubkey()
    client = _chain()
    client.token_balances[find_ata(user, T22_QUOTE, TOKEN_2022_PROGRAM)] = 10_000_000
    result, _ = await _launch(
        client, tmp_keystore, initial_buy=2, quote_mint_str=str(T22_QUOTE), creator_fee_bps=100
    )
    assert result["creator_fee_bps"] == 100
    create, _, buy = _pump(client)
    assert create.accounts[16].pubkey == T22_QUOTE
    assert int.from_bytes(bytes(buy.data[8:16]), "little") == 2_000_000


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"creator_fee_bps": 100}, "store 0"),
        ({"is_mayhem": True, "quote_mint_str": str(USDC_MINT)}, "Mayhem"),
        ({"quote_mint_str": str(Pubkey.new_unique())}, "admit"),
        ({"quote_mint_str": str(T22_QUOTE), "creator_fee_bps": 900}, "maximum"),
    ],
)
async def test_refused_before_upload(tmp_keystore, kwargs, message):
    client = _chain()
    client.add_mint(Pubkey.new_unique(), 6)
    with pytest.raises(ValueError, match=message):
        await _launch(client, tmp_keystore, **kwargs)
    assert client.sent == []


async def test_holder_reward_disabled(tmp_keystore):
    client = _chain(is_holder_reward_enabled=False)
    result, upload = await _launch(client, tmp_keystore, is_holder_reward=True)
    assert result["error"] == "holder_reward_disabled"
    upload.assert_not_awaited()


async def test_custom_quote_buy_needs_the_asset(tmp_keystore):
    client = _chain()
    result, upload = await _launch(
        client, tmp_keystore, initial_buy=2, quote_mint_str=str(T22_QUOTE)
    )
    assert result["error"] == "insufficient_balance"
    upload.assert_not_awaited()


async def test_hosted_uri_skips_the_upload(tmp_keystore):
    client = _chain()
    result, upload = await _launch(client, tmp_keystore, uri="https://example.com/m.json")
    upload.assert_not_awaited()
    assert result["metadata_uri"] == "https://example.com/m.json"
    create = _pump(client)[0]
    assert b"https://example.com/m.json" in bytes(create.data)


async def test_refused_upload_points_at_uri(tmp_keystore):
    client = _chain()
    with (
        patch("pumpfun_cli.core.launch.RpcClient", return_value=client),
        patch(
            "pumpfun_cli.core.launch.upload_metadata",
            AsyncMock(side_effect=RuntimeError("Metadata upload to pump.fun failed (HTTP 405)")),
        ),
    ):
        result = await launch_token("http://rpc", tmp_keystore, "testpass", "N", "T", "d")
    assert result["error"] == "ipfs_failed"
    assert "--uri" in result["message"]
    assert client.sent == []


def test_upload_identifies_itself(respx_mock):
    import asyncio

    import httpx

    from pumpfun_cli.core.launch import upload_metadata

    route = respx_mock.post("https://pump.fun/api/ipfs").mock(
        return_value=httpx.Response(200, json={"metadataUri": "https://ipfs.io/ipfs/x"})
    )
    assert asyncio.run(upload_metadata("N", "T", "d")) == "https://ipfs.io/ipfs/x"
    assert route.calls.last.request.headers["user-agent"].startswith("pumpfun-cli")
