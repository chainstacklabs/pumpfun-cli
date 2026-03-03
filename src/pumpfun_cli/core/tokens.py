"""Fetch pump.fun token data via v3 frontend API."""

import httpx

from pumpfun_cli.protocol.curve import get_bonding_progress, get_token_price_sol

PUMP_API = "https://frontend-api-v3.pump.fun"


def _enrich_tokens(tokens: list[dict]) -> list[dict]:
    """Add price_sol and bonding_progress to each token dict."""
    for t in tokens:
        try:
            t["price_sol"] = get_token_price_sol(t)
        except KeyError:
            t["price_sol"] = None
        try:
            t["bonding_progress"] = round(get_bonding_progress(t) * 100, 1)
        except KeyError:
            t["bonding_progress"] = None
    return tokens


async def get_trending_tokens(limit: int = 20) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{PUMP_API}/coins/top-runners")
        resp.raise_for_status()
        runners = resp.json()
    tokens = [item["coin"] for item in runners if "coin" in item]
    if len(tokens) >= limit:
        return _enrich_tokens(tokens[:limit])
    recommended = await get_recommended_tokens(limit=limit - len(tokens))
    seen = {t["mint"] for t in tokens}
    for t in recommended:
        if t["mint"] not in seen:
            tokens.append(t)
            seen.add(t["mint"])
        if len(tokens) >= limit:
            break
    return _enrich_tokens(tokens[:limit])


async def get_recommended_tokens(limit: int = 50) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{PUMP_API}/coins/recommended",
            params={"limit": min(limit, 300), "includeNsfw": "false"},
        )
        resp.raise_for_status()
        return _enrich_tokens(resp.json())


async def get_new_tokens(limit: int = 20) -> list[dict]:
    tokens = await get_recommended_tokens(limit=300)
    tokens.sort(key=lambda t: t.get("created_timestamp", 0), reverse=True)
    return tokens[:limit]


async def get_graduating_tokens(limit: int = 20) -> list[dict]:
    tokens = await get_recommended_tokens(limit=300)
    bonding = [t for t in tokens if not t.get("complete", True) and not t.get("pump_swap_pool")]
    bonding.sort(key=lambda t: t.get("real_sol_reserves", 0), reverse=True)
    return bonding[:limit]


async def search_tokens(query: str, limit: int = 20) -> list[dict]:
    tokens = await get_recommended_tokens(limit=300)
    q = query.lower()
    return [
        t
        for t in tokens
        if q in (t.get("name") or "").lower()
        or q in (t.get("symbol") or "").lower()
        or q in (t.get("description") or "").lower()
    ][:limit]
