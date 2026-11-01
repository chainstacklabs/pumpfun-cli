"""Instruction builders checked against the vendored IDLs.

Every pump.fun builder must match its IDL instruction: discriminator, account
order, writable and signer flags, and fixed addresses. PumpSwap swaps carry
accounts the IDL does not list, so only their IDL prefix is checked here; the
extras are covered in test_pumpswap_instructions.py.
"""

import json
import struct
from pathlib import Path

import pytest
from solders.instruction import Instruction
from solders.pubkey import Pubkey

from pumpfun_cli.protocol import instructions as ix
from pumpfun_cli.protocol.address import (
    derive_bonding_curve,
    derive_creator_vault,
    find_ata,
    find_global_volume_accumulator,
    find_sharing_config,
)
from pumpfun_cli.protocol.contracts import (
    BUYBACK_FEE_RECIPIENTS,
    NORMAL_FEE_RECIPIENTS,
    RESERVED_FEE_RECIPIENTS,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    WSOL_MINT,
)

IDL_DIR = Path(__file__).parents[2] / "idl"
PUMP_IDL = json.loads((IDL_DIR / "pump_fun_idl.json").read_text())
AMM_IDL = json.loads((IDL_DIR / "pump_fun_amm_idl.json").read_text())

USER = Pubkey.new_unique()
MINT = Pubkey.new_unique()
CREATOR = Pubkey.new_unique()


def _spec(idl: dict, name: str) -> dict:
    return next(i for i in idl["instructions"] if i["name"] == name)


def assert_matches_idl(idl: dict, name: str, built: Instruction, prefix: int | None = None):
    spec = _spec(idl, name)
    assert bytes(built.data[:8]) == bytes(spec["discriminator"]), f"{name} discriminator"
    accounts = spec["accounts"][:prefix] if prefix else spec["accounts"]
    if prefix is None:
        assert len(built.accounts) >= len(accounts)
    for i, (want, got) in enumerate(zip(accounts, built.accounts, strict=False)):
        label = f"{name}[{i}] {want['name']}"
        assert got.is_writable == bool(want.get("writable")), f"{label} writable"
        assert got.is_signer == bool(want.get("signer")), f"{label} signer"
        if "address" in want:
            assert got.pubkey == Pubkey.from_string(want["address"]), f"{label} address"


PUMP_BUILDERS = [
    (
        "buy_v2",
        lambda: ix.build_buy_v2_instruction(
            mint=MINT, creator=CREATOR, user=USER, token_amount=1, max_quote_cost=2
        ),
        27,
    ),
    (
        "buy_exact_quote_in_v2",
        lambda: ix.build_buy_exact_quote_in_v2_instruction(
            mint=MINT, creator=CREATOR, user=USER, spendable_quote_in=1, min_tokens_out=2
        ),
        27,
    ),
    (
        "sell_v2",
        lambda: ix.build_sell_v2_instruction(
            mint=MINT, creator=CREATOR, user=USER, token_amount=1, min_quote_out=2
        ),
        26,
    ),
    (
        "create_v2",
        lambda: ix.build_create_v2_instruction(
            mint=MINT, user=USER, creator=USER, name="n", symbol="s", uri="u"
        ),
        20,
    ),
    ("extend_account", lambda: ix.build_extend_account_instruction(MINT, USER), 5),
    ("claim_cashback_v2", lambda: ix.build_claim_cashback_v2_instruction(user=USER), 10),
    (
        "close_user_volume_accumulator",
        lambda: ix.build_close_volume_accumulator_instruction(USER),
        4,
    ),
    (
        "collect_creator_fee_v2",
        lambda: ix.build_collect_creator_fee_v2_instruction(creator=USER),
        10,
    ),
    (
        "migrate_v2",
        lambda: ix.build_migrate_v2_instruction(mint=MINT, user=USER, withdraw_authority=CREATOR),
        27,
    ),
]


@pytest.mark.parametrize("name,build,count", PUMP_BUILDERS, ids=[b[0] for b in PUMP_BUILDERS])
def test_pump_builders_match_idl(name, build, count):
    built = build()
    assert_matches_idl(PUMP_IDL, name, built)
    assert len(built.accounts) == count


@pytest.mark.parametrize(
    "name,build",
    [
        (
            "collect_coin_creator_fee",
            lambda: ix.build_collect_coin_creator_fee_instruction(creator=USER),
        ),
        ("init_user_volume_accumulator", lambda: ix.build_init_amm_user_volume_accumulator(USER)),
    ],
)
def test_amm_builders_match_idl(name, build):
    built = build()
    assert_matches_idl(AMM_IDL, name, built)
    assert len(built.accounts) == len(_spec(AMM_IDL, name)["accounts"])


def test_buy_v2_args_are_two_u64s():
    built = ix.build_buy_v2_instruction(
        mint=MINT, creator=CREATOR, user=USER, token_amount=123, max_quote_cost=456
    )
    assert bytes(built.data[8:]) == struct.pack("<QQ", 123, 456)


def test_only_buys_carry_the_global_volume_accumulator():
    gva = find_global_volume_accumulator()
    buy = ix.build_buy_v2_instruction(
        mint=MINT, creator=CREATOR, user=USER, token_amount=1, max_quote_cost=1
    )
    sell = ix.build_sell_v2_instruction(
        mint=MINT, creator=CREATOR, user=USER, token_amount=1, min_quote_out=1
    )
    assert buy.accounts[19].pubkey == gva
    assert gva not in [m.pubkey for m in sell.accounts]


def test_v2_accounts_follow_quote_mint_and_programs():
    quote = Pubkey.new_unique()
    built = ix.build_buy_exact_quote_in_v2_instruction(
        mint=MINT,
        creator=CREATOR,
        user=USER,
        spendable_quote_in=1,
        min_tokens_out=1,
        quote_mint=quote,
        base_token_program=TOKEN_PROGRAM,
        quote_token_program=TOKEN_2022_PROGRAM,
    )
    keys = [m.pubkey for m in built.accounts]
    curve = derive_bonding_curve(MINT)
    vault = derive_creator_vault(CREATOR)
    assert keys[2] == quote
    assert keys[3] == TOKEN_PROGRAM
    assert keys[4] == TOKEN_2022_PROGRAM
    assert find_ata(curve, MINT, TOKEN_PROGRAM) in keys
    assert find_ata(curve, quote, TOKEN_2022_PROGRAM) in keys
    assert find_ata(USER, quote, TOKEN_2022_PROGRAM) in keys
    assert find_ata(vault, quote, TOKEN_2022_PROGRAM) in keys
    assert find_sharing_config(MINT) in keys


@pytest.mark.parametrize(
    "mayhem,pool", [(False, NORMAL_FEE_RECIPIENTS), (True, RESERVED_FEE_RECIPIENTS)]
)
def test_v2_fee_recipients(mayhem, pool):
    built = ix.build_sell_v2_instruction(
        mint=MINT,
        creator=CREATOR,
        user=USER,
        token_amount=1,
        min_quote_out=1,
        is_mayhem_mode=mayhem,
    )
    keys = [m.pubkey for m in built.accounts]
    assert keys[6] in pool
    assert keys[8] in BUYBACK_FEE_RECIPIENTS
    assert keys[7] == find_ata(keys[6], WSOL_MINT, TOKEN_PROGRAM)


@pytest.mark.parametrize(
    "fee,holder,tail",
    [
        (None, None, b""),
        (100, None, struct.pack("<?Q", False, 100)),
        (None, True, struct.pack("<?Q?", False, 0, True)),
        (250, True, struct.pack("<?Q?", False, 250, True)),
    ],
)
def test_create_v2_trailing_args(fee, holder, tail):
    built = ix.build_create_v2_instruction(
        mint=MINT,
        user=USER,
        creator=USER,
        name="n",
        symbol="s",
        uri="u",
        creator_fee_bps=fee,
        is_holder_reward=holder,
    )
    head = (
        bytes(_spec(PUMP_IDL, "create_v2")["discriminator"])
        + struct.pack("<I", 1)
        + b"n"
        + struct.pack("<I", 1)
        + b"s"
        + struct.pack("<I", 1)
        + b"u"
        + bytes(USER)
        + b"\x00"
    )
    assert bytes(built.data) == head + tail


def test_create_v2_never_asks_for_cashback():
    built = ix.build_create_v2_instruction(
        mint=MINT, user=USER, creator=USER, name="n", symbol="s", uri="u", creator_fee_bps=1
    )
    cashback_flag = bytes(built.data)[-9]
    assert cashback_flag == 0


def test_create_v2_quote_remaining_accounts():
    quote = Pubkey.new_unique()
    built = ix.build_create_v2_instruction(
        mint=MINT,
        user=USER,
        creator=USER,
        name="n",
        symbol="s",
        uri="u",
        quote_mint=quote,
        quote_token_program=TOKEN_2022_PROGRAM,
    )
    tail = [m.pubkey for m in built.accounts[16:]]
    curve = derive_bonding_curve(MINT)
    assert tail[0] == quote
    assert tail[1] == find_ata(curve, quote, TOKEN_2022_PROGRAM)
    assert tail[2] == TOKEN_2022_PROGRAM


# --- PDAs: every seed-derived account matches what the IDL says it derives from ---


def _resolve_pdas(spec: dict, built: Instruction, program_id: Pubkey) -> list[str]:
    """Derive each IDL PDA from the built accounts; return the names that disagree."""
    keys = {a["name"]: m.pubkey for a, m in zip(spec["accounts"], built.accounts, strict=False)}
    bad = []
    for acc in spec["accounts"]:
        pda = acc.get("pda")
        if not pda or acc["name"] not in keys:
            continue
        seeds, resolvable = [], True
        for seed in pda["seeds"]:
            if seed["kind"] == "const":
                seeds.append(bytes(seed["value"]))
            elif seed["kind"] == "account" and seed["path"] in keys:
                seeds.append(bytes(keys[seed["path"]]))
            else:
                resolvable = False
        prog = pda.get("program")
        owner = program_id
        if prog and prog["kind"] == "const":
            owner = Pubkey(bytes(prog["value"]))
        elif prog and prog["kind"] == "account":
            if prog["path"] not in keys:
                resolvable = False
            else:
                owner = keys[prog["path"]]
        if resolvable and Pubkey.find_program_address(seeds, owner)[0] != keys[acc["name"]]:
            bad.append(acc["name"])
    return bad


@pytest.mark.parametrize("name,build,count", PUMP_BUILDERS, ids=[b[0] for b in PUMP_BUILDERS])
def test_pump_builder_pdas_match_idl_seeds(name, build, count):
    built = build()
    assert (
        _resolve_pdas(_spec(PUMP_IDL, name), built, Pubkey.from_string(PUMP_IDL["address"])) == []
    )


@pytest.mark.parametrize(
    "name,build",
    [
        (
            "collect_coin_creator_fee",
            lambda: ix.build_collect_coin_creator_fee_instruction(creator=USER),
        ),
        ("init_user_volume_accumulator", lambda: ix.build_init_amm_user_volume_accumulator(USER)),
    ],
)
def test_amm_builder_pdas_match_idl_seeds(name, build):
    built = build()
    assert _resolve_pdas(_spec(AMM_IDL, name), built, Pubkey.from_string(AMM_IDL["address"])) == []
