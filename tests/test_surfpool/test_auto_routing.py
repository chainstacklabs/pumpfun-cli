"""Surfpool integration: auto-routing for graduated tokens.

These tests verify that buying/selling a graduated token WITHOUT --force-amm
automatically routes through PumpSwap. Requires a running surfpool instance
with a graduated token.

Run with: pytest tests/test_surfpool/ -v --surfpool
"""

import pytest
from typer.testing import CliRunner

from pumpfun_cli.cli import app
from pumpfun_cli.core.trade import buy_token, sell_token

# Surfpool needs time to lazy-fetch pool token accounts from mainnet.
SURFPOOL_TIMEOUT = 120.0

runner = CliRunner()


@pytest.mark.asyncio
async def test_buy_auto_route_graduated_token(
    surfpool_rpc, funded_keypair, test_keystore, test_password, graduated_mint
):
    """buy_token returns graduated, then buy_pumpswap succeeds."""
    # Step 1: buy_token should detect graduated
    result = await buy_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        sol_amount=0.001,
        slippage=25,
    )

    assert result.get("error") == "graduated", f"Expected graduated, got: {result}"

    # Step 2: pumpswap buy should succeed
    from pumpfun_cli.core.pumpswap import buy_pumpswap

    ps_result = await buy_pumpswap(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        sol_amount=0.001,
        slippage=50,
        rpc_timeout=SURFPOOL_TIMEOUT,
    )

    assert "error" not in ps_result, f"PumpSwap buy failed: {ps_result}"
    assert ps_result["venue"] == "pumpswap"
    assert ps_result["action"] == "buy"
    assert ps_result["tokens_received"] > 0


@pytest.mark.asyncio
async def test_sell_auto_route_graduated_token(
    surfpool_rpc, funded_keypair, test_keystore, test_password, graduated_mint
):
    """After buying, sell auto-routes through pumpswap."""
    from pumpfun_cli.core.pumpswap import buy_pumpswap

    # Buy some tokens first
    buy_result = await buy_pumpswap(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        sol_amount=0.001,
        slippage=50,
        rpc_timeout=SURFPOOL_TIMEOUT,
        confirm=True,
    )
    assert "error" not in buy_result, f"Buy failed: {buy_result}"

    # sell_token should detect graduated
    sell_result = await sell_token(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        amount_str="all",
        slippage=25,
    )

    assert sell_result.get("error") == "graduated", f"Expected graduated, got: {sell_result}"

    # sell_pumpswap should succeed
    from pumpfun_cli.core.pumpswap import sell_pumpswap

    ps_result = await sell_pumpswap(
        rpc_url=surfpool_rpc,
        keystore_path=str(test_keystore),
        password=test_password,
        mint_str=graduated_mint,
        amount_str="all",
        slippage=50,
        rpc_timeout=SURFPOOL_TIMEOUT,
    )

    assert "error" not in ps_result, f"PumpSwap sell failed: {ps_result}"
    assert ps_result["venue"] == "pumpswap"
    assert ps_result["action"] == "sell"


def test_buy_auto_route_full_command_layer(
    surfpool_rpc, funded_keypair, test_keystore, test_password, graduated_mint, tmp_path
):
    """CliRunner buy without --force-amm shows venue=pumpswap."""
    import json
    import os

    # Set up env for CLI
    env = {
        "PUMPFUN_RPC": surfpool_rpc,
        "PUMPFUN_PASSWORD": test_password,
        "XDG_CONFIG_HOME": str(test_keystore.parent.parent),
    }
    for key, val in env.items():
        os.environ[key] = val

    try:
        # Rename the keystore dir to match what the CLI expects
        import shutil

        cli_config_dir = test_keystore.parent.parent / "pumpfun-cli"
        if not cli_config_dir.exists():
            cli_config_dir.mkdir()
        cli_wallet = cli_config_dir / "wallet.enc"
        if not cli_wallet.exists():
            shutil.copy2(str(test_keystore), str(cli_wallet))

        result = runner.invoke(
            app,
            [
                "--json",
                "--rpc",
                surfpool_rpc,
                "buy",
                graduated_mint,
                "0.001",
                "--slippage",
                "50",
            ],
        )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        data = json.loads(result.output)
        assert data["venue"] == "pumpswap"
    finally:
        for key in env:
            os.environ.pop(key, None)
