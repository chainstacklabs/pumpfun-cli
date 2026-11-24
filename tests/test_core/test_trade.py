"""Bonding-curve trades, payouts and migration, against an in-memory chain."""

from unittest.mock import patch

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.core.trade import (
    MAX_SWEEPS,
    buy_token,
    claim_cashback,
    close_volume_accumulator,
    collect_creator_fees,
    migrate_token,
    sell_token,
)
from pumpfun_cli.protocol.address import (
    derive_amm_creator_vault,
    derive_amm_pool,
    derive_bonding_curve,
    derive_creator_vault,
    find_ata,
    find_user_volume_accumulator,
)
from pumpfun_cli.protocol.client import (
    TransactionExpiredError,
    TransactionFailedError,
    TransactionNotSentError,
)
from pumpfun_cli.protocol.contracts import (
    ASSOCIATED_TOKEN_PROGRAM,
    BUY_EXACT_QUOTE_IN_V2_DISCRIMINATOR,
    CLAIM_CASHBACK_V2_DISCRIMINATOR,
    COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR,
    COLLECT_CREATOR_FEE_V2_DISCRIMINATOR,
    MIGRATE_V2_DISCRIMINATOR,
    PUMP_AMM_PROGRAM,
    PUMP_BUY_COMPUTE_UNITS,
    PUMP_NON_SOL_TRADE_COMPUTE_UNITS,
    PUMP_PROGRAM,
    SELL_V2_DISCRIMINATOR,
    SWEEP_CREATOR_FEE_DISCRIMINATOR,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    WSOL_MINT,
)
from tests.test_core.helpers import (
    COIN,
    CREATOR,
    GLOBAL_DEFAULTS,
    T22_QUOTE,
    TOKEN_ACCOUNT_LAMPORTS,
    FakeClient,
    assert_closes,
    assert_harvests,
    build_curve_data,
    build_pool_data,
    chain_with_coin,
    closed_accounts,
    hold,
)

MINT_STR = str(COIN)


def _patched(client: FakeClient):
    return patch("pumpfun_cli.core.trade.RpcClient", return_value=client)


def _pump_ix(sent: dict):
    return next(i for i in sent["instructions"] if i.program_id == PUMP_PROGRAM)


def _user_from(tmp_keystore):
    from pathlib import Path

    from pumpfun_cli.crypto import decrypt_keypair

    return decrypt_keypair(Path(tmp_keystore), "testpass").pubkey()


# --- input validation ---


@pytest.mark.parametrize(
    "fn,args", [(buy_token, (0.01,)), (sell_token, ("all",)), (migrate_token, ())]
)
async def test_invalid_mint_is_refused_before_any_rpc(tmp_keystore, fn, args):
    result = await fn("http://rpc", tmp_keystore, "testpass", "not-a-mint", *args)
    assert result["error"] == "invalid_address"


# --- buy ---


async def test_buy_no_curve(tmp_keystore):
    client = FakeClient()
    client.add_mint(COIN, 6)
    with _patched(client):
        result = await buy_token("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
    assert result["error"] == "not_found"


async def test_buy_graduated_curve_defers_to_pumpswap(tmp_keystore):
    client = chain_with_coin(curve=build_curve_data(complete=True))
    with _patched(client):
        result = await buy_token("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
    assert result["error"] == "graduated"


async def test_buy_sol_coin_spends_exact_quote(tmp_keystore):
    client = chain_with_coin()
    with _patched(client):
        result = await buy_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01, slippage=10
        )
    assert result["action"] == "buy"
    assert result["quote_symbol"] == "SOL"
    assert result["quote_spent"] == 0.01
    assert result["signature"] == "fakesig"

    sent = client.sent[0]
    assert sent["compute_units"] == PUMP_BUY_COMPUTE_UNITS
    # Only the base ATA is created; a SOL coin's quote account is seed-checked only.
    assert [i.program_id for i in sent["instructions"]] == [ASSOCIATED_TOKEN_PROGRAM, PUMP_PROGRAM]
    ix = _pump_ix(sent)
    assert bytes(ix.data[:8]) == BUY_EXACT_QUOTE_IN_V2_DISCRIMINATOR
    spend = int.from_bytes(bytes(ix.data[8:16]), "little")
    floor = int.from_bytes(bytes(ix.data[16:24]), "little")
    expected = 10_000_000 * 1_000_000_000_000_000 // (30_000_000_000 + 10_000_000)
    assert spend == 10_000_000
    assert floor == int(expected * 0.9)
    keys = [m.pubkey for m in ix.accounts]
    assert keys[2] == WSOL_MINT
    assert keys[16] == derive_creator_vault(CREATOR)


async def test_buy_uses_curve_creator_not_launcher(tmp_keystore):
    """A fee-sharing or holder-reward coin stores a different creator; the vault follows it."""
    other = Pubkey.new_unique()
    client = chain_with_coin(curve=build_curve_data(creator=other))
    with _patched(client):
        await buy_token("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
    assert _pump_ix(client.sent[0]).accounts[16].pubkey == derive_creator_vault(other)


async def test_buy_full_slippage_still_asks_for_one_token(tmp_keystore):
    client = chain_with_coin()
    with _patched(client):
        await buy_token("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01, slippage=100)
    floor = int.from_bytes(bytes(_pump_ix(client.sent[0]).data[16:24]), "little")
    assert floor == 1


async def test_buy_non_sol_coin_scales_by_quote_decimals(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = chain_with_coin(
        curve=build_curve_data(quote_mint=T22_QUOTE, virtual_quote=5_000_000_000),
        quote_mint=T22_QUOTE,
        quote_decimals=6,
    )
    client.token_balances[find_ata(user, T22_QUOTE, TOKEN_2022_PROGRAM)] = 5_000_000
    with _patched(client):
        result = await buy_token("http://rpc", tmp_keystore, "testpass", MINT_STR, 2.5)
    assert result["quote_symbol"] == str(T22_QUOTE)
    sent = client.sent[0]
    assert sent["compute_units"] == PUMP_NON_SOL_TRADE_COMPUTE_UNITS
    ix = _pump_ix(sent)
    assert int.from_bytes(bytes(ix.data[8:16]), "little") == 2_500_000
    assert ix.accounts[2].pubkey == T22_QUOTE
    assert ix.accounts[4].pubkey == TOKEN_2022_PROGRAM


async def test_buy_non_sol_coin_needs_the_quote_asset(tmp_keystore):
    client = chain_with_coin(
        curve=build_curve_data(quote_mint=T22_QUOTE), quote_mint=T22_QUOTE, quote_decimals=6
    )
    with _patched(client):
        result = await buy_token("http://rpc", tmp_keystore, "testpass", MINT_STR, 2.5)
    assert result["error"] == "insufficient_balance"
    assert client.sent == []


async def test_buy_insufficient_sol(tmp_keystore):
    client = chain_with_coin()
    client.default_balance = 1_000
    with _patched(client):
        result = await buy_token("http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01)
    assert result["error"] == "insufficient_balance"
    assert client.sent == []


async def test_buy_dry_run_sends_nothing(tmp_keystore):
    client = chain_with_coin()
    with _patched(client):
        result = await buy_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01, dry_run=True
        )
    assert result["dry_run"] is True
    assert result["quote_in"] == 0.01
    assert result["spot_price"] == pytest.approx(3e-8)  # 30 SOL / 1e9 tokens
    assert {"expected_tokens", "min_tokens_out", "effective_price", "price_impact_pct"} <= set(
        result
    )
    assert client.sent == []


@pytest.mark.parametrize("code,error", [(6042, "slippage"), (6000, "tx_error")])
async def test_buy_maps_onchain_errors(tmp_keystore, code, error):
    client = chain_with_coin()
    client.send_error = TransactionFailedError({"InstructionError": [2, {"Custom": code}]})
    with _patched(client):
        result = await buy_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01, confirm=True
        )
    assert result["error"] == error
    assert result["error_code"] == code


# --- sell ---


async def test_sell_all(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = chain_with_coin()
    hold(client, user, COIN, 5_000_000)
    with _patched(client):
        result = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
    assert result["tokens_sold"] == 5.0
    assert result["quote_symbol"] == "SOL"
    ix = _pump_ix(client.sent[0])
    assert bytes(ix.data[:8]) == SELL_V2_DISCRIMINATOR
    assert len(ix.accounts) == 26
    assert int.from_bytes(bytes(ix.data[8:16]), "little") == 5_000_000
    # A SOL coin pays out natively: the sell, then closing the emptied account.
    sell, close = client.sent[0]["instructions"]
    assert sell.program_id == PUMP_PROGRAM
    assert_closes(close, find_ata(user, COIN, TOKEN_2022_PROGRAM), user, TOKEN_2022_PROGRAM)
    assert result["token_account_closed"] is True
    assert result["rent_recovered_sol"] == TOKEN_ACCOUNT_LAMPORTS / 10**9
    assert result["rent_recovered_sol_raw"] == TOKEN_ACCOUNT_LAMPORTS


async def test_selling_exactly_the_balance_closes_the_account(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = chain_with_coin()
    hold(client, user, COIN, 5_000_000)
    with _patched(client):
        result = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "5")
    assert_closes(
        client.sent[0]["instructions"][-1],
        find_ata(user, COIN, TOKEN_2022_PROGRAM),
        user,
        TOKEN_2022_PROGRAM,
    )
    assert result["token_account_closed"] is True


async def test_a_partial_sell_leaves_the_account_open(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = chain_with_coin()
    hold(client, user, COIN, 5_000_000)
    with _patched(client):
        result = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "4.999999")
    assert closed_accounts(client.sent[0]["instructions"]) == []
    assert "token_account_closed" not in result


async def test_an_account_someone_else_can_close_stays_open(tmp_keystore):
    """Some trading tools set their own close authority on the accounts they open."""
    user = _user_from(tmp_keystore)
    client = chain_with_coin()
    ata = hold(client, user, COIN, 5_000_000)
    client.closers[ata] = Pubkey.new_unique()
    with _patched(client):
        result = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
    assert result["tokens_sold_raw"] == 5_000_000
    assert closed_accounts(client.sent[0]["instructions"]) == []
    assert "token_account_closed" not in result


async def test_withheld_transfer_fees_are_harvested_before_closing(tmp_keystore):
    user = _user_from(tmp_keystore)
    ata = find_ata(user, COIN, TOKEN_2022_PROGRAM)
    client = chain_with_coin()
    hold(client, user, COIN, 5_000_000, withheld=7)
    with _patched(client):
        await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
    _, harvest, close = client.sent[0]["instructions"]
    assert_harvests(harvest, COIN, ata)
    assert_closes(close, ata, user, TOKEN_2022_PROGRAM)


async def test_sell_non_sol_creates_the_payout_account(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = chain_with_coin(
        curve=build_curve_data(quote_mint=T22_QUOTE), quote_mint=T22_QUOTE, quote_decimals=6
    )
    hold(client, user, COIN, 1_000_000)
    with _patched(client):
        result = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "1")
    assert result["action"] == "sell"
    instructions = client.sent[0]["instructions"]
    assert instructions[0].program_id == ASSOCIATED_TOKEN_PROGRAM
    assert instructions[0].accounts[3].pubkey == T22_QUOTE


async def test_sell_more_than_held(tmp_keystore):
    client = chain_with_coin()
    with _patched(client):
        result = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "5")
    assert result["error"] == "insufficient_balance"


async def test_sell_nothing_held(tmp_keystore):
    client = chain_with_coin()
    with _patched(client):
        result = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
    assert result["error"] == "no_tokens"


async def test_sell_dry_run(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = chain_with_coin()
    hold(client, user, COIN, 5_000_000)
    with _patched(client):
        result = await sell_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, "all", dry_run=True
        )
    assert result["dry_run"] is True
    assert {"expected_quote", "min_quote_out", "spot_price"} <= set(result)
    assert client.sent == []


async def test_buy_past_the_curve_reports_tokens_left(tmp_keystore):
    client = chain_with_coin()
    client.send_error = TransactionFailedError({"InstructionError": [2, {"Custom": 6021}]})
    with _patched(client):
        result = await buy_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, 0.01, confirm=True
        )
    assert result["error"] == "exceeds_curve"
    assert result["curve_tokens_left_raw"] == 793_100_000_000_000
    assert "793100000.000000 tokens left" in result["message"]


# A mayhem-style curve whose real reserves fall short of what its price promises.
_SHORT_CURVE = {"real_quote": 1_000_000, "mayhem": True}
_HELD = 10**14


async def test_sell_caps_at_what_the_curve_can_pay(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = chain_with_coin(curve=build_curve_data(**_SHORT_CURVE))
    hold(client, user, COIN, _HELD)
    with _patched(client):
        result = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
    sold = int.from_bytes(bytes(_pump_ix(client.sent[0]).data[8:16]), "little")
    assert 0 < sold < _HELD
    assert result["tokens_sold_raw"] == sold
    assert result["tokens_kept_raw"] == _HELD - sold
    # What the curve can't pay for stays in the account, so it stays open.
    assert closed_accounts(client.sent[0]["instructions"]) == []
    assert "token_account_closed" not in result
    # The payout fits the real reserves, and one more token would not.
    assert sold * 30_000_000_000 // (10**15 + sold) <= 1_000_000
    assert (sold + 1) * 30_000_000_000 // (10**15 + sold + 1) > 1_000_000


async def test_sell_dry_run_shows_what_the_curve_cant_pay(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = chain_with_coin(curve=build_curve_data(**_SHORT_CURVE))
    hold(client, user, COIN, _HELD)
    with _patched(client):
        result = await sell_token(
            "http://rpc", tmp_keystore, "testpass", MINT_STR, "all", dry_run=True
        )
    assert result["tokens_in_raw"] + result["tokens_kept_raw"] == _HELD
    assert client.sent == []


async def test_sell_within_reserves_keeps_nothing(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = chain_with_coin()
    hold(client, user, COIN, 5_000_000)
    with _patched(client):
        result = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
    assert "tokens_kept" not in result


async def test_sell_refused_when_the_curve_can_pay_nothing(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = chain_with_coin(curve=build_curve_data(real_quote=0, mayhem=True))
    hold(client, user, COIN, 5_000_000)
    with _patched(client):
        result = await sell_token("http://rpc", tmp_keystore, "testpass", MINT_STR, "all")
    assert result["error"] == "curve_short"
    assert client.sent == []


# --- cashback, accumulator, fees, migration ---


async def test_claim_cashback_without_accumulator(tmp_keystore):
    client = FakeClient()
    with _patched(client):
        result = await claim_cashback("http://rpc", tmp_keystore, "testpass")
    assert result["error"] == "no_accumulator"


async def test_claim_cashback_sol(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.add(find_user_volume_accumulator(user), b"\x00" * 8)
    with _patched(client):
        result = await claim_cashback("http://rpc", tmp_keystore, "testpass")
    assert result["quote_symbol"] == "SOL"
    ixs = client.sent[0]["instructions"]
    assert len(ixs) == 1
    assert bytes(ixs[0].data) == CLAIM_CASHBACK_V2_DISCRIMINATOR


async def test_claim_cashback_other_quote_creates_payout_account(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.add_mint(T22_QUOTE, 6)
    client.add(find_user_volume_accumulator(user), b"\x00" * 8)
    with _patched(client):
        await claim_cashback("http://rpc", tmp_keystore, "testpass", str(T22_QUOTE))
    ixs = client.sent[0]["instructions"]
    assert ixs[0].program_id == ASSOCIATED_TOKEN_PROGRAM
    assert ixs[1].accounts[2].pubkey == T22_QUOTE


async def test_close_volume_accumulator(tmp_keystore):
    client = FakeClient()
    with _patched(client):
        result = await close_volume_accumulator("http://rpc", tmp_keystore, "testpass")
    assert result["action"] == "close_volume_accumulator"
    assert result["signature"] == "fakesig"


async def test_collect_creator_fees_nothing_accrued(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.balances[derive_creator_vault(user)] = 0
    with _patched(client):
        result = await collect_creator_fees("http://rpc", tmp_keystore, "testpass")
    assert result["error"] == "no_fees"


async def test_collect_creator_fees_from_both_venues(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.balances[derive_creator_vault(user)] = 2_000_650_240
    client.token_balances[find_ata(derive_amm_creator_vault(user), WSOL_MINT, TOKEN_PROGRAM)] = (
        500_000_000
    )
    with _patched(client):
        result = await collect_creator_fees("http://rpc", tmp_keystore, "testpass")
    assert result["pump_recovered"] == 2.0
    assert result["pumpswap_recovered"] == 0.5
    discs = [bytes(i.data[:8]) for i in client.sent[0]["instructions"]]
    assert COLLECT_CREATOR_FEE_V2_DISCRIMINATOR in discs
    assert COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR in discs


async def test_migrate_needs_a_complete_curve(tmp_keystore):
    client = chain_with_coin()
    with _patched(client):
        result = await migrate_token("http://rpc", tmp_keystore, "testpass", MINT_STR)
    assert result["error"] == "not_complete"


async def test_migrate_complete_curve_uses_global_withdraw_authority(tmp_keystore):
    client = chain_with_coin(curve=build_curve_data(complete=True))
    with _patched(client):
        result = await migrate_token("http://rpc", tmp_keystore, "testpass", MINT_STR)
    assert result["action"] == "migrate"
    ix = client.sent[0]["instructions"][0]
    assert bytes(ix.data) == MIGRATE_V2_DISCRIMINATOR
    assert ix.accounts[1].pubkey == GLOBAL_DEFAULTS["withdraw_authority"]
    assert ix.accounts[10].pubkey == derive_amm_pool(COIN, WSOL_MINT)


async def test_collect_ignores_the_vaults_rent_floor(tmp_keystore):
    """A SOL creator vault keeps its rent-exempt minimum; that is not a fee to collect."""
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.balances[derive_creator_vault(user)] = 650_240
    with _patched(client):
        result = await collect_creator_fees("http://rpc", tmp_keystore, "testpass")
    assert result["error"] == "no_fees"
    assert client.sent == []


@pytest.mark.parametrize("fn,arg", [(buy_token, 0.01), (sell_token, "all")])
async def test_legacy_curve_without_creator_is_refused(tmp_keystore, fn, arg):
    client = chain_with_coin(curve=build_curve_data(length=49))
    with _patched(client):
        result = await fn("http://rpc", tmp_keystore, "testpass", MINT_STR, arg)
    assert result["error"] == "legacy_curve"
    assert client.sent == []


def _waiting_curve(client: FakeClient, creator: Pubkey, fee: int, **curve) -> Pubkey:
    """A coin of `creator` whose curve holds `fee` waiting for a sweep."""
    mint = Pubkey.new_unique()
    curve_address = derive_bonding_curve(mint)
    client.add(
        curve_address,
        build_curve_data(creator=creator, creator_fee=fee, length=166, **curve),
        owner=PUMP_PROGRAM,
    )
    client.token_accounts[curve_address] = [(mint, TOKEN_2022_PROGRAM)]
    return mint


def _waiting_pool(client: FakeClient, creator: Pubkey, fee: int) -> Pubkey:
    address = Pubkey.new_unique()
    client.add(
        address, build_pool_data(coin_creator=creator, creator_fees=fee), owner=PUMP_AMM_PROGRAM
    )
    return address


def _sweeps(sent: dict) -> list:
    return [
        ix for ix in sent["instructions"] if bytes(ix.data[:8]) == SWEEP_CREATOR_FEE_DISCRIMINATOR
    ]


def _land_sweeps(client: FakeClient, creator: Pubkey, fees: dict, then_raise=None) -> None:
    """Make sweep-only transactions move their fees into the creator's vaults, as on
    chain; `fees` maps a curve's mint or a pool's address to its waiting fee.
    `then_raise` is raised after the first one lands, as when a confirmation is lost."""
    real_send = client.send_tx
    amm_ata = find_ata(derive_amm_creator_vault(creator), WSOL_MINT, TOKEN_PROGRAM)

    async def send(instructions, signers, **kw):
        sig = await real_send(instructions, signers, **kw)
        sweeps = _sweeps({"instructions": instructions})
        if sweeps and len(sweeps) == len(instructions):
            for ix in sweeps:
                key = next(m.pubkey for m in ix.accounts if m.pubkey in fees)
                if ix.program_id == PUMP_PROGRAM:
                    vault = derive_creator_vault(creator)
                    client.balances[vault] = client.balances.get(vault, 0) + fees[key]
                else:
                    client.token_balances[amm_ata] = (
                        client.token_balances.get(amm_ata, 0) + fees[key]
                    )
            if then_raise is not None:
                raise then_raise
        return sig

    client.send_tx = send


async def test_collect_sweeps_fees_waiting_on_curves_and_pools_first(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.balances[derive_creator_vault(user)] = 650_240  # only the rent floor
    mint = _waiting_curve(client, user, 300_000_000)
    pool = _waiting_pool(client, user, 200_000_000)
    _waiting_curve(client, CREATOR, 999)  # someone else's coin
    _waiting_curve(client, user, 0)  # nothing waiting
    with _patched(client):
        result = await collect_creator_fees("http://rpc", tmp_keystore, "testpass")
    assert result["pump_recovered"] == 0.3
    assert result["pumpswap_recovered"] == 0.2
    assert result["coins_swept"] == 2
    ixs = client.sent[0]["instructions"]
    sweeps = _sweeps(client.sent[0])
    assert {(ix.program_id, ix.accounts[2].pubkey) for ix in sweeps} == {
        (PUMP_PROGRAM, mint),
        (PUMP_AMM_PROGRAM, pool),
    }
    collects = [
        i
        for i, ix in enumerate(ixs)
        if bytes(ix.data[:8])
        in (COLLECT_CREATOR_FEE_V2_DISCRIMINATOR, COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR)
    ]
    assert max(ixs.index(ix) for ix in sweeps) < min(collects)


async def test_collect_sweeps_only_the_requested_quote_asset(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.balances[derive_creator_vault(user)] = 650_240
    _waiting_curve(client, user, 5_000, quote_mint=Pubkey.new_unique())
    with _patched(client):
        result = await collect_creator_fees("http://rpc", tmp_keystore, "testpass")
    assert result["error"] == "no_fees"


async def test_collect_sweeps_every_waiting_coin(tmp_keystore):
    """The largest go with the collect; the rest are swept, and confirmed, first."""
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.balances[derive_creator_vault(user)] = 650_240  # only the rent floor
    fees = [1_000 * (i + 1) for i in range(2 * MAX_SWEEPS + 3)]
    mints = {_waiting_curve(client, user, fee): fee for fee in fees}
    _land_sweeps(client, user, mints)
    with _patched(client):
        result = await collect_creator_fees("http://rpc", tmp_keystore, "testpass")
    ahead, collect = client.sent[:-1], client.sent[-1]
    assert [len(_sweeps(tx)) for tx in ahead] == [MAX_SWEEPS, 3]
    assert all(tx["confirm"] for tx in ahead)
    assert all(len(_sweeps(tx)) == len(tx["instructions"]) for tx in ahead)
    swept_with_collect = {mints[ix.accounts[2].pubkey] for ix in _sweeps(collect)}
    assert swept_with_collect == set(sorted(fees)[-MAX_SWEEPS:])
    all_swept = [mints[ix.accounts[2].pubkey] for tx in client.sent for ix in _sweeps(tx)]
    assert sorted(all_swept) == fees
    assert result["coins_swept"] == len(fees)
    assert result["pump_recovered"] == sum(fees) / 10**9
    assert "coins_still_waiting" not in result


async def test_a_sweep_that_landed_unconfirmed_is_still_collected(tmp_keystore):
    """A lost confirmation doesn't mean the sweep failed: the vaults are read again,
    so a pool's fees that reached an empty PumpSwap vault still get collected."""
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.balances[derive_creator_vault(user)] = 650_240  # only the rent floor
    fees = {
        _waiting_curve(client, user, 1_000_000 * (i + 2)): 1_000_000 * (i + 2)
        for i in range(MAX_SWEEPS)
    }
    pool = _waiting_pool(client, user, 500)
    fees[pool] = 500
    _land_sweeps(client, user, fees, then_raise=RuntimeError("Sent x but could not confirm it"))
    with _patched(client):
        result = await collect_creator_fees("http://rpc", tmp_keystore, "testpass")
    collect = client.sent[-1]["instructions"]
    assert any(bytes(ix.data[:8]) == COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR for ix in collect)
    assert result["pumpswap_recovered"] == 500 / 10**9
    assert "outcome is unknown" in result["sweep_warning"]


@pytest.mark.parametrize(
    "never_ran",
    [
        TransactionFailedError({"InstructionError": [0, {"Custom": 1}]}),
        TransactionNotSentError("The RPC refused the transaction"),
        TransactionExpiredError("sig"),
    ],
    ids=["failed", "not_sent", "expired"],
)
async def test_a_sweep_ahead_that_never_ran_still_collects_what_landed(tmp_keystore, never_ran):
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.balances[derive_creator_vault(user)] = 650_240  # only the rent floor
    fees = [1_000 * (i + 1) for i in range(MAX_SWEEPS + 2)]
    for fee in fees:
        _waiting_curve(client, user, fee)
    sends = []
    real_send = client.send_tx

    async def send(instructions, signers, **kw):
        sends.append(instructions)
        if len(sends) == 1:
            raise never_ran
        return await real_send(instructions, signers, **kw)

    client.send_tx = send
    with _patched(client):
        result = await collect_creator_fees("http://rpc", tmp_keystore, "testpass")
    assert result["coins_swept"] == MAX_SWEEPS
    assert result["pump_recovered"] == sum(sorted(fees)[-MAX_SWEEPS:]) / 10**9
    assert result["sweep_warning"].startswith("2 coin(s) not swept")


async def test_collect_without_get_program_accounts_collects_the_vaults(tmp_keystore):
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.balances[derive_creator_vault(user)] = 650_240 + 1_000_000
    client.program_accounts_error = RuntimeError("method not allowed")
    with _patched(client):
        result = await collect_creator_fees("http://rpc", tmp_keystore, "testpass")
    assert result["pump_recovered"] == 0.001
    assert "getProgramAccounts" in result["sweep_warning"]
    assert not _sweeps(client.sent[0])


async def test_collect_without_get_program_accounts_and_empty_vaults_says_so(tmp_keystore):
    """Empty vaults plus a failed search must not read as "nothing to collect"."""
    user = _user_from(tmp_keystore)
    client = FakeClient()
    client.balances[derive_creator_vault(user)] = 650_240  # only the rent floor
    client.program_accounts_error = RuntimeError("method not allowed")
    with _patched(client):
        result = await collect_creator_fees("http://rpc", tmp_keystore, "testpass")
    assert result["error"] == "no_fees"
    assert "getProgramAccounts" in result["message"]
    assert "getProgramAccounts" in result["sweep_warning"]
    assert not client.sent
