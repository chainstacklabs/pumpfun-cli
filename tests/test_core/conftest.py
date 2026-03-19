"""Shared fixtures for core tests."""

import pytest
from solders.keypair import Keypair

from pumpfun_cli.crypto import encrypt_keypair


@pytest.fixture
def mock_keypair():
    return Keypair()


@pytest.fixture
def tmp_keystore(tmp_path, mock_keypair):
    """Create an encrypted keystore file for testing."""
    keyfile = tmp_path / "wallet.enc"
    encrypt_keypair(mock_keypair, "testpass", keyfile)
    return str(keyfile)
