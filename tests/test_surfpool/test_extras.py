"""Surfpool integration: bonding curve extras (cashback, volume acc, migrate)."""

import pytest

from pumpfun_cli.core.trade import (
    claim_cashback,
    close_volume_accumulator,
    migrate_token,
)


@pytest.mark.asyncio
async def test_migrate_not_complete(
    surfpool_rpc, funded_keypair, test_keystore, test_password, active_mint
):
    """Migrating an active (not graduated) token returns not_complete."""
    result = await migrate_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=active_mint,
    )
    assert result["error"] == "not_complete"


@pytest.mark.asyncio
async def test_migrate_not_found(surfpool_rpc, funded_keypair, test_keystore, test_password):
    """Migrating a non-existent token returns not_found."""
    from solders.keypair import Keypair

    fake_mint = str(Keypair().pubkey())
    result = await migrate_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=fake_mint,
    )
    assert result["error"] == "not_found"


@pytest.mark.asyncio
async def test_claim_cashback_runs(surfpool_rpc, funded_keypair, test_keystore, test_password):
    """Claim cashback submits a transaction (may fail on-chain if no accumulator).

    We verify the function runs without Python-level errors and returns
    either a signature or a known error.
    """
    result = await claim_cashback(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
    )
    # Either succeeds or returns an error dict — both are valid outcomes
    assert "signature" in result or "error" in result


@pytest.mark.asyncio
async def test_close_volume_accumulator_runs(
    surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Close volume accumulator submits a transaction.

    Like cashback, may fail on-chain if no accumulator exists.
    """
    result = await close_volume_accumulator(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
    )
    assert "signature" in result or "error" in result


@pytest.mark.asyncio
async def test_collect_creator_fees_no_fees(
    surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Collecting creator fees from a non-creator wallet returns no_fees."""
    from pumpfun_cli.core.trade import collect_creator_fees

    result = await collect_creator_fees(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
    )
    assert result["error"] == "no_fees"
    assert "No creator fees" in result["message"]


@pytest.mark.asyncio
async def test_migrate_a_completed_curve(
    surfpool_rpc, funded_keypair, test_keystore, test_password
):
    """Launch a coin, buy its whole curve, then migrate it into its PumpSwap pool."""
    from solana.rpc.async_api import AsyncClient
    from solders.pubkey import Pubkey

    from pumpfun_cli.core.info import get_token_info
    from pumpfun_cli.core.launch import launch_token
    from pumpfun_cli.core.trade import buy_token
    from pumpfun_cli.protocol.address import derive_amm_pool, derive_bonding_curve
    from pumpfun_cli.protocol.client import RpcClient
    from pumpfun_cli.protocol.curve import parse_bonding_curve
    from pumpfun_cli.protocol.instructions import build_buy_v2_instruction

    client = AsyncClient(surfpool_rpc)
    try:
        await client.request_airdrop(funded_keypair.pubkey(), 200_000_000_000)
    finally:
        await client.close()

    launched = await launch_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        name="Migrate",
        ticker="MIG",
        description="migrate test",
        uri="https://example.com/migrate.json",
        confirm=True,
    )
    assert "error" not in launched, launched
    mint = launched["mint"]
    mint_pk = Pubkey.from_string(mint)

    # A small buy creates the token account; buy_v2 then takes every token left.
    bought = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=mint,
        amount=0.01,
        confirm=True,
    )
    assert "error" not in bought, bought
    client = RpcClient(surfpool_rpc)
    try:
        curve = parse_bonding_curve(
            bytes((await client.get_account_info(derive_bonding_curve(mint_pk))).value.data)
        )
        await client.send_tx(
            [
                build_buy_v2_instruction(
                    mint=mint_pk,
                    creator=curve["creator"],
                    user=funded_keypair.pubkey(),
                    token_amount=curve["real_token_reserves"],
                    max_quote_cost=150_000_000_000,
                )
            ],
            [funded_keypair],
            compute_units=400_000,
            confirm=True,
        )
    finally:
        await client.close()

    migrated = await migrate_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=mint,
        confirm=True,
    )
    assert "error" not in migrated, migrated

    client = AsyncClient(surfpool_rpc)
    try:
        pool = await client.get_account_info(derive_amm_pool(mint_pk))
    finally:
        await client.close()
    assert pool.value is not None
    info = await get_token_info(surfpool_rpc, mint)
    assert info["graduated"] is True
