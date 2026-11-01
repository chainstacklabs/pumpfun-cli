"""User amounts become raw units exactly, never through a float product."""

import pytest

from pumpfun_cli.core.amounts import to_raw


@pytest.mark.parametrize(
    "amount,decimals,raw",
    [
        (0.29, 9, 290_000_000),
        (0.57, 2, 57),
        (4.35, 6, 4_350_000),
        ("0.29", 2, 29),
        ("1.5", 6, 1_500_000),
        (1e-9, 9, 1),
        ("0.0000001", 6, 0),
        (0, 9, 0),
    ],
)
def test_to_raw(amount, decimals, raw):
    assert to_raw(amount, decimals) == raw


def test_float_product_would_have_lost_a_unit():
    assert int(0.57 * 10**2) == 56
