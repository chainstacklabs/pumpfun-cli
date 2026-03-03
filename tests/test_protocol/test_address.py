from solders.pubkey import Pubkey

from pumpfun_cli.protocol.address import (
    derive_bonding_curve,
    derive_bonding_curve_v2,
    derive_creator_vault,
)


def test_bonding_curve_is_deterministic():
    mint = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    assert derive_bonding_curve(mint) == derive_bonding_curve(mint)


def test_bonding_curve_v2_differs_from_v1():
    mint = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    assert derive_bonding_curve(mint) != derive_bonding_curve_v2(mint)


def test_creator_vault_deterministic():
    user = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    assert derive_creator_vault(user) == derive_creator_vault(user)
