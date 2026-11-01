"""Human-readable output for the reshaped results, labelled by the coin's quote asset."""

from unittest.mock import AsyncMock, patch

import pytest
from solders.keypair import Keypair
from typer.testing import CliRunner

from pumpfun_cli.cli import app
from pumpfun_cli.crypto import encrypt_keypair

runner = CliRunner()
MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


@pytest.fixture
def wallet(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PUMPFUN_PASSWORD", "testpass")
    config_dir = tmp_path / "pumpfun-cli"
    config_dir.mkdir()
    encrypt_keypair(Keypair(), "testpass", config_dir / "wallet.enc")


def _human(module: str):
    return patch(f"pumpfun_cli.commands.{module}.render", return_value=False)


def test_buy_and_sell_name_the_quote_asset(wallet):
    with (
        _human("trade"),
        patch("pumpfun_cli.commands.trade.buy_token", new_callable=AsyncMock) as buy,
        patch("pumpfun_cli.commands.trade.sell_token", new_callable=AsyncMock) as sell,
    ):
        buy.return_value = {
            "action": "buy",
            "quote_symbol": "USDC",
            "quote_spent": 5.0,
            "tokens_received": 10.0,
            "explorer": "x",
        }
        sell.return_value = {
            "action": "sell",
            "quote_symbol": "USDC",
            "quote_received": 4.5,
            "tokens_sold": 10.0,
            "explorer": "x",
        }
        bought = runner.invoke(app, ["--rpc", "http://rpc", "buy", MINT, "5"])
        sold = runner.invoke(app, ["--rpc", "http://rpc", "sell", MINT, "all"])
    assert bought.exit_code == 0 and "for 5.0 USDC" in bought.output
    assert sold.exit_code == 0 and "4.500000 USDC" in sold.output


def test_dry_runs(wallet):
    common = {
        "dry_run": True,
        "venue": "bonding_curve",
        "quote_symbol": "SOL",
        "effective_price": 1e-8,
        "spot_price": 1e-8,
        "price_impact_pct": 0.5,
        "slippage_pct": 15,
    }
    with (
        _human("trade"),
        patch("pumpfun_cli.commands.trade.buy_token", new_callable=AsyncMock) as buy,
        patch("pumpfun_cli.commands.trade.sell_token", new_callable=AsyncMock) as sell,
    ):
        buy.return_value = {
            **common,
            "action": "buy",
            "quote_in": 0.01,
            "expected_tokens": 1.0,
            "min_tokens_out": 0.9,
        }
        sell.return_value = {
            **common,
            "action": "sell",
            "tokens_in": 1.0,
            "expected_quote": 0.01,
            "min_quote_out": 0.009,
        }
        b = runner.invoke(app, ["--rpc", "http://rpc", "buy", "--dry-run", MINT, "0.01"])
        s = runner.invoke(app, ["--rpc", "http://rpc", "sell", "--dry-run", MINT, "1"])
    assert b.exit_code == 0 and "0.01 SOL" in b.output
    assert s.exit_code == 0 and "SOL/token" in s.output


def test_collect_and_claim_forward_quote_mint(wallet):
    with (
        _human("trade"),
        patch(
            "pumpfun_cli.commands.trade.collect_creator_fees_core", new_callable=AsyncMock
        ) as col,
        patch("pumpfun_cli.commands.trade.claim_cashback_core", new_callable=AsyncMock) as claim,
    ):
        col.return_value = {
            "quote_symbol": "USDC",
            "pump_recovered": 1.0,
            "pumpswap_recovered": 0.0,
            "explorer": "x",
        }
        claim.return_value = {"action": "claim_cashback", "explorer": "x"}
        c = runner.invoke(
            app, ["--rpc", "http://rpc", "collect-creator-fee", "--quote-mint", MINT]
        )
        k = runner.invoke(app, ["--rpc", "http://rpc", "claim-cashback", "--quote-mint", MINT])
    assert c.exit_code == 0 and "1.000000 USDC" in c.output
    assert col.call_args.args[3] == MINT
    assert k.exit_code == 0 and claim.call_args.args[3] == MINT


def test_info(wallet):
    with (
        _human("info"),
        patch("pumpfun_cli.commands.info.get_token_info", new_callable=AsyncMock) as info,
    ):
        info.return_value = {
            "mint": MINT,
            "quote_symbol": "USDC",
            "price": 0.5,
            "bonding_progress": 10.0,
            "graduated": False,
            "real_quote_reserves": 3.0,
            "creator": "c",
            "is_mayhem_mode": False,
            "is_cashback_coin": False,
            "is_holder_reward": True,
            "creator_fee_bps": 300,
        }
        result = runner.invoke(app, ["--rpc", "http://rpc", "info", MINT])
    assert result.exit_code == 0
    assert "0.5000000000 USDC" in result.output
    assert "Holder rewards:   Yes" in result.output
    assert "300 bps" in result.output


def test_launch_forwards_options(wallet):
    with (
        _human("launch"),
        patch("pumpfun_cli.commands.launch.launch_token", new_callable=AsyncMock) as launch,
    ):
        launch.return_value = {
            "name": "N",
            "ticker": "T",
            "mint": MINT,
            "quote_symbol": "USDC",
            "explorer": "x",
            "pump_url": "y",
            "initial_buy": 2.0,
            "is_holder_reward": True,
            "creator_fee_bps": 100,
        }
        result = runner.invoke(
            app,
            [
                "--rpc",
                "http://rpc",
                "launch",
                "--name",
                "N",
                "--ticker",
                "T",
                "--desc",
                "d",
                "--buy",
                "2",
                "--quote-mint",
                MINT,
                "--creator-fee-bps",
                "100",
                "--holder-reward",
            ],
        )
    assert result.exit_code == 0, result.output
    kwargs = launch.call_args.kwargs
    assert kwargs["quote_mint_str"] == MINT
    assert kwargs["creator_fee_bps"] == 100
    assert kwargs["is_holder_reward"] is True
    assert kwargs["initial_buy"] == 2.0
    assert "Buy:      2.0 USDC" in result.output


def test_launch_rejects_negative_fee(wallet):
    result = runner.invoke(
        app,
        [
            "--rpc",
            "http://rpc",
            "launch",
            "--name",
            "N",
            "--ticker",
            "T",
            "--desc",
            "d",
            "--creator-fee-bps",
            "-1",
        ],
    )
    assert result.exit_code != 0
