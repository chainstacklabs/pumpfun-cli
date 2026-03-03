"""Surfpool integration test fixtures.

These tests require a running surfpool instance:
    surfpool start --airdrop <PUBKEY> --airdrop-amount 100000000000 --no-deploy

Run with: pytest tests/test_surfpool/ -v
"""

import asyncio
import os

import pytest
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair

from pumpfun_cli.crypto import encrypt_keypair

SURFPOOL_RPC = os.environ.get("SURFPOOL_RPC", "http://127.0.0.1:8899")
SURFPOOL_PASSWORD = "test-password-surfpool"


def pytest_collection_modifyitems(config, items):
    """Skip surfpool tests unless --surfpool flag is passed."""
    if not config.getoption("--surfpool", default=False):
        skip = pytest.mark.skip(reason="need --surfpool flag to run")
        for item in items:
            if "test_surfpool" in str(item.fspath):
                item.add_marker(skip)


def pytest_addoption(parser):
    parser.addoption(
        "--surfpool", action="store_true", default=False, help="run surfpool integration tests"
    )


@pytest.fixture(scope="session")
def surfpool_rpc():
    """Return the surfpool RPC URL."""
    return SURFPOOL_RPC


@pytest.fixture(scope="session")
def test_keypair():
    """Generate a fresh keypair for this test session."""
    return Keypair()


@pytest.fixture(scope="session")
def test_keystore(test_keypair, tmp_path_factory):
    """Create an encrypted keystore file for the test keypair."""
    keystore_dir = tmp_path_factory.mktemp("keystore")
    keystore_path = keystore_dir / "wallet.enc"
    encrypt_keypair(test_keypair, SURFPOOL_PASSWORD, keystore_path)
    return keystore_path


@pytest.fixture(scope="session")
def test_password():
    return SURFPOOL_PASSWORD


@pytest.fixture(scope="session")
def funded_keypair(surfpool_rpc, test_keypair):
    """Ensure the test keypair has SOL on surfpool.

    Either start surfpool with --airdrop <pubkey>, or this fixture
    will request an airdrop via standard RPC.
    """

    async def _fund():
        client = AsyncClient(surfpool_rpc)
        try:
            pubkey = test_keypair.pubkey()
            resp = await client.get_balance(pubkey)
            if resp.value < 1_000_000_000:  # less than 1 SOL
                await client.request_airdrop(pubkey, 100_000_000_000)  # 100 SOL
                # wait for airdrop to land
                for _ in range(30):
                    await asyncio.sleep(0.5)
                    resp = await client.get_balance(pubkey)
                    if resp.value >= 1_000_000_000:
                        break
                else:
                    pytest.fail(
                        f"Airdrop failed. Start surfpool with: "
                        f"surfpool start --airdrop {pubkey} --airdrop-amount 100000000000 --no-deploy"
                    )
        finally:
            await client.close()
        return test_keypair

    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_fund())


@pytest.fixture(scope="session")
def active_mint():
    """Return an active pump.fun token mint for testing.

    Override with SURFPOOL_TEST_MINT env var to use a specific token.
    Falls back to a known active mint (must have an open bonding curve on mainnet).
    """
    mint = os.environ.get("SURFPOOL_TEST_MINT")
    if not mint:
        pytest.skip(
            "Set SURFPOOL_TEST_MINT=<mint_address> to a token with an active "
            "bonding curve on mainnet"
        )
    return mint


@pytest.fixture(scope="session")
def graduated_mint():
    """Return a graduated pump.fun token mint (on PumpSwap AMM).

    Override with SURFPOOL_GRADUATED_MINT env var.
    """
    mint = os.environ.get("SURFPOOL_GRADUATED_MINT")
    if not mint:
        pytest.skip(
            "Set SURFPOOL_GRADUATED_MINT=<mint_address> to a graduated token "
            "with a PumpSwap pool on mainnet"
        )
    return mint
