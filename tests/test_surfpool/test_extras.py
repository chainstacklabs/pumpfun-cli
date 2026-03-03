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
