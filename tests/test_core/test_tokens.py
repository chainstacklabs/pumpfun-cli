"""Token discovery: the endpoints used, the pump.fun-only filter, and chain enrichment."""

from unittest.mock import patch

import httpx
import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.core.tokens import (
    PUMP_API,
    SOLANA_CHAIN_ID,
    TokenApiError,
    enrich_from_chain,
    get_graduating_tokens,
    get_new_tokens,
    get_recommended_tokens,
    get_trending_tokens,
    search_tokens,
)
from pumpfun_cli.protocol.address import derive_bonding_curve
from pumpfun_cli.protocol.contracts import USDC_MINT
from tests.test_core.helpers import FakeClient, build_curve_data, build_global_data

PUMP_GLOBAL_DATA = build_global_data()


def _row(
    symbol: str,
    *,
    program: str | None = "pump",
    chain: str = SOLANA_CHAIN_ID,
    quote: str | None = None,
    mint: str | None = None,
) -> dict:
    return {
        "mint": mint or str(Pubkey.new_unique()),
        "name": symbol.title(),
        "symbol": symbol,
        "chain_id": chain,
        "program": program,
        "quote_mint": quote,
        "usd_market_cap": 1234.5,
        "complete": False,
        "created_timestamp": 1,
        "last_trade_timestamp": 2,
        "mayhem": None,
        "is_cashback_enabled": False,
        "is_holder_reward": True,
    }


OTHER_LAUNCHPAD = _row("MDBC", program="meteora_dbc")
EVM = _row("EVM", program=None, chain="eip155:56")


@pytest.mark.parametrize(
    "fn,board",
    [
        (get_trending_tokens, "movers"),
        (get_new_tokens, "new"),
        (get_graduating_tokens, "graduating"),
    ],
)
async def test_boards_keep_only_pump_coins(respx_mock, fn, board):
    route = respx_mock.get(f"{PUMP_API}/coins/boards/{board}").mock(
        return_value=httpx.Response(
            200, json={"coins": [OTHER_LAUNCHPAD, _row("ONE"), EVM, _row("TWO")]}
        )
    )
    tokens = await fn(limit=5)
    assert [t["symbol"] for t in tokens] == ["ONE", "TWO"]
    assert route.call_count == 1  # a short page is the end of the board
    assert route.calls.last.request.headers["user-agent"].startswith("pumpfun-cli")


async def test_board_pages_until_the_limit(respx_mock):
    edge = str(Pubkey.new_unique())
    first = [_row(f"A{i}") for i in range(3)] + [EVM] * 146 + [_row("EDGE", mint=edge)]
    second = [_row("EDGE", mint=edge)] + [_row(f"B{i}") for i in range(5)]
    route = respx_mock.get(f"{PUMP_API}/coins/boards/new").mock(
        side_effect=[
            httpx.Response(200, json={"coins": first}),
            httpx.Response(200, json={"coins": second}),
        ]
    )
    tokens = await get_new_tokens(limit=6)
    assert [t["symbol"] for t in tokens] == ["A0", "A1", "A2", "EDGE", "B0", "B1"]
    assert route.calls[1].request.url.params["offset"] == "149"
    assert route.call_count == 2


async def test_board_stops_on_an_empty_page(respx_mock):
    respx_mock.get(f"{PUMP_API}/coins/boards/graduating").mock(
        return_value=httpx.Response(200, json={"coins": []})
    )
    assert await get_graduating_tokens(limit=5) == []


async def test_recommendations_are_capped_at_ten(respx_mock):
    route = respx_mock.get(f"{PUMP_API}/coins/recommendations").mock(
        return_value=httpx.Response(200, json=[_row("REC")])
    )
    await get_recommended_tokens(limit=50)
    params = route.calls.last.request.url.params
    assert params["surface"] == "search_entry" and params["limit"] == "10"


async def test_search_is_server_side(respx_mock):
    route = respx_mock.get(f"{PUMP_API}/coins/search-unrestricted").mock(
        return_value=httpx.Response(200, json=[EVM, _row("PEPE"), OTHER_LAUNCHPAD])
    )
    tokens = await search_tokens("pepe", limit=5)
    assert [t["symbol"] for t in tokens] == ["PEPE"]
    assert route.calls.last.request.url.params["searchTerm"] == "pepe"


async def test_summary_names_the_quote_asset(respx_mock):
    respx_mock.get(f"{PUMP_API}/coins/boards/new").mock(
        return_value=httpx.Response(
            200,
            json={
                "coins": [
                    _row("SOLCOIN", quote="11111111111111111111111111111111"),
                    _row("OLD", quote=None),
                    _row("USD", quote=str(USDC_MINT)),
                ]
            },
        )
    )
    tokens = await get_new_tokens(limit=3)
    assert [t["quote_symbol"] for t in tokens] == ["SOL", "SOL", "USDC"]
    assert tokens[0]["is_holder_reward"] is True
    assert set(tokens[0]) >= {"mint", "name", "symbol", "usd_market_cap", "complete"}


@pytest.mark.parametrize(
    "response",
    [httpx.Response(404, json={"message": "gone"}), httpx.Response(403, text="cf")],
)
async def test_api_failures_raise_a_clean_error(respx_mock, response):
    respx_mock.get(f"{PUMP_API}/coins/boards/movers").mock(return_value=response)
    with pytest.raises(TokenApiError, match=str(response.status_code)):
        await get_trending_tokens()


async def test_transport_failure_raises_a_clean_error(respx_mock):
    respx_mock.get(f"{PUMP_API}/coins/boards/movers").mock(side_effect=httpx.ConnectTimeout("x"))
    with pytest.raises(TokenApiError, match="ConnectTimeout"):
        await get_trending_tokens()


async def test_enrich_reads_price_and_progress_from_the_curves():
    from pumpfun_cli.protocol.contracts import PUMP_GLOBAL

    sol_coin, usdc_coin, missing, done = (Pubkey.new_unique() for _ in range(4))
    client = FakeClient()
    client.add(PUMP_GLOBAL, PUMP_GLOBAL_DATA)
    client.add(derive_bonding_curve(sol_coin), build_curve_data(real_token=693_100_000_000_000))
    client.add(
        derive_bonding_curve(usdc_coin),
        build_curve_data(quote_mint=USDC_MINT, virtual_quote=5_000_000_000),
    )
    client.add(derive_bonding_curve(done), build_curve_data(complete=True, length=49))
    tokens = [
        {"mint": str(m), "quote_symbol": "SOL"} for m in (sol_coin, usdc_coin, missing, done)
    ]
    with patch("pumpfun_cli.core.tokens.RpcClient", return_value=client):
        enriched = await enrich_from_chain(tokens, "http://rpc")
    sol, usdc, gone, graduated = enriched
    assert sol["price"] == pytest.approx(3e-8)
    assert sol["bonding_progress"] == pytest.approx(12.6, abs=0.1)
    assert usdc["quote_symbol"] == "USDC" and usdc["price"] == pytest.approx(5e-6)
    assert "price" not in gone
    assert graduated["price"] is None and graduated["bonding_progress"] == 100.0


async def test_error_carries_pump_funs_own_message(respx_mock):
    respx_mock.get(f"{PUMP_API}/coins/boards/movers").mock(
        return_value=httpx.Response(400, json={"message": ["board must be one of: new"]})
    )
    with pytest.raises(TokenApiError, match="400.*board must be one of: new"):
        await get_trending_tokens()


async def test_html_error_page_adds_nothing(respx_mock):
    respx_mock.get(f"{PUMP_API}/coins/boards/movers").mock(
        return_value=httpx.Response(403, text="<!DOCTYPE html><html>challenge</html>")
    )
    with pytest.raises(TokenApiError) as info:
        await get_trending_tokens()
    assert "DOCTYPE" not in str(info.value)


async def test_non_json_success_is_a_clean_error(respx_mock):
    respx_mock.get(f"{PUMP_API}/coins/search-unrestricted").mock(
        return_value=httpx.Response(200, text="<html>challenge</html>")
    )
    with pytest.raises(TokenApiError, match="non-JSON"):
        await search_tokens("pepe")


@pytest.mark.parametrize("body", [{"coins": "nope"}, {"other": []}, ["not", "a", "board"]])
async def test_unexpected_board_shape_is_a_clean_error(respx_mock, body):
    respx_mock.get(f"{PUMP_API}/coins/boards/new").mock(
        return_value=httpx.Response(200, json=body)
    )
    with pytest.raises(TokenApiError, match="unexpected shape"):
        await get_new_tokens()


async def test_unexpected_search_shape_is_a_clean_error(respx_mock):
    respx_mock.get(f"{PUMP_API}/coins/recommendations").mock(
        return_value=httpx.Response(200, json={"coins": []})
    )
    with pytest.raises(TokenApiError, match="unexpected shape"):
        await get_recommended_tokens()


async def test_malformed_rows_are_skipped_not_fatal(respx_mock):
    respx_mock.get(f"{PUMP_API}/coins/search-unrestricted").mock(
        return_value=httpx.Response(
            200,
            json=[
                "a string",
                _row("BADQUOTE", quote="not-a-pubkey"),
                _row("BADMINT", mint="nope"),
                _row("GOOD"),
            ],
        )
    )
    assert [t["symbol"] for t in await search_tokens("x")] == ["GOOD"]


async def test_rpc_failure_during_enrichment_is_a_runtime_error_without_the_url():
    from unittest.mock import AsyncMock

    from solana.exceptions import SolanaRpcException

    client = FakeClient()
    client.get_account_info = AsyncMock(
        side_effect=SolanaRpcException(
            TimeoutError("https://rpc.test/secret-api-key timed out"), lambda: None, None, object()
        )
    )
    with (
        patch("pumpfun_cli.core.tokens.RpcClient", return_value=client),
        pytest.raises(RuntimeError) as info,
    ):
        await enrich_from_chain([{"mint": str(Pubkey.new_unique())}], "https://rpc.test")
    assert "secret-api-key" not in str(info.value)
