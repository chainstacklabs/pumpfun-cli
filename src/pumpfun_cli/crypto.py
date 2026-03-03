"""AES-256-GCM keystore encryption with scrypt KDF."""

import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from solders.keypair import Keypair

_KDF_N = 2**18
_KDF_R = 8
_KDF_P = 1
_KEY_LEN = 32


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=_KEY_LEN, n=_KDF_N, r=_KDF_R, p=_KDF_P)
    return kdf.derive(password.encode("utf-8"))


def encrypt_keypair(keypair: Keypair, password: str, path: Path):
    salt = os.urandom(32)
    key = _derive_key(password, salt)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, bytes(keypair), None)

    keystore = {
        "version": 1,
        "pubkey": str(keypair.pubkey()),
        "encrypted_key": base64.b64encode(nonce + ciphertext).decode(),
        "kdf": {
            "algorithm": "scrypt",
            "salt": base64.b64encode(salt).decode(),
            "n": _KDF_N,
            "r": _KDF_R,
            "p": _KDF_P,
        },
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keystore, indent=2))

    if os.name != "nt":
        os.chmod(path, 0o600)


def decrypt_keypair(path: Path, password: str) -> Keypair:
    data = json.loads(Path(path).read_text())
    salt = base64.b64decode(data["kdf"]["salt"])
    key = _derive_key(password, salt)
    raw = base64.b64decode(data["encrypted_key"])
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception:
        raise ValueError("Could not decrypt wallet. Check your password.")
    return Keypair.from_bytes(plaintext)


def get_pubkey(path: Path) -> str:
    data = json.loads(Path(path).read_text())
    return data["pubkey"]
