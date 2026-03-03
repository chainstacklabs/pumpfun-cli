import json

import pytest
from solders.keypair import Keypair

from pumpfun_cli.crypto import decrypt_keypair, encrypt_keypair, get_pubkey


def test_encrypt_decrypt_roundtrip(tmp_path):
    kp = Keypair()
    path = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass123", path)
    recovered = decrypt_keypair(path, "testpass123")
    assert recovered.pubkey() == kp.pubkey()


def test_wrong_password_raises(tmp_path):
    kp = Keypair()
    path = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "correct", path)
    with pytest.raises(ValueError, match="[Cc]ould not decrypt"):
        decrypt_keypair(path, "wrong")


def test_get_pubkey_no_password(tmp_path):
    kp = Keypair()
    path = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass123", path)
    pubkey = get_pubkey(path)
    assert pubkey == str(kp.pubkey())


def test_keystore_format(tmp_path):
    kp = Keypair()
    path = tmp_path / "wallet.enc"
    encrypt_keypair(kp, "testpass123", path)
    data = json.loads(path.read_text())
    assert data["version"] == 1
    assert "pubkey" in data
    assert "encrypted_key" in data
    assert data["kdf"]["algorithm"] == "scrypt"
