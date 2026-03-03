import asyncio
import json
import math
from unittest.mock import AsyncMock, patch

import pytest
from solders.keypair import Keypair

from pumpfun_cli.core.wallet import (
    create_wallet,
    export_wallet,
    import_wallet,
    transfer_token,
)


def test_create_wallet(tmp_path):
    result = create_wallet("testpass", str(tmp_path / "wallet.enc"))
    assert "pubkey" in result
    assert (tmp_path / "wallet.enc").exists()


def test_import_wallet(tmp_path):
    kp = Keypair()
    keypair_path = tmp_path / "keypair.json"
    keypair_path.write_text(json.dumps(list(bytes(kp))))
    result = import_wallet(str(keypair_path), "testpass", str(tmp_path / "wallet.enc"))
    assert result["pubkey"] == str(kp.pubkey())


def test_export_wallet(tmp_path):
    create_wallet("testpass", str(tmp_path / "wallet.enc"))
    export_path = tmp_path / "exported.json"
    export_wallet(str(tmp_path / "wallet.enc"), "testpass", str(export_path))
    data = json.loads(export_path.read_text())
    assert isinstance(data, list)
    assert len(data) == 64


def test_transfer_token_function_exists():
    import inspect

    sig = inspect.signature(transfer_token)
    params = list(sig.parameters.keys())
    assert "rpc_url" in params
    assert "mint_str" in params
    assert "amount_str" in params


def test_create_wallet_refuses_overwrite_by_default(tmp_path):
    """Existing wallet + no force → error dict with existing_pubkey."""
    keystore = str(tmp_path / "wallet.enc")
    first = create_wallet("testpass", keystore)
    result = create_wallet("testpass", keystore)
    assert result["error"] == "wallet_exists"
    assert "existing_pubkey" in result
    assert result["existing_pubkey"] == first["pubkey"]


def test_create_wallet_force_overwrites(tmp_path):
    """Existing wallet + force=True → succeeds with different pubkey."""
    keystore = str(tmp_path / "wallet.enc")
    first = create_wallet("testpass", keystore)
    second = create_wallet("testpass", keystore, force=True)
    assert "pubkey" in second
    assert first["pubkey"] != second["pubkey"]
    assert (tmp_path / "wallet.enc").exists()


def test_create_wallet_force_noop_when_no_file(tmp_path):
    """No file + force=True → succeeds normally."""
    keystore = str(tmp_path / "wallet.enc")
    result = create_wallet("testpass", keystore, force=True)
    assert "pubkey" in result
    assert (tmp_path / "wallet.enc").exists()


def test_create_wallet_existing_corrupted_file(tmp_path):
    """Corrupted file + no force → error dict with 'unknown (file unreadable)'."""
    keystore = tmp_path / "wallet.enc"
    keystore.write_text("corrupted garbage data")
    result = create_wallet("testpass", str(keystore))
    assert result["error"] == "wallet_exists"
    assert result["existing_pubkey"] == "unknown (file unreadable)"


def test_import_wallet_refuses_overwrite_by_default(tmp_path):
    """Existing wallet + no force → error dict."""
    keystore = str(tmp_path / "wallet.enc")
    create_wallet("testpass", keystore, force=True)
    # Re-read the pubkey from the file
    from pathlib import Path

    from pumpfun_cli.crypto import get_pubkey

    existing_pubkey = get_pubkey(Path(keystore))

    kp = Keypair()
    keypair_path = tmp_path / "keypair.json"
    keypair_path.write_text(json.dumps(list(bytes(kp))))

    result = import_wallet(str(keypair_path), "testpass", keystore)
    assert result["error"] == "wallet_exists"
    assert result["existing_pubkey"] == existing_pubkey


def test_import_wallet_force_overwrites(tmp_path):
    """Existing wallet + force=True → succeeds."""
    keystore = str(tmp_path / "wallet.enc")
    create_wallet("testpass", keystore, force=True)

    kp = Keypair()
    keypair_path = tmp_path / "keypair.json"
    keypair_path.write_text(json.dumps(list(bytes(kp))))

    result = import_wallet(str(keypair_path), "testpass", keystore, force=True)
    assert result["pubkey"] == str(kp.pubkey())


def test_transfer_token_has_confirm_param():
    import inspect

    sig = inspect.signature(transfer_token)
    assert "confirm" in sig.parameters
    assert sig.parameters["confirm"].default is False


# --- invalid pubkey tests ---


def test_get_balance_invalid_pubkey():
    """Invalid pubkey returns error dict without RPC calls."""

    from pumpfun_cli.core.wallet import get_balance

    result = asyncio.run(get_balance("http://rpc", "invalidpubkey"))
    assert result["error"] == "invalid_address"
    assert "invalidpubkey" in result["message"]


def test_list_token_accounts_invalid_pubkey():
    """Invalid pubkey returns error dict without RPC calls."""

    from pumpfun_cli.core.wallet import list_token_accounts

    result = asyncio.run(list_token_accounts("http://rpc", "invalidpubkey"))
    assert result["error"] == "invalid_address"
    assert "invalidpubkey" in result["message"]


def test_transfer_sol_invalid_recipient(tmp_path):
    """Invalid recipient returns error dict without RPC calls."""

    from pumpfun_cli.core.wallet import transfer_sol
    from pumpfun_cli.crypto import encrypt_keypair

    kp = Keypair()
    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass", keyfile)

    result = asyncio.run(
        transfer_sol("http://rpc", str(keyfile), "testpass", "invalidrecipient", 1.0)
    )
    assert result["error"] == "invalid_address"
    assert "invalidrecipient" in result["message"]


def test_transfer_token_invalid_recipient(tmp_path):
    """Invalid recipient returns error dict without RPC calls."""

    from pumpfun_cli.core.wallet import transfer_token
    from pumpfun_cli.crypto import encrypt_keypair

    kp = Keypair()
    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass", keyfile)

    result = asyncio.run(
        transfer_token(
            "http://rpc",
            str(keyfile),
            "testpass",
            "invalidrecipient",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "1.0",
        )
    )
    assert result["error"] == "invalid_address"
    assert "invalidrecipient" in result["message"]


# --- BUG-13: transfer_all_sol tests ---


@pytest.mark.asyncio
async def test_transfer_all_sol_sends_balance_minus_fees(tmp_path):
    """Balance of 1 SOL → sends balance minus fees."""
    from pumpfun_cli.core.wallet import transfer_all_sol
    from pumpfun_cli.crypto import encrypt_keypair
    from pumpfun_cli.protocol.contracts import BASE_TX_FEE

    kp = Keypair()
    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass", keyfile)

    balance = 1_000_000_000  # 1 SOL
    default_priority = 200_000
    default_cu = 100_000
    expected_fees = BASE_TX_FEE + math.ceil(default_priority * default_cu / 1_000_000)
    expected_lamports = balance - expected_fees

    mock_client = AsyncMock()
    mock_client.get_balance.return_value = balance
    mock_client.send_tx.return_value = "fakesig123"
    mock_client.close.return_value = None

    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=mock_client):
        result = await transfer_all_sol(
            "http://rpc",
            str(keyfile),
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        )

    assert result["action"] == "transfer"
    assert result["sol_amount"] == expected_lamports / 1_000_000_000
    assert result["signature"] == "fakesig123"
    # Verify the system transfer instruction used the right lamports
    call_args = mock_client.send_tx.call_args
    assert call_args is not None


@pytest.mark.asyncio
async def test_transfer_all_sol_insufficient_balance(tmp_path):
    """Balance too low to cover fees → returns error dict."""
    from pumpfun_cli.core.wallet import transfer_all_sol
    from pumpfun_cli.crypto import encrypt_keypair

    kp = Keypair()
    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass", keyfile)

    mock_client = AsyncMock()
    mock_client.get_balance.return_value = 10_000  # too low
    mock_client.close.return_value = None

    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=mock_client):
        result = await transfer_all_sol(
            "http://rpc",
            str(keyfile),
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        )

    assert result["error"] == "insufficient_balance"


@pytest.mark.asyncio
async def test_transfer_all_sol_zero_balance(tmp_path):
    """Zero balance → returns error dict."""
    from pumpfun_cli.core.wallet import transfer_all_sol
    from pumpfun_cli.crypto import encrypt_keypair

    kp = Keypair()
    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass", keyfile)

    mock_client = AsyncMock()
    mock_client.get_balance.return_value = 0
    mock_client.close.return_value = None

    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=mock_client):
        result = await transfer_all_sol(
            "http://rpc",
            str(keyfile),
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        )

    assert result["error"] == "insufficient_balance"


@pytest.mark.asyncio
async def test_transfer_all_sol_custom_priority_fee(tmp_path):
    """Custom priority fee and compute units → correct fee deduction."""
    from pumpfun_cli.core.wallet import transfer_all_sol
    from pumpfun_cli.crypto import encrypt_keypair
    from pumpfun_cli.protocol.contracts import BASE_TX_FEE

    kp = Keypair()
    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass", keyfile)

    balance = 500_000_000  # 0.5 SOL
    priority = 500_000
    cu = 200_000
    expected_fees = BASE_TX_FEE + math.ceil(priority * cu / 1_000_000)
    expected_lamports = balance - expected_fees

    mock_client = AsyncMock()
    mock_client.get_balance.return_value = balance
    mock_client.send_tx.return_value = "customsig"
    mock_client.close.return_value = None

    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=mock_client):
        result = await transfer_all_sol(
            "http://rpc",
            str(keyfile),
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            priority_fee=priority,
            compute_units=cu,
        )

    assert result["sol_amount"] == expected_lamports / 1_000_000_000
    assert result["signature"] == "customsig"


@pytest.mark.asyncio
async def test_transfer_all_sol_invalid_recipient(tmp_path):
    """Invalid recipient → returns error dict without RPC calls."""
    from pumpfun_cli.core.wallet import transfer_all_sol
    from pumpfun_cli.crypto import encrypt_keypair

    kp = Keypair()
    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass", keyfile)

    result = await transfer_all_sol(
        "http://rpc",
        str(keyfile),
        "testpass",
        "invalidrecipient",
    )

    assert result["error"] == "invalid_address"
    assert "invalidrecipient" in result["message"]


@pytest.mark.asyncio
async def test_transfer_all_sol_confirms(tmp_path):
    """confirm=True → result has 'confirmed': True."""
    from pumpfun_cli.core.wallet import transfer_all_sol
    from pumpfun_cli.crypto import encrypt_keypair

    kp = Keypair()
    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass", keyfile)

    mock_client = AsyncMock()
    mock_client.get_balance.return_value = 1_000_000_000
    mock_client.send_tx.return_value = "confirmedsig"
    mock_client.close.return_value = None

    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=mock_client):
        result = await transfer_all_sol(
            "http://rpc",
            str(keyfile),
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            confirm=True,
        )

    assert result["confirmed"] is True
    assert result["signature"] == "confirmedsig"


# --- BUG-11: commitment parameter tests ---


@pytest.mark.asyncio
async def test_get_balance_passes_commitment():
    """Default commitment='confirmed' is passed to client.get_balance."""
    from pumpfun_cli.core.wallet import get_balance

    mock_client = AsyncMock()
    mock_client.get_balance.return_value = 1_000_000_000
    mock_client.close.return_value = None

    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=mock_client):
        result = await get_balance("http://rpc", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

    assert result["sol_balance"] == 1.0
    mock_client.get_balance.assert_called_once()
    call_kwargs = mock_client.get_balance.call_args
    assert call_kwargs.kwargs.get("commitment") == "confirmed"


@pytest.mark.asyncio
async def test_get_balance_custom_commitment():
    """Explicit commitment='finalized' is passed through."""
    from pumpfun_cli.core.wallet import get_balance

    mock_client = AsyncMock()
    mock_client.get_balance.return_value = 500_000_000
    mock_client.close.return_value = None

    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=mock_client):
        result = await get_balance(
            "http://rpc",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            commitment="finalized",
        )

    assert result["sol_balance"] == 0.5
    call_kwargs = mock_client.get_balance.call_args
    assert call_kwargs.kwargs.get("commitment") == "finalized"


@pytest.mark.asyncio
async def test_list_token_accounts_passes_commitment():
    """Both get_token_accounts_by_owner calls receive commitment."""
    from pumpfun_cli.core.wallet import list_token_accounts

    mock_client = AsyncMock()
    mock_client.get_token_accounts_by_owner.return_value = []
    mock_client.close.return_value = None

    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=mock_client):
        await list_token_accounts("http://rpc", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

    assert mock_client.get_token_accounts_by_owner.call_count == 2
    for call in mock_client.get_token_accounts_by_owner.call_args_list:
        assert call.kwargs.get("commitment") == "confirmed"


# --- BUG-12: zero-balance filtering tests ---


@pytest.mark.asyncio
async def test_list_token_accounts_filters_zero_balance():
    """show_empty=False filters out amount==0 accounts."""
    from pumpfun_cli.core.wallet import list_token_accounts

    mock_client = AsyncMock()
    mock_client.get_token_accounts_by_owner.side_effect = [
        [
            {"address": "A", "mint": "M1", "amount": 100, "program": "P1"},
            {"address": "B", "mint": "M2", "amount": 0, "program": "P1"},
        ],
        [
            {"address": "C", "mint": "M3", "amount": 0, "program": "P2"},
        ],
    ]
    mock_client.close.return_value = None

    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=mock_client):
        result = await list_token_accounts(
            "http://rpc",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            show_empty=False,
        )

    accounts = result["token_accounts"]
    assert len(accounts) == 1
    assert accounts[0]["address"] == "A"


@pytest.mark.asyncio
async def test_list_token_accounts_show_empty_true():
    """show_empty=True returns all accounts including zero-balance."""
    from pumpfun_cli.core.wallet import list_token_accounts

    mock_client = AsyncMock()
    mock_client.get_token_accounts_by_owner.side_effect = [
        [
            {"address": "A", "mint": "M1", "amount": 100, "program": "P1"},
            {"address": "B", "mint": "M2", "amount": 0, "program": "P1"},
        ],
        [],
    ]
    mock_client.close.return_value = None

    with patch("pumpfun_cli.protocol.client.RpcClient", return_value=mock_client):
        result = await list_token_accounts(
            "http://rpc",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            show_empty=True,
        )

    accounts = result["token_accounts"]
    assert len(accounts) == 2


def test_transfer_token_invalid_mint(tmp_path):
    """Invalid mint returns error dict without RPC calls."""

    from pumpfun_cli.core.wallet import transfer_token
    from pumpfun_cli.crypto import encrypt_keypair

    kp = Keypair()
    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass", keyfile)

    result = asyncio.run(
        transfer_token(
            "http://rpc",
            str(keyfile),
            "testpass",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "invalidmint",
            "1.0",
        )
    )
    assert result["error"] == "invalid_address"
    assert "invalidmint" in result["message"]


# --- BUG-14: drain_wallet tests ---


def _make_keyfile(tmp_path, password="testpass"):
    """Helper: create encrypted wallet, return (keyfile_path, pubkey_str)."""
    from pumpfun_cli.crypto import encrypt_keypair

    kp = Keypair()
    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(kp, password, keyfile)
    return str(keyfile), str(kp.pubkey())


@pytest.mark.asyncio
async def test_drain_wallet_happy_path(tmp_path):
    """All steps succeed: close ATAs, transfer SOL."""
    from pumpfun_cli.core.wallet import drain_wallet

    keyfile, pubkey = _make_keyfile(tmp_path)

    with (
        patch(
            "pumpfun_cli.core.wallet.list_token_accounts",
            new_callable=AsyncMock,
            return_value={"pubkey": pubkey, "token_accounts": []},
        ),
        patch(
            "pumpfun_cli.core.wallet.close_empty_atas",
            new_callable=AsyncMock,
            return_value={"closed": 3, "recovered_sol": 0.006118, "signature": "atasig"},
        ),
        patch(
            "pumpfun_cli.core.wallet.transfer_all_sol",
            new_callable=AsyncMock,
            return_value={
                "action": "transfer",
                "sol_amount": 0.99,
                "signature": "solsig",
            },
        ),
    ):
        result = await drain_wallet(
            "http://rpc", keyfile, "testpass", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )

    assert result["action"] == "drain"
    assert result["atas_closed"] == 3
    assert result["sol_transferred"] == 0.99
    assert result["ata_signature"] == "atasig"
    assert result["sol_signature"] == "solsig"
    assert result["non_empty_token_accounts"] == []
    assert result.get("ata_error") is None
    assert result.get("sol_error") is None


@pytest.mark.asyncio
async def test_drain_wallet_warns_non_empty_tokens(tmp_path):
    """Non-empty token accounts are reported but drain still proceeds."""
    from pumpfun_cli.core.wallet import drain_wallet

    keyfile, pubkey = _make_keyfile(tmp_path)
    non_empty = [
        {"mint": "TokenA", "amount": 1000},
        {"mint": "TokenB", "amount": 500},
    ]

    with (
        patch(
            "pumpfun_cli.core.wallet.list_token_accounts",
            new_callable=AsyncMock,
            return_value={"pubkey": pubkey, "token_accounts": non_empty},
        ),
        patch(
            "pumpfun_cli.core.wallet.close_empty_atas",
            new_callable=AsyncMock,
            return_value={"closed": 0, "recovered_sol": 0.0, "signature": None},
        ),
        patch(
            "pumpfun_cli.core.wallet.transfer_all_sol",
            new_callable=AsyncMock,
            return_value={"action": "transfer", "sol_amount": 0.5, "signature": "sig1"},
        ),
    ):
        result = await drain_wallet(
            "http://rpc", keyfile, "testpass", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )

    assert len(result["non_empty_token_accounts"]) == 2
    assert result["sol_transferred"] == 0.5


@pytest.mark.asyncio
async def test_drain_wallet_no_empty_atas(tmp_path):
    """No empty ATAs to close, SOL transfer still happens."""
    from pumpfun_cli.core.wallet import drain_wallet

    keyfile, pubkey = _make_keyfile(tmp_path)

    with (
        patch(
            "pumpfun_cli.core.wallet.list_token_accounts",
            new_callable=AsyncMock,
            return_value={"pubkey": pubkey, "token_accounts": []},
        ),
        patch(
            "pumpfun_cli.core.wallet.close_empty_atas",
            new_callable=AsyncMock,
            return_value={"closed": 0, "recovered_sol": 0.0, "signature": None},
        ),
        patch(
            "pumpfun_cli.core.wallet.transfer_all_sol",
            new_callable=AsyncMock,
            return_value={"action": "transfer", "sol_amount": 1.0, "signature": "solsig2"},
        ),
    ):
        result = await drain_wallet(
            "http://rpc", keyfile, "testpass", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )

    assert result["atas_closed"] == 0
    assert result["sol_transferred"] == 1.0
    assert result["sol_signature"] == "solsig2"


@pytest.mark.asyncio
async def test_drain_wallet_ata_close_fails_sol_still_transfers(tmp_path):
    """ATA close raises exception, but SOL transfer still proceeds."""
    from pumpfun_cli.core.wallet import drain_wallet

    keyfile, pubkey = _make_keyfile(tmp_path)

    with (
        patch(
            "pumpfun_cli.core.wallet.list_token_accounts",
            new_callable=AsyncMock,
            return_value={"pubkey": pubkey, "token_accounts": []},
        ),
        patch(
            "pumpfun_cli.core.wallet.close_empty_atas",
            new_callable=AsyncMock,
            side_effect=Exception("RPC timeout"),
        ),
        patch(
            "pumpfun_cli.core.wallet.transfer_all_sol",
            new_callable=AsyncMock,
            return_value={"action": "transfer", "sol_amount": 0.8, "signature": "solsig3"},
        ),
    ):
        result = await drain_wallet(
            "http://rpc", keyfile, "testpass", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )

    assert result["ata_error"] == "RPC timeout"
    assert result["sol_transferred"] == 0.8
    assert result["sol_signature"] == "solsig3"


@pytest.mark.asyncio
async def test_drain_wallet_zero_sol_after_atas(tmp_path):
    """SOL transfer returns error (insufficient balance), ATAs still closed."""
    from pumpfun_cli.core.wallet import drain_wallet

    keyfile, pubkey = _make_keyfile(tmp_path)

    with (
        patch(
            "pumpfun_cli.core.wallet.list_token_accounts",
            new_callable=AsyncMock,
            return_value={"pubkey": pubkey, "token_accounts": []},
        ),
        patch(
            "pumpfun_cli.core.wallet.close_empty_atas",
            new_callable=AsyncMock,
            return_value={"closed": 2, "recovered_sol": 0.004, "signature": "atasig2"},
        ),
        patch(
            "pumpfun_cli.core.wallet.transfer_all_sol",
            new_callable=AsyncMock,
            return_value={"error": "insufficient_balance", "message": "Balance too low."},
        ),
    ):
        result = await drain_wallet(
            "http://rpc", keyfile, "testpass", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )

    assert result["atas_closed"] == 2
    assert result["sol_error"] == "insufficient_balance"
    assert result["sol_transferred"] == 0


@pytest.mark.asyncio
async def test_drain_wallet_invalid_recipient(tmp_path):
    """Invalid recipient returns error dict."""
    from pumpfun_cli.core.wallet import drain_wallet

    keyfile, _pubkey = _make_keyfile(tmp_path)

    result = await drain_wallet("http://rpc", keyfile, "testpass", "invalidrecipient")

    assert result["error"] == "invalid_address"


@pytest.mark.asyncio
async def test_drain_wallet_self_transfer_rejected(tmp_path):
    """Cannot drain wallet to itself."""
    from pumpfun_cli.core.wallet import drain_wallet

    keyfile, pubkey = _make_keyfile(tmp_path)

    result = await drain_wallet("http://rpc", keyfile, "testpass", pubkey)

    assert result["error"] == "self_transfer"
    assert "itself" in result["message"].lower()


def test_drain_wallet_wrong_password(tmp_path):
    """Wrong password raises ValueError."""
    from pumpfun_cli.core.wallet import drain_wallet

    keyfile, _pubkey = _make_keyfile(tmp_path)

    with pytest.raises(ValueError):
        asyncio.run(
            drain_wallet(
                "http://rpc", keyfile, "wrongpass", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            )
        )
