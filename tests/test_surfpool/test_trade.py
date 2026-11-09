"""Surfpool integration: buy and sell against forked mainnet state."""

import pytest

from pumpfun_cli.core.trade import buy_token, sell_token


@pytest.mark.asyncio
async def test_buy_token(surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint):
    """Buy a small amount of tokens on the surfpool fork."""
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        amount=0.001,
        slippage=25,
    )

    assert "error" not in result, f"Buy failed: {result}"
    assert result["action"] == "buy"
    assert result["mint"] == active_mint
    assert result["quote_spent"] == 0.001
    assert result["tokens_received"] > 0
    assert result["signature"]


@pytest.mark.asyncio
async def test_buy_then_sell(
    surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint
):
    """Buy tokens then sell them all back."""
    # Buy
    buy_result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        amount=0.001,
        slippage=25,
        confirm=True,
    )
    assert "error" not in buy_result, f"Buy failed: {buy_result}"

    # Sell all
    sell_result = await sell_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        amount_str="all",
        slippage=25,
    )
    assert "error" not in sell_result, f"Sell failed: {sell_result}"
    assert sell_result["action"] == "sell"
    assert sell_result["tokens_sold"] > 0
    assert sell_result["quote_received"] > 0
    assert sell_result["signature"]


@pytest.mark.asyncio
async def test_buy_with_confirm(
    surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint
):
    """Buy with --confirm flag waits for confirmation."""
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        amount=0.001,
        slippage=25,
        confirm=True,
    )
    assert "error" not in result, f"Buy failed: {result}"
    assert result["confirmed"] is True
    assert result["signature"]


@pytest.mark.asyncio
async def test_buy_graduated_token_fails(
    surfpool_rpc, funded_keypair, test_keystore, test_password, graduated_mint
):
    """Buying a graduated token via bonding curve returns graduated error."""
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        amount=0.001,
        slippage=25,
    )
    assert result["error"] == "graduated"


@pytest.mark.asyncio
async def test_buy_then_partial_sell(
    surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint
):
    """Buy tokens then sell a specific amount (not all)."""
    buy_result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        amount=0.001,
        slippage=25,
        confirm=True,
    )
    assert "error" not in buy_result, f"Buy failed: {buy_result}"

    # Sell half the tokens
    half_tokens = buy_result["tokens_received"] / 2
    sell_result = await sell_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        amount_str=str(half_tokens),
        slippage=25,
    )
    assert "error" not in sell_result, f"Sell failed: {sell_result}"
    assert sell_result["action"] == "sell"
    assert sell_result["tokens_sold"] > 0
    assert sell_result["signature"]


@pytest.mark.asyncio
async def test_buy_without_confirm(
    surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint
):
    """Buy without --confirm returns signature but no confirmed key."""
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
        amount=0.001,
        slippage=25,
        confirm=False,
    )
    assert "error" not in result, f"Buy failed: {result}"
    assert result["signature"]
    assert "confirmed" not in result


@pytest.mark.asyncio
async def test_sell_caps_at_the_curves_real_reserves(
    surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """A curve holding less than its price promises takes the most it can pay for.

    The curve's real reserves are lowered with surfnet_setAccount, the way they
    drift on a mayhem coin. The capped sell lands; one more token reverts.
    """
    import struct

    import httpx
    from solders.pubkey import Pubkey

    from pumpfun_cli.core.launch import launch_token
    from pumpfun_cli.protocol.address import derive_bonding_curve
    from pumpfun_cli.protocol.client import RpcClient, TransactionFailedError
    from pumpfun_cli.protocol.curve import parse_bonding_curve
    from pumpfun_cli.protocol.instructions import build_sell_v2_instruction

    launched = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="Short",
        ticker="SHRT",
        description="short reserves",
        uri="https://example.com/short.json",
        initial_buy=1,
        confirm=True,
    )
    assert "error" not in launched, launched
    mint = Pubkey.from_string(launched["mint"])
    curve_pda = derive_bonding_curve(mint)

    client = RpcClient(surfpool_rpc)
    try:
        data = bytearray((await client.get_account_info(curve_pda)).value.data)
        struct.pack_into("<Q", data, 32, 10_000_000)  # real_quote_reserves: 0.01 SOL
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                surfpool_rpc,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "surfnet_setAccount",
                    "params": [str(curve_pda), {"data": bytes(data).hex()}],
                },
            )
            resp.raise_for_status()
            assert "error" not in resp.json(), resp.json()
        curve = parse_bonding_curve(bytes((await client.get_account_info(curve_pda)).value.data))
        assert curve["real_quote_reserves"] == 10_000_000

        preview = await sell_token(
            rpc_url=surfpool_rpc,
            keystore_path=str(test_keystore),
            password=test_password,
            mint_str=str(mint),
            amount_str="all",
            dry_run=True,
        )
        assert preview["tokens_kept_raw"] > 0, preview
        sellable = preview["tokens_in_raw"]

        # One token more than the cap is more than the curve can pay.
        with pytest.raises(TransactionFailedError) as over:
            await client.send_tx(
                [
                    build_sell_v2_instruction(
                        mint=mint,
                        creator=curve["creator"],
                        user=funded_keypair.pubkey(),
                        token_amount=sellable + 1,
                        min_quote_out=1,
                    )
                ],
                [funded_keypair],
                compute_units=200_000,
                confirm=True,
            )
        assert over.value.error_code == 6024  # Overflow: the payout exceeds real reserves
    finally:
        await client.close()

    sold = await sell_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=str(mint),
        amount_str="all",
        slippage=50,
        confirm=True,
    )
    assert "error" not in sold, sold
    assert sold["tokens_sold_raw"] == sellable
    assert sold["tokens_kept_raw"] > 0


@pytest.mark.asyncio
async def test_buy_past_the_curve_is_reported(
    surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Spending more than the curve has left fails with how many tokens remain."""
    from solana.rpc.async_api import AsyncClient

    from pumpfun_cli.core.launch import launch_token

    client = AsyncClient(surfpool_rpc)
    try:
        await client.request_airdrop(funded_keypair.pubkey(), 200_000_000_000)
    finally:
        await client.close()
    launched = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="Big",
        ticker="BIG",
        description="buy past the curve",
        uri="https://example.com/big.json",
        confirm=True,
    )
    assert "error" not in launched, launched
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=launched["mint"],
        amount=150,
        confirm=True,
    )
    assert result["error"] == "exceeds_curve", result
    assert result["curve_tokens_left_raw"] > 0
