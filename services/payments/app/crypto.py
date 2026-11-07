"""Encryption at rest for suppliers' Paynow integration keys."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretBox:
    def __init__(self, secret: str):
        try:
            self._f = Fernet(secret.encode())
        except ValueError:  # any passphrase works in development; production must use a real Fernet key
            self._f = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))

    def encrypt(self, value: str) -> str:
        return self._f.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._f.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Stored Paynow key can't be decrypted (was PAYMENTS_SECRET_KEY changed?)") from exc


def mask(value: str | None) -> str | None:
    if not value:
        return None
    return "•" * max(len(value) - 4, 4) + value[-4:]
