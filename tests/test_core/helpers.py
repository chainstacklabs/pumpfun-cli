"""Shared test helpers: real account layouts and an in-memory RPC client."""

import struct
from types import SimpleNamespace

from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import (
    derive_amm_pool,
    derive_bonding_curve,
    find_quote_control,
)
from pumpfun_cli.protocol.contracts import (
    BONDING_CURVE_DISCRIMINATOR,
    DEFAULT_PUBKEY,
    GLOBAL_CONFIG_DISCRIMINATOR,
    GLOBALCONFIG_BUYBACK_FEE_RECIPIENTS_OFFSET,
    GLOBALCONFIG_COIN_CREATOR_FEE_BPS_OFFSET,
    GLOBALCONFIG_LP_FEE_BPS_OFFSET,
    GLOBALCONFIG_PROTOCOL_FEE_BPS_OFFSET,
    GLOBALCONFIG_PROTOCOL_FEE_RECIPIENTS_OFFSET,
    GLOBALCONFIG_RESERVED_FEE_RECIPIENT_OFFSET,
    POOL_DISCRIMINATOR,
    PUMP_GLOBAL,
    PUMP_SWAP_GLOBAL_CONFIG,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    WSOL_MINT,
)
from pumpfun_cli.protocol.quote import _GLOBAL_LAYOUT

MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
COIN = Pubkey.from_string("9PWeFRMCgEpt6ygn4L6c2sEFtRTerppBKUTWgyRwpump")
CREATOR = Pubkey.from_string("7BajYqDdCgin9T6UnJon1pH2kJwXhLe9d277iRcva8wX")
T22_QUOTE = Pubkey.from_string("SPCXxcqXj6e5dJDVNovHN8744zkbhM2bYudU45BimGb")

PROTOCOL_RECIPIENTS = [Pubkey.new_unique() for _ in range(8)]
RESERVED_RECIPIENT = Pubkey.new_unique()
BUYBACK_RECIPIENTS = [Pubkey.new_unique() for _ in range(8)]


def build_curve_data(
    *,
    virtual_token: int = 1_000_000_000_000_000,
    virtual_quote: int = 30_000_000_000,
    real_token: int = 793_100_000_000_000,
    real_quote: int = 0,
    supply: int = 1_000_000_000_000_000,
    complete: bool = False,
    creator: Pubkey = CREATOR,
    mayhem: bool = False,
    cashback: bool = False,
    quote_mint: Pubkey = DEFAULT_PUBKEY,
    creator_fee_bps: int = 0,
    holder_reward: bool = False,
    length: int = 125,
) -> bytes:
    """A BondingCurve account as create_v2 allocates it (125 bytes) or longer."""
    data = bytearray(max(length, 125))
    data[:8] = BONDING_CURVE_DISCRIMINATOR
    struct.pack_into(
        "<QQQQQ?", data, 8, virtual_token, virtual_quote, real_token, real_quote, supply, complete
    )
    data[49:81] = bytes(creator)
    data[81] = mayhem
    data[82] = cashback
    data[83:115] = bytes(quote_mint)
    struct.pack_into("<Q", data, 115, creator_fee_bps)
    data[124] = holder_reward
    return bytes(data[:length])


def build_pool_data(
    *,
    mint: Pubkey = MINT,
    quote_mint: Pubkey = WSOL_MINT,
    coin_creator: Pubkey | None = CREATOR,
    base_account: Pubkey | None = None,
    quote_account: Pubkey | None = None,
    mayhem: bool = False,
    cashback: bool = False,
    virtual_quote: int = 0,
    index: int = 0,
) -> bytes:
    """A PumpSwap Pool account (301 bytes, like live pools)."""
    data = bytearray(301)
    data[:8] = POOL_DISCRIMINATOR
    data[8] = 255
    struct.pack_into("<H", data, 9, index)
    data[11:43] = bytes(Pubkey.new_unique())
    data[43:75] = bytes(mint)
    data[75:107] = bytes(quote_mint)
    data[107:139] = bytes(Pubkey.new_unique())
    data[139:171] = bytes(base_account or Pubkey.new_unique())
    data[171:203] = bytes(quote_account or Pubkey.new_unique())
    struct.pack_into("<Q", data, 203, 1_000_000)
    data[211:243] = bytes(coin_creator or DEFAULT_PUBKEY)
    data[243] = mayhem
    data[244] = cashback
    data[245:261] = virtual_quote.to_bytes(16, "little", signed=True)
    return bytes(data)


def build_global_config_data(
    lp_bps: int = 20, protocol_bps: int = 5, creator_bps: int = 5
) -> bytes:
    """A PumpSwap GlobalConfig with known fees and recipients."""
    data = bytearray(GLOBALCONFIG_BUYBACK_FEE_RECIPIENTS_OFFSET + 8 * 32 + 16)
    data[:8] = GLOBAL_CONFIG_DISCRIMINATOR
    struct.pack_into("<Q", data, GLOBALCONFIG_LP_FEE_BPS_OFFSET, lp_bps)
    struct.pack_into("<Q", data, GLOBALCONFIG_PROTOCOL_FEE_BPS_OFFSET, protocol_bps)
    struct.pack_into("<Q", data, GLOBALCONFIG_COIN_CREATOR_FEE_BPS_OFFSET, creator_bps)
    for i, pk in enumerate(PROTOCOL_RECIPIENTS):
        off = GLOBALCONFIG_PROTOCOL_FEE_RECIPIENTS_OFFSET + 32 * i
        data[off : off + 32] = bytes(pk)
    off = GLOBALCONFIG_RESERVED_FEE_RECIPIENT_OFFSET
    data[off : off + 32] = bytes(RESERVED_RECIPIENT)
    for i, pk in enumerate(BUYBACK_RECIPIENTS):
        off = GLOBALCONFIG_BUYBACK_FEE_RECIPIENTS_OFFSET + 32 * i
        data[off : off + 32] = bytes(pk)
    return bytes(data)


GLOBAL_DEFAULTS = {
    "initialized": True,
    "initial_virtual_token_reserves": 1_073_000_000_000_000,
    "initial_virtual_sol_reserves": 30_000_000_000,
    "initial_real_token_reserves": 793_100_000_000_000,
    "token_total_supply": 1_000_000_000_000_000,
    "fee_basis_points": 95,
    "creator_fee_basis_points": 30,
    "withdraw_authority": Pubkey.from_string("39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"),
    "initial_virtual_quote_reserves": 5_000_000_000,
    "whitelisted_quote_mints": [MINT],
    "creator_fee_configurable": True,
    "max_configurable_creator_fee_bps": 500,
    "is_holder_reward_enabled": True,
}


def build_global_data(**overrides) -> bytes:
    """pump.fun's Global account, every field in declaration order."""
    values = {**GLOBAL_DEFAULTS, **overrides}
    out = bytearray(b"\x00" * 8)
    for name, kind in _GLOBAL_LAYOUT:
        base, _, count = kind.partition("[")
        repeat = int(count.rstrip("]")) if count else 1
        value = values.get(name)
        if base == "bool":
            out += bytes([1 if value else 0])
        elif base == "u64":
            out += struct.pack("<Q", value or 0)
        else:
            items = value if count else [value]
            items = list(items or [])
            for i in range(repeat):
                out += bytes(items[i]) if i < len(items) and items[i] else bytes(32)
    return bytes(out)


def build_quote_control_data(entries: dict[Pubkey, int]) -> bytes:
    data = bytearray(8 + 32 + 64)
    data += struct.pack("<I", len(entries))
    for mint, reserves in entries.items():
        data += bytes(mint) + struct.pack("<Q", reserves)
    return bytes(data)


def build_mint_data(decimals: int) -> bytes:
    data = bytearray(82)
    data[44] = decimals
    return bytes(data)


class FakeClient:
    """In-memory stand-in for RpcClient: accounts by address, sends recorded."""

    def __init__(self):
        self.accounts: dict[Pubkey, SimpleNamespace] = {}
        self.balances: dict[Pubkey, int] = {}
        self.token_balances: dict[Pubkey, int] = {}
        self.default_balance = 10_000_000_000
        self.sent: list[dict] = []
        self.send_error: Exception | None = None
        # What getTransaction returns for any signature; None means not found.
        self.transaction: dict | None = None

    def add(self, address: Pubkey, data: bytes, owner: Pubkey = TOKEN_PROGRAM) -> None:
        self.accounts[address] = SimpleNamespace(data=data, owner=owner, lamports=1)

    def add_mint(self, mint: Pubkey, decimals: int, program: Pubkey = TOKEN_2022_PROGRAM) -> None:
        self.add(mint, build_mint_data(decimals), owner=program)

    async def get_account_info(self, pubkey: Pubkey):
        return SimpleNamespace(value=self.accounts.get(pubkey))

    async def get_multiple_accounts(self, pubkeys):
        return [self.accounts.get(pk) for pk in pubkeys]

    async def get_balance(self, pubkey: Pubkey, commitment=None) -> int:
        return self.balances.get(pubkey, self.default_balance)

    async def get_minimum_balance_for_rent_exemption(self, size: int) -> int:
        return 650_240 if size == 0 else (128 + size) * 5_080

    async def get_token_account_balance(self, account: Pubkey) -> int:
        return self.token_balances.get(account, 0)

    async def send_tx(
        self, instructions, signers, compute_units=100_000, priority_fee=200_000, confirm=False
    ):
        if self.send_error:
            raise self.send_error
        self.sent.append(
            {
                "instructions": instructions,
                "signers": signers,
                "compute_units": compute_units,
                "priority_fee": priority_fee,
                "confirm": confirm,
            }
        )
        return "fakesig"

    async def get_transaction(self, signature: str) -> dict | None:
        return self.transaction

    async def close(self) -> None:
        return None


def chain_with_coin(
    *,
    mint: Pubkey = COIN,
    curve: bytes | None = None,
    quote_decimals: int | None = None,
    quote_mint: Pubkey | None = None,
    quote_program: Pubkey = TOKEN_2022_PROGRAM,
) -> FakeClient:
    """A chain holding one pump.fun coin's mint, its curve, and Global."""
    client = FakeClient()
    client.add_mint(mint, 6, TOKEN_2022_PROGRAM)
    client.add(derive_bonding_curve(mint), curve if curve is not None else build_curve_data())
    client.add(PUMP_GLOBAL, build_global_data())
    if quote_mint is not None and quote_decimals is not None:
        client.add_mint(quote_mint, quote_decimals, quote_program)
    return client


def add_pool(
    client: FakeClient,
    *,
    mint: Pubkey = COIN,
    quote_mint: Pubkey = WSOL_MINT,
    base_reserve: int = 500_000_000_000_000,
    quote_reserve: int = 80_000_000_000,
    **pool_kwargs,
) -> dict:
    """Add a canonical pool for `mint`, its vault balances and GlobalConfig."""
    base_account, quote_account = Pubkey.new_unique(), Pubkey.new_unique()
    pool_address = derive_amm_pool(mint, quote_mint)
    client.add(
        pool_address,
        build_pool_data(
            mint=mint,
            quote_mint=quote_mint,
            base_account=base_account,
            quote_account=quote_account,
            **pool_kwargs,
        ),
        owner=Pubkey.new_unique(),
    )
    client.token_balances[base_account] = base_reserve
    client.token_balances[quote_account] = quote_reserve
    client.add(PUMP_SWAP_GLOBAL_CONFIG, build_global_config_data(), owner=Pubkey.new_unique())
    return {"address": pool_address, "base_account": base_account, "quote_account": quote_account}


def add_quote_control(client: FakeClient, entries: dict[Pubkey, int]) -> None:
    client.add(find_quote_control(), build_quote_control_data(entries), owner=Pubkey.new_unique())
