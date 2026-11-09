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


def test_a_capped_sell_says_what_it_kept(wallet):
    with (
        _human("trade"),
        patch("pumpfun_cli.commands.trade.sell_token", new_callable=AsyncMock) as sell,
    ):
        sell.return_value = {
            "action": "sell",
            "quote_symbol": "SOL",
            "quote_received": 0.001,
            "tokens_sold": 6.0,
            "tokens_kept": 4.0,
            "explorer": "x",
        }
        sold = runner.invoke(app, ["--rpc", "http://rpc", "sell", MINT, "all"])
    assert sold.exit_code == 0 and "Kept 4.00 tokens" in sold.output


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


@pytest.mark.parametrize("amount", ["0", "-1"])
def test_buy_rejects_non_positive_amount(wallet, amount):
    with patch("pumpfun_cli.commands.trade.buy_token", new_callable=AsyncMock) as buy:
        result = runner.invoke(app, ["--rpc", "http://rpc", "buy", MINT, "--", amount])
    assert result.exit_code == 2
    buy.assert_not_called()


def test_launch_rejects_negative_buy(wallet):
    with patch("pumpfun_cli.commands.launch.launch_token", new_callable=AsyncMock) as launch:
        result = runner.invoke(
            app, ["--rpc", "http://rpc", "launch", "--name", "N", "--ticker", "T", "--buy", "-1"]
        )
    assert result.exit_code != 0
    launch.assert_not_called()


@pytest.mark.parametrize(
    ("name", "ticker", "message"),
    [
        ("", "T", "Token name cannot be empty."),
        ("   ", "T", "Token name cannot be empty."),
        ("N", "", "Token ticker cannot be empty."),
        ("N", "  ", "Token ticker cannot be empty."),
    ],
)
def test_launch_rejects_blank_name_or_ticker(wallet, name, ticker, message):
    with patch("pumpfun_cli.commands.launch.launch_token", new_callable=AsyncMock) as launch:
        result = runner.invoke(
            app,
            ["--rpc", "http://rpc", "launch", "--name", name, "--ticker", ticker, "--uri", "u"],
        )
    assert result.exit_code == 2
    assert message in result.output
    launch.assert_not_called()


def test_launch_with_uri_needs_no_desc(wallet):
    with patch("pumpfun_cli.commands.launch.launch_token", new_callable=AsyncMock) as launch:
        launch.return_value = {"error": "stop", "message": "stop"}
        runner.invoke(
            app, ["--rpc", "http://rpc", "launch", "--name", "N", "--ticker", "T", "--uri", "u"]
        )
    launch.assert_called_once()


def test_tokens_table_names_quote_and_survives_missing_chain_data():
    rows = [
        {
            "name": "A",
            "symbol": "A",
            "mint": "m1",
            "quote_symbol": "SOL",
            "price": 3.2e-7,
            "bonding_progress": 96.2,
            "usd_market_cap": 31_800,
        },
        {
            "name": "B",
            "symbol": "B",
            "mint": "m2",
            "quote_symbol": "6FhVPctYg363pQbs4iSv",
            "price": 0.0093,
            "bonding_progress": 96.3,
            "usd_market_cap": 1_200_000,
        },
        {"name": "C", "symbol": "C", "mint": "m3", "quote_symbol": "SOL", "usd_market_cap": None},
    ]
    with (
        _human("tokens"),
        patch(
            "pumpfun_cli.commands.tokens.get_graduating_tokens", new_callable=AsyncMock
        ) as fetch,
        patch("pumpfun_cli.commands.tokens.render_table") as table,
    ):
        fetch.return_value = rows
        result = runner.invoke(app, ["tokens", "graduating"])
    assert result.exit_code == 0, result.output
    shown = table.call_args.args[0]
    assert [t["_price"] for t in shown] == ["3.2e-07 SOL", "0.0093 6FhV…", "—"]
    assert [t["_mcap"] for t in shown] == ["$31.8K", "$1.2M", ""]


def test_tokens_api_failure_is_a_clean_error():
    from pumpfun_cli.core.tokens import TokenApiError

    with patch(
        "pumpfun_cli.commands.tokens.get_new_tokens",
        new=AsyncMock(side_effect=TokenApiError("pump.fun API returned HTTP 404 for /x")),
    ):
        result = runner.invoke(app, ["tokens", "new"])
    assert result.exit_code == 1
    assert "404" in result.output


def test_tokens_listing_survives_an_rpc_failure(monkeypatch):
    monkeypatch.setenv("PUMPFUN_RPC", "http://rpc.test")
    rows = [{"name": "A", "symbol": "A", "mint": "m1", "quote_symbol": "SOL", "usd_market_cap": 1}]
    with (
        _human("tokens"),
        patch("pumpfun_cli.commands.tokens.get_new_tokens", new_callable=AsyncMock) as fetch,
        patch(
            "pumpfun_cli.commands.tokens.enrich_from_chain",
            new=AsyncMock(side_effect=RuntimeError("RPC request failed")),
        ),
        patch("pumpfun_cli.commands.tokens.render_table") as table,
    ):
        fetch.return_value = rows
        result = runner.invoke(app, ["tokens", "new"])
    assert result.exit_code == 0
    assert table.called
    assert "Could not read prices from chain" in result.output


@pytest.mark.parametrize("graduated", [False, True])
def test_info_for_a_launchlab_coin(wallet, graduated):
    info = {
        "mint": MINT,
        "venue": "launchlab",
        "platform": "StonkFun",
        "quote_mint": MINT,
        "quote_symbol": "USDC",
        "launchlab_pool": "pool",
        "price": 0.001,
        "bonding_progress": 40.0,
        "graduated": graduated,
        "real_quote_reserves": 12.5,
        "creator": "c",
        "curve_fee_pct": 1.25,
        "transfer_fee_bps": 100,
    }
    if graduated:
        # A pool address without its reserves, as when the pool lookup failed.
        info.update(migrate_type="cpmm", pool_address="cpmm-pool")
    with (
        _human("info"),
        patch("pumpfun_cli.commands.info.get_token_info", new_callable=AsyncMock) as get,
    ):
        get.return_value = info
        shown = runner.invoke(app, ["--rpc", "http://rpc", "info", MINT])
    assert shown.exit_code == 0, shown.output
    assert "StonkFun (Raydium LaunchLab)" in shown.output
    assert "Transfer fee:     100 bps" in shown.output
