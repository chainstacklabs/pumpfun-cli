"""Surfpool integration: buy and sell forked LaunchLab coins that trade on Raydium CPMM.

Set SURFPOOL_CPMM_MINT to a LaunchLab coin migrated to CPMM and priced in SOL.
The trade goes through the command's routing: the LaunchLab curve reports it
graduated and the CPMM pool takes the trade.
"""

import json
import os

import pytest
from typer.testing import CliRunner

from pumpfun_cli.cli import app
from pumpfun_cli.core.info import get_token_info

runner = CliRunner()


def _mint() -> str:
    mint = os.environ.get("SURFPOOL_CPMM_MINT")
    if not mint:
        pytest.skip("Set SURFPOOL_CPMM_MINT to a LaunchLab coin migrated to CPMM")
    return mint


def _cli(surfpool_rpc, keystore, password, monkeypatch, *args) -> dict:
    monkeypatch.setenv("PUMPFUN_PASSWORD", password)
    out = runner.invoke(app, ["--json", "--rpc", surfpool_rpc, "--keyfile", str(keystore), *args])
    assert out.exit_code == 0, out.output
    return json.loads(out.output)


@pytest.mark.asyncio
async def test_info_shows_the_cpmm_pool(surfpool_rpc):
    info = await get_token_info(surfpool_rpc, _mint())
    assert info["venue"] == "cpmm" and info["graduated"] is True, info
    assert info["quote_reserves"] > 0


def test_buy_and_sell_route_to_cpmm(
    surfpool_rpc, funded_keypair, test_keystore, test_password, monkeypatch
):
    mint = _mint()
    bought = _cli(
        surfpool_rpc, test_keystore, test_password, monkeypatch, "buy", mint, "0.01", "--confirm"
    )
    assert bought["venue"] == "cpmm" and bought["tokens_received_raw"] > 0
    sold = _cli(
        surfpool_rpc, test_keystore, test_password, monkeypatch, "sell", mint, "all", "--confirm"
    )
    assert sold["venue"] == "cpmm"
    assert sold["tokens_sold_raw"] == bought["tokens_received_raw"]


def test_force_amm_trades_a_launchlab_coin_on_cpmm(
    surfpool_rpc, funded_keypair, test_keystore, test_password, monkeypatch
):
    mint = _mint()
    bought = _cli(
        surfpool_rpc,
        test_keystore,
        test_password,
        monkeypatch,
        "buy",
        "--force-amm",
        mint,
        "0.01",
        "--confirm",
    )
    assert bought["venue"] == "cpmm"
    sold = _cli(
        surfpool_rpc,
        test_keystore,
        test_password,
        monkeypatch,
        "sell",
        "--force-amm",
        mint,
        "all",
        "--confirm",
    )
    assert sold["venue"] == "cpmm"
