"""Surfpool integration: RPC client basics against local fork."""

import pytest

from pumpfun_cli.protocol.client import RpcClient
from pumpfun_cli.protocol.contracts import PUMP_GLOBAL


@pytest.mark.asyncio
async def test_get_blockhash(surfpool_rpc):
    """Surfpool returns a valid blockhash."""
    client = RpcClient(surfpool_rpc)
    try:
        blockhash = await client.get_blockhash()
        assert blockhash is not None
        assert len(bytes(blockhash)) == 32
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_balance(surfpool_rpc, funded_keypair):
    """Funded keypair has SOL balance on surfpool."""
    client = RpcClient(surfpool_rpc)
    try:
        balance = await client.get_balance(funded_keypair.pubkey())
        assert balance > 0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_account_info_pump_global(surfpool_rpc):
    """Surfpool lazily fetches the pump.fun global account from mainnet."""
    client = RpcClient(surfpool_rpc)
    try:
        resp = await client.get_account_info(PUMP_GLOBAL)
        assert resp.value is not None, "Surfpool should fetch PUMP_GLOBAL from mainnet"
        assert len(resp.value.data) > 0
    finally:
        await client.close()
