import httpx
import pytest
import respx

from pumpfun_cli.core.tokens import (
    get_graduating_tokens,
    get_recommended_tokens,
    get_trending_tokens,
    search_tokens,
)

PUMP_API = "https://frontend-api-v3.pump.fun"

MOCK_RECOMMENDED = [
    {
        "name": "TestToken",
        "symbol": "TEST",
        "mint": "abc123",
        "usd_market_cap": 100000,
        "created_timestamp": 1000,
        "complete": False,
        "real_sol_reserves": 50_000_000_000,
        "virtual_sol_reserves": 30_000_000_000,
        "virtual_token_reserves": 1_000_000_000_000,
        "description": "A test token",
    },
    {
        "name": "Another",
        "symbol": "ANO",
        "mint": "def456",
        "usd_market_cap": 50000,
        "created_timestamp": 2000,
        "complete": False,
        "real_sol_reserves": 10_000_000_000,
        "virtual_sol_reserves": 10_000_000_000,
        "virtual_token_reserves": 500_000_000_000,
        "description": "Another token",
    },
]


@pytest.mark.asyncio
@respx.mock
async def test_get_recommended():
    respx.get(f"{PUMP_API}/coins/recommended").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMENDED)
    )
    tokens = await get_recommended_tokens(limit=10)
    assert len(tokens) == 2
    assert tokens[0]["symbol"] == "TEST"
    assert "price_sol" in tokens[0]
    assert "bonding_progress" in tokens[0]


@pytest.mark.asyncio
@respx.mock
async def test_search_filters_by_name():
    respx.get(f"{PUMP_API}/coins/recommended").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMENDED)
    )
    results = await search_tokens("test", limit=10)
    assert len(results) == 1
    assert results[0]["name"] == "TestToken"


@pytest.mark.asyncio
@respx.mock
async def test_enriched_tokens_have_price_and_progress():
    """Tokens with reserve fields should have price_sol (float > 0) and bonding_progress (0-100)."""
    respx.get(f"{PUMP_API}/coins/recommended").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMENDED)
    )
    tokens = await get_recommended_tokens(limit=10)
    for t in tokens:
        assert isinstance(t["price_sol"], float)
        assert t["price_sol"] > 0
        assert isinstance(t["bonding_progress"], float)
        assert 0 <= t["bonding_progress"] <= 100


@pytest.mark.asyncio
@respx.mock
async def test_enriched_tokens_missing_reserves_fields():
    """Tokens missing reserve fields should have price_sol and bonding_progress as None."""
    bare_token = [
        {
            "name": "Bare",
            "symbol": "BARE",
            "mint": "bare111",
            "complete": False,
            "description": "no reserves",
        }
    ]
    respx.get(f"{PUMP_API}/coins/recommended").mock(
        return_value=httpx.Response(200, json=bare_token)
    )
    tokens = await get_recommended_tokens(limit=10)
    assert tokens[0]["price_sol"] is None
    assert tokens[0]["bonding_progress"] is None


@pytest.mark.asyncio
@respx.mock
async def test_enriched_tokens_zero_token_reserves():
    """Token with virtual_token_reserves: 0 should have price_sol == 0.0."""
    zero_token = [
        {
            "name": "Zero",
            "symbol": "ZERO",
            "mint": "zero111",
            "complete": False,
            "virtual_sol_reserves": 10_000_000_000,
            "virtual_token_reserves": 0,
            "real_sol_reserves": 5_000_000_000,
            "description": "zero reserves",
        }
    ]
    respx.get(f"{PUMP_API}/coins/recommended").mock(
        return_value=httpx.Response(200, json=zero_token)
    )
    tokens = await get_recommended_tokens(limit=10)
    assert tokens[0]["price_sol"] == 0.0
    assert isinstance(tokens[0]["bonding_progress"], float)


@pytest.mark.asyncio
@respx.mock
async def test_graduating_filters_pump_swap_pool():
    """Tokens with pump_swap_pool set should be excluded from graduating list."""
    tokens_data = [
        {
            "name": "Normal",
            "symbol": "NRM",
            "mint": "nrm111",
            "complete": False,
            "real_sol_reserves": 50_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "virtual_token_reserves": 1_000_000_000_000,
        },
        {
            "name": "Swapped",
            "symbol": "SWP",
            "mint": "swp111",
            "complete": False,
            "real_sol_reserves": 70_000_000_000,
            "virtual_sol_reserves": 40_000_000_000,
            "virtual_token_reserves": 800_000_000_000,
            "pump_swap_pool": "somePoolAddress",
        },
        {
            "name": "Completed",
            "symbol": "CMP",
            "mint": "cmp111",
            "complete": True,
            "real_sol_reserves": 85_000_000_000,
            "virtual_sol_reserves": 50_000_000_000,
            "virtual_token_reserves": 500_000_000_000,
        },
    ]
    respx.get(f"{PUMP_API}/coins/recommended").mock(
        return_value=httpx.Response(200, json=tokens_data)
    )
    result = await get_graduating_tokens(limit=20)
    assert len(result) == 1
    assert result[0]["symbol"] == "NRM"


@pytest.mark.asyncio
@respx.mock
async def test_graduating_keeps_tokens_without_pool():
    """Tokens without pump_swap_pool and complete=False should all be included."""
    tokens_data = [
        {
            "name": "A",
            "symbol": "AAA",
            "mint": "aaa111",
            "complete": False,
            "real_sol_reserves": 50_000_000_000,
            "virtual_sol_reserves": 30_000_000_000,
            "virtual_token_reserves": 1_000_000_000_000,
        },
        {
            "name": "B",
            "symbol": "BBB",
            "mint": "bbb111",
            "complete": False,
            "real_sol_reserves": 40_000_000_000,
            "virtual_sol_reserves": 20_000_000_000,
            "virtual_token_reserves": 900_000_000_000,
        },
    ]
    respx.get(f"{PUMP_API}/coins/recommended").mock(
        return_value=httpx.Response(200, json=tokens_data)
    )
    result = await get_graduating_tokens(limit=20)
    assert len(result) == 2


@pytest.mark.asyncio
@respx.mock
async def test_trending_tokens_enriched():
    """Trending results should include price_sol and bonding_progress."""
    runners = [{"coin": MOCK_RECOMMENDED[0]}]
    respx.get(f"{PUMP_API}/coins/top-runners").mock(return_value=httpx.Response(200, json=runners))
    respx.get(f"{PUMP_API}/coins/recommended").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMENDED)
    )
    tokens = await get_trending_tokens(limit=5)
    for t in tokens:
        assert "price_sol" in t
        assert "bonding_progress" in t


@pytest.mark.asyncio
@respx.mock
async def test_search_tokens_enriched():
    """Search results should include price_sol and bonding_progress."""
    respx.get(f"{PUMP_API}/coins/recommended").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMENDED)
    )
    results = await search_tokens("test", limit=10)
    assert len(results) == 1
    assert "price_sol" in results[0]
    assert "bonding_progress" in results[0]
