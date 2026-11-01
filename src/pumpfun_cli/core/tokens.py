"""Token discovery through pump.fun's frontend API, optionally enriched from chain.

The API ranks and lists coins but no longer returns curve reserves, so price
and bonding progress come from the bonding curves themselves when an RPC
endpoint is available. Lists are narrowed to pump.fun coins on Solana, the only
ones this CLI can trade; pump.fun's boards also carry other launchpads and chains.
"""

import httpx
from solana.exceptions import SolanaRpcException
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import derive_bonding_curve
from pumpfun_cli.protocol.client import RpcClient
from pumpfun_cli.protocol.contracts import HTTP_HEADERS
from pumpfun_cli.protocol.curve import get_bonding_progress, get_token_price, parse_bonding_curve
from pumpfun_cli.protocol.quote import (
    fetch_global,
    get_mint_info,
    normalize_quote_mint,
    quote_symbol,
)

PUMP_API = "https://frontend-api-v3.pump.fun"
SOLANA_CHAIN_ID = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
PUMP_PROGRAM_LABEL = "pump"

# Board pages hold up to 150 rows and the offset stops at 149.
_BOARD_PAGE = 150
_BOARD_MAX_OFFSET = 149
_RECOMMENDATIONS_MAX = 10
_SEARCH_MAX = 100
_MULTIPLE_ACCOUNTS_MAX = 100


class TokenApiError(RuntimeError):
    """pump.fun's API refused or failed a listing request."""


async def _get(path: str, params: dict) -> object:
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=HTTP_HEADERS) as client:
            resp = await client.get(f"{PUMP_API}{path}", params=params)
    except httpx.HTTPError as exc:
        raise TokenApiError(f"pump.fun API request failed ({type(exc).__name__})") from None
    if resp.status_code != 200:
        raise TokenApiError(
            f"pump.fun API returned HTTP {resp.status_code} for {path}{_reason(resp)}"
        )
    try:
        return resp.json()
    except ValueError:
        raise TokenApiError(f"pump.fun API returned a non-JSON response for {path}") from None


def _reason(resp: httpx.Response) -> str:
    """pump.fun's own error message, when the body is its JSON error; an HTML page says nothing."""
    try:
        message = resp.json().get("message")
    except (ValueError, AttributeError):
        return ""
    if isinstance(message, list):
        message = "; ".join(str(m) for m in message)
    return f": {str(message)[:200]}" if message else ""


def _is_pump_coin(row: object) -> bool:
    if not isinstance(row, dict) or not isinstance(row.get("mint"), str):
        return False
    if row.get("chain_id") != SOLANA_CHAIN_ID or row.get("program") != PUMP_PROGRAM_LABEL:
        return False
    # A row whose mint or quote asset is not a pubkey cannot be priced or traded.
    try:
        Pubkey.from_string(row["mint"])
        if row.get("quote_mint") is not None:
            Pubkey.from_string(row["quote_mint"])
    except (ValueError, TypeError):
        return False
    return True


def _summarize(row: dict) -> dict:
    """The fields a caller acts on, in one shape whichever endpoint served the row."""
    raw_quote = row.get("quote_mint")
    quote_mint = normalize_quote_mint(Pubkey.from_string(raw_quote) if raw_quote else None)
    return {
        "mint": row.get("mint"),
        "name": row.get("name"),
        "symbol": row.get("symbol"),
        "quote_mint": str(quote_mint),
        "quote_symbol": quote_symbol(quote_mint),
        "usd_market_cap": row.get("usd_market_cap"),
        "complete": bool(row.get("complete")),
        "created_timestamp": row.get("created_timestamp"),
        "last_trade_timestamp": row.get("last_trade_timestamp"),
        "is_mayhem_mode": bool(row.get("mayhem")),
        "is_cashback_coin": bool(row.get("is_cashback_enabled")),
        "is_holder_reward": bool(row.get("is_holder_reward")),
    }


def _pump_coins(rows: object, limit: int, path: str) -> list[dict]:
    if not isinstance(rows, list):
        raise TokenApiError(f"pump.fun API returned an unexpected shape for {path}")
    return [_summarize(r) for r in rows if _is_pump_coin(r)][:limit]


async def _board(board: str, limit: int) -> list[dict]:
    """A pump.fun board, narrowed to pump.fun coins, paging until `limit` are found.

    The API caps the offset at 149, so a board holds at most 299 rows and the
    second page overlaps the first by one; rows are deduplicated by mint.
    """
    found: dict[str, dict] = {}
    offset = 0
    while len(found) < limit:
        page = await _get(f"/coins/boards/{board}", {"limit": _BOARD_PAGE, "offset": offset})
        rows = page.get("coins") if isinstance(page, dict) else None
        if not isinstance(rows, list):
            raise TokenApiError(f"pump.fun API returned an unexpected shape for board {board}")
        for row in rows:
            if _is_pump_coin(row):
                found.setdefault(row.get("mint"), row)
        if len(rows) < _BOARD_PAGE or offset >= _BOARD_MAX_OFFSET:
            break
        offset = min(offset + len(rows), _BOARD_MAX_OFFSET)
    return [_summarize(r) for r in list(found.values())[:limit]]


async def get_trending_tokens(limit: int = 20) -> list[dict]:
    """pump.fun's "movers" board."""
    return await _board("movers", limit)


async def get_new_tokens(limit: int = 20) -> list[dict]:
    """Newest coins first."""
    return await _board("new", limit)


async def get_graduating_tokens(limit: int = 20) -> list[dict]:
    """Coins pump.fun ranks as closest to graduating."""
    return await _board("graduating", limit)


async def get_recommended_tokens(limit: int = 10) -> list[dict]:
    """pump.fun's own recommendations; it serves at most 10."""
    path = "/coins/recommendations"
    rows = await _get(path, {"surface": "search_entry", "limit": min(limit, _RECOMMENDATIONS_MAX)})
    return _pump_coins(rows, limit, path)


async def search_tokens(query: str, limit: int = 20) -> list[dict]:
    """Search pump.fun coins by name or ticker, older coins included."""
    path = "/coins/search-unrestricted"
    rows = await _get(path, {"searchTerm": query, "limit": _SEARCH_MAX})
    return _pump_coins(rows, limit, path)


async def enrich_from_chain(tokens: list[dict], rpc_url: str) -> list[dict]:
    """Add price (in each coin's quote asset) and bonding progress read from the curves.

    A coin whose curve cannot be read keeps the API's fields only.

    Raises:
        RuntimeError: If the RPC endpoint fails; the caller can still show the listing
    """
    if not tokens:
        return tokens
    try:
        return await _enrich(tokens, rpc_url)
    except SolanaRpcException as exc:
        # Rebuilt without the original message, which can carry the endpoint URL.
        raise RuntimeError(f"RPC request failed ({type(exc).__name__})") from None


async def _enrich(tokens: list[dict], rpc_url: str) -> list[dict]:
    client = RpcClient(rpc_url)
    try:
        global_state = await fetch_global(client)
        initial_real = global_state["initial_real_token_reserves"]
        curves = [derive_bonding_curve(Pubkey.from_string(t["mint"])) for t in tokens]
        accounts = []
        for i in range(0, len(curves), _MULTIPLE_ACCOUNTS_MAX):
            accounts += await client.get_multiple_accounts(curves[i : i + _MULTIPLE_ACCOUNTS_MAX])
        decimals: dict[Pubkey, int] = {}
        for token, account in zip(tokens, accounts, strict=True):
            if account is None:
                continue
            try:
                state = parse_bonding_curve(bytes(account.data))
            except ValueError:
                continue
            quote_mint = state["quote_mint"]
            if quote_mint not in decimals:
                try:
                    decimals[quote_mint] = (await get_mint_info(client, quote_mint))[1]
                except RuntimeError:
                    continue
            token["quote_mint"] = str(quote_mint)
            token["quote_symbol"] = quote_symbol(quote_mint)
            token["complete"] = state["complete"]
            token["bonding_progress"] = round(get_bonding_progress(state, initial_real) * 100, 1)
            token["price"] = (
                None if state["complete"] else get_token_price(state, decimals[quote_mint])
            )
        return tokens
    finally:
        await client.close()
