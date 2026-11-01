"""PumpSwap Pool and GlobalConfig parsing, fee recipients and pricing."""

import pytest
from solders.pubkey import Pubkey

from pumpfun_cli.protocol.contracts import USDC_MINT
from pumpfun_cli.protocol.pumpswap import (
    parse_global_config,
    parse_pool_data,
    pick_fee_recipients,
    pool_price,
)
from tests.test_core.helpers import (
    BUYBACK_RECIPIENTS,
    CREATOR,
    MINT,
    PROTOCOL_RECIPIENTS,
    RESERVED_RECIPIENT,
    build_global_config_data,
    build_pool_data,
)


def test_parse_pool_reads_flags_and_virtual_reserves():
    base, quote = Pubkey.new_unique(), Pubkey.new_unique()
    pool = parse_pool_data(
        build_pool_data(
            quote_mint=USDC_MINT,
            base_account=base,
            quote_account=quote,
            mayhem=True,
            cashback=True,
            virtual_quote=-5,
            index=3,
        )
    )
    assert pool["base_mint"] == MINT
    assert pool["quote_mint"] == USDC_MINT
    assert pool["pool_base_token_account"] == base
    assert pool["pool_quote_token_account"] == quote
    assert pool["coin_creator"] == CREATOR
    assert pool["is_canonical"] is True
    assert pool["is_mayhem_mode"] is True
    assert pool["is_cashback_coin"] is True
    assert pool["virtual_quote_reserves"] == -5
    assert pool["index"] == 3


def test_pool_without_coin_creator_is_not_canonical():
    assert parse_pool_data(build_pool_data(coin_creator=None))["is_canonical"] is False


def test_short_pool_reads_absent_fields_as_unset():
    pool = parse_pool_data(build_pool_data(mayhem=True)[:243])
    assert pool["is_mayhem_mode"] is False
    assert pool["virtual_quote_reserves"] == 0


def test_global_config_offsets():
    config = parse_global_config(
        build_global_config_data(lp_bps=20, protocol_bps=5, creator_bps=7)
    )
    assert (config["lp_fee_bps"], config["protocol_fee_bps"], config["coin_creator_fee_bps"]) == (
        20,
        5,
        7,
    )
    assert config["protocol_fee_recipients"] == PROTOCOL_RECIPIENTS
    assert config["reserved_fee_recipient"] == RESERVED_RECIPIENT
    assert config["buyback_fee_recipients"] == BUYBACK_RECIPIENTS


@pytest.mark.parametrize("mayhem", [False, True])
def test_fee_recipients(mayhem):
    config = parse_global_config(build_global_config_data())
    fee, buyback = pick_fee_recipients(config, mayhem)
    if mayhem:
        assert fee == RESERVED_RECIPIENT
    else:
        assert fee in PROTOCOL_RECIPIENTS
    assert buyback in BUYBACK_RECIPIENTS


def test_pool_price_uses_both_decimals():
    assert pool_price(1_000_000, 2_000_000_000, 6, 9) == pytest.approx(2.0)
    assert pool_price(1_000_000_000, 2_000_000, 9, 6) == pytest.approx(2.0)
    assert pool_price(0, 1, 6, 9) == 0.0
