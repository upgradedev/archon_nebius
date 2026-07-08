"""
Envelope encryption for uploaded documents at rest (AES-256-GCM).

Threat: raw uploaded business documents (invoices, payroll, bank confirmations)
sit in Object Storage as the most sensitive data Archon holds. This module
encrypts each raw document with a per-object data key, and wraps that data key
with a long-lived Key-Encryption-Key (KEK) — classic envelope encryption.

Key custody: the KEK is a 256-bit secret custodied in **Nebius Secrets Manager
(MysteryBox)** and delivered to the runtime as the base64 env var
``DOC_ENCRYPTION_KEK``. (Nebius does not expose a crypto-KMS with server-side
Encrypt/Decrypt on symmetric keys via the CLI; MysteryBox is a secret store. So
the wrap/unwrap is done locally with a KEK custodied there — strictly safer for
the pipeline than a per-object network round-trip to a key service would be.)

Design invariants (so this can never break the live pipeline):
  * WRITE is flag-gated: bytes are encrypted only when ``DOC_ENCRYPTION_ENABLED``
    is truthy AND a KEK is configured. Otherwise ``maybe_encrypt`` is a passthrough.
  * READ is self-describing: ``maybe_decrypt`` decrypts iff the blob carries the
    envelope magic header — regardless of the flag. Plaintext (legacy / flag-off)
    objects pass straight through. This makes the two sides independently safe.

The envelope blob is a compact, self-describing binary:
    MAGIC(8) | wrapped_dek_len(u16 BE) | kek_nonce(12) | wrapped_dek(N) |
    dek_nonce(12) | ciphertext(rest)
"""

from __future__ import annotations

import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"ARCHENV1"          # Archon envelope, format v1
_NONCE_LEN = 12             # AES-GCM standard nonce
_KEY_LEN = 32              # AES-256
_HEADER = struct.Struct(">H")  # wrapped-DEK length prefix (unsigned 16-bit BE)


class DocEncryptionError(RuntimeError):
    """Raised when an encrypted blob is present but cannot be decrypted."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def encryption_enabled() -> bool:
    """WRITE-side gate: encrypt new uploads only when explicitly enabled + keyed."""
    return _truthy(os.getenv("DOC_ENCRYPTION_ENABLED")) and _load_kek() is not None


def _load_kek() -> bytes | None:
    """Decode the base64 KEK from env (custodied in Nebius MysteryBox). None if unset."""
    raw = os.getenv("DOC_ENCRYPTION_KEK", "").strip()
    if not raw:
        return None
    import base64
    key = base64.b64decode(raw)
    if len(key) != _KEY_LEN:
        raise DocEncryptionError(
            f"DOC_ENCRYPTION_KEK must decode to {_KEY_LEN} bytes, got {len(key)}"
        )
    return key


def is_encrypted(blob: bytes) -> bool:
    """True iff the blob is an Archon envelope (self-describing magic header)."""
    return len(blob) >= len(MAGIC) and blob[: len(MAGIC)] == MAGIC


def encrypt(plaintext: bytes, kek: bytes | None = None) -> bytes:
    """Envelope-encrypt bytes. Generates a fresh per-object DEK, wraps it with the KEK."""
    kek = kek or _load_kek()
    if kek is None:
        raise DocEncryptionError("no KEK configured (set DOC_ENCRYPTION_KEK)")
    dek = os.urandom(_KEY_LEN)
    kek_nonce = os.urandom(_NONCE_LEN)
    dek_nonce = os.urandom(_NONCE_LEN)
    wrapped_dek = AESGCM(kek).encrypt(kek_nonce, dek, MAGIC)
    ciphertext = AESGCM(dek).encrypt(dek_nonce, plaintext, MAGIC)
    return b"".join([
        MAGIC,
        _HEADER.pack(len(wrapped_dek)),
        kek_nonce,
        wrapped_dek,
        dek_nonce,
        ciphertext,
    ])


def decrypt(blob: bytes, kek: bytes | None = None) -> bytes:
    """Decrypt an Archon envelope produced by :func:`encrypt`."""
    if not is_encrypted(blob):
        raise DocEncryptionError("not an Archon envelope (missing magic header)")
    kek = kek or _load_kek()
    if kek is None:
        raise DocEncryptionError("encrypted object present but no KEK configured")
    try:
        pos = len(MAGIC)
        (wrapped_len,) = _HEADER.unpack_from(blob, pos)
        pos += _HEADER.size
        kek_nonce = blob[pos:pos + _NONCE_LEN]; pos += _NONCE_LEN
        wrapped_dek = blob[pos:pos + wrapped_len]; pos += wrapped_len
        dek_nonce = blob[pos:pos + _NONCE_LEN]; pos += _NONCE_LEN
        ciphertext = blob[pos:]
        dek = AESGCM(kek).decrypt(kek_nonce, wrapped_dek, MAGIC)
        return AESGCM(dek).decrypt(dek_nonce, ciphertext, MAGIC)
    except DocEncryptionError:
        raise
    except Exception as exc:  # cryptography raises InvalidTag etc. — normalise
        raise DocEncryptionError(f"decryption failed: {type(exc).__name__}") from exc


def maybe_encrypt(plaintext: bytes) -> bytes:
    """WRITE path: encrypt iff enabled + keyed, else return plaintext unchanged."""
    return encrypt(plaintext) if encryption_enabled() else plaintext


def maybe_decrypt(blob: bytes) -> bytes:
    """READ path: decrypt iff the blob is an envelope, else return it unchanged.

    Transparent + backward-compatible: legacy plaintext objects and flag-off
    writes pass straight through; only genuine envelopes are unwrapped (which
    requires the KEK — a configuration error surfaces loudly, never silently).
    """
    return decrypt(blob) if is_encrypted(blob) else blob
