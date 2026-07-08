"""
Envelope encryption for uploaded documents at rest — master key in Nebius KMS.

Threat: raw uploaded business documents (invoices, payroll, bank confirmations)
sit in Object Storage as the most sensitive data Archon holds. This module
encrypts each raw document with a per-object data key (DEK), and wraps that DEK
with a long-lived Key-Encryption-Key (KEK) that lives **inside Nebius KMS** —
classic envelope encryption, with the KEK never leaving the key service.

Key custody — Nebius KMS (Key Management Service):
  Nebius KMS (preview) provides symmetric AES-256-GCM keys with server-side
  ``Encrypt`` / ``Decrypt`` (and ``GenerateDataKey``) plus default 3-month
  automatic key rotation. The KEK is a KMS symmetric key identified by
  ``DOC_ENCRYPTION_KMS_KEY_ID``; the raw key bytes never leave KMS. Archon holds
  only KMS *ciphertext* of each per-object DEK. We call KMS to wrap/unwrap that
  small DEK (one KMS round-trip per document — the document body itself is
  encrypted locally with AES-256-GCM, so there is no per-byte network cost).

  (Correcting the earlier design note: Nebius **does** expose a crypto KMS with
  server-side symmetric Encrypt/Decrypt — ``nebius.api.nebius.kms.v1``'s
  ``SymmetricCryptoServiceClient``, reached with the same service-account
  credentials the pipeline already uses for JobService. The previous claim that
  "Nebius does not expose a crypto-KMS" and the local ``DOC_ENCRYPTION_KEK`` env
  key it justified were wrong and have been removed.)

WRITE (encrypt):
  generate a fresh random 256-bit DEK locally → AES-256-GCM encrypt the document
  with the DEK → call **KMS Encrypt** to wrap ONLY the small DEK → store a
  self-describing envelope. The wrapped DEK is a KMS ciphertext (variable length,
  so a u16 length prefix precedes it; KMS manages its own nonces internally).

READ (decrypt):
  parse the envelope → call **KMS Decrypt** to unwrap the DEK → AES-256-GCM
  decrypt the document body locally.

Design invariants (so this can never break the live pipeline):
  * WRITE is flag-gated: bytes are encrypted only when ``DOC_ENCRYPTION_ENABLED``
    is truthy AND a KMS key id is configured. Otherwise ``maybe_encrypt`` is an
    exact passthrough. ``encryption_enabled()`` is network-free (env only) — it
    runs on every upload and must never make a KMS call.
  * READ is self-describing: ``maybe_decrypt`` decrypts iff the blob carries the
    envelope magic header — regardless of the flag. Plaintext (legacy / flag-off)
    objects pass straight through. This makes the two sides independently safe.
  * ``nebius`` is imported lazily, only inside the KMS seam — so flag-off never
    imports it and the module loads regardless of image contents.

The envelope blob is a compact, self-describing binary (format v2, KMS-wrapped):
    MAGIC(8) | wrapped_dek_len(u16 BE) | wrapped_dek(N) | dek_nonce(12) |
    ciphertext(rest)

MAGIC is ``ARCHENV2`` — bumped from the retired v1 local-KEK format so the two
formats can never be confused. Only the v2 (KMS) read path is implemented.
"""

from __future__ import annotations

import base64
import os
import struct
import tempfile
import threading

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"ARCHENV2"          # Archon envelope, format v2 (KMS-wrapped DEK)
_NONCE_LEN = 12             # AES-GCM standard nonce
_KEY_LEN = 32              # AES-256 DEK
_HEADER = struct.Struct(">H")  # wrapped-DEK length prefix (unsigned 16-bit BE)


class DocEncryptionError(RuntimeError):
    """Raised when an encrypted blob is present but cannot be decrypted."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _kms_key_id() -> str | None:
    """The KMS symmetric-key id used to wrap/unwrap DEKs, or None if unset."""
    kid = os.getenv("DOC_ENCRYPTION_KMS_KEY_ID", "").strip()
    return kid or None


def encryption_enabled() -> bool:
    """WRITE-side gate: encrypt new uploads only when explicitly enabled + keyed.

    Network-free by construction — checks env only, never calls KMS.
    """
    return _truthy(os.getenv("DOC_ENCRYPTION_ENABLED")) and _kms_key_id() is not None


def is_encrypted(blob: bytes) -> bool:
    """True iff the blob is an Archon envelope (self-describing magic header)."""
    return len(blob) >= len(MAGIC) and blob[: len(MAGIC)] == MAGIC


# ── Nebius KMS seam ───────────────────────────────────────────────────────────
# The only code that touches the Nebius SDK. Kept thin and network-only so the
# rest of the module is exercised offline via injected wrap/unwrap callables.
# ``nebius`` is imported lazily here so the flag-off path never imports it.

_SA_KEY_PATH = None
_SA_KEY_LOCK = threading.Lock()


def _sa_key_path(sa_key_b64: str) -> str:  # pragma: no cover - writes the SA PEM once
    """Return the path to the SA private-key PEM, writing it at most once."""
    global _SA_KEY_PATH
    if _SA_KEY_PATH is None:
        with _SA_KEY_LOCK:
            if _SA_KEY_PATH is None:
                pem = base64.b64decode(sa_key_b64).decode()
                tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
                tmp.write(pem)
                tmp.flush()
                tmp.close()
                _SA_KEY_PATH = tmp.name
    return _SA_KEY_PATH


def _make_sdk():  # pragma: no cover - constructs a live Nebius SDK
    """Return a Nebius SDK instance for KMS calls.

    Prefers service-account credentials (NEBIUS_SA_KEY_B64 + NEBIUS_SA_KEY_ID +
    NEBIUS_SA_ID) — the same auth the backend already uses for JobService. Falls
    back to NEBIUS_IAM_TOKEN (12-hour session token) for local dev.
    """
    from nebius.sdk import SDK

    sa_key_b64 = os.getenv("NEBIUS_SA_KEY_B64")
    sa_key_id = os.getenv("NEBIUS_SA_KEY_ID")
    sa_id = os.getenv("NEBIUS_SA_ID")

    if sa_key_b64 and sa_key_id and sa_id:
        return SDK(
            service_account_private_key_file_name=_sa_key_path(sa_key_b64),
            service_account_public_key_id=sa_key_id,
            service_account_id=sa_id,
        )
    return SDK()


def _kms_wrap(dek: bytes, key_id: str) -> bytes:  # pragma: no cover - live KMS Encrypt
    """Wrap a DEK with the KMS symmetric key (server-side Encrypt). Returns KMS ciphertext."""
    from nebius.api.nebius.kms.v1 import SymmetricCryptoServiceClient, SymmetricEncryptRequest

    sdk = _make_sdk()
    try:
        resp = SymmetricCryptoServiceClient(sdk).encrypt(
            SymmetricEncryptRequest(key_id=key_id, plaintext=dek, aad_context=MAGIC)
        ).wait()
        return resp.ciphertext
    finally:
        sdk.sync_close()


def _kms_unwrap(wrapped_dek: bytes, key_id: str) -> bytes:  # pragma: no cover - live KMS Decrypt
    """Unwrap a KMS-wrapped DEK (server-side Decrypt). Returns the plaintext DEK."""
    from nebius.api.nebius.kms.v1 import SymmetricCryptoServiceClient, SymmetricDecryptRequest

    sdk = _make_sdk()
    try:
        resp = SymmetricCryptoServiceClient(sdk).decrypt(
            SymmetricDecryptRequest(key_id=key_id, ciphertext=wrapped_dek, aad_context=MAGIC)
        ).wait()
        return resp.plaintext
    finally:
        sdk.sync_close()


def encrypt(plaintext: bytes, key_id: str | None = None, wrap=None) -> bytes:
    """Envelope-encrypt bytes: fresh per-object DEK, DEK wrapped by KMS.

    ``wrap`` is the DEK-wrapping seam (``dek -> wrapped_dek``); it defaults to a
    live KMS Encrypt against ``key_id`` (or ``DOC_ENCRYPTION_KMS_KEY_ID``). Tests
    inject a local fake to exercise the full envelope offline.
    """
    key_id = key_id or _kms_key_id()
    if wrap is None:
        if key_id is None:
            raise DocEncryptionError(
                "no KMS key configured (set DOC_ENCRYPTION_KMS_KEY_ID)"
            )
        wrap = lambda dek: _kms_wrap(dek, key_id)  # noqa: E731
    dek = os.urandom(_KEY_LEN)
    dek_nonce = os.urandom(_NONCE_LEN)
    wrapped_dek = wrap(dek)
    ciphertext = AESGCM(dek).encrypt(dek_nonce, plaintext, MAGIC)
    return b"".join([
        MAGIC,
        _HEADER.pack(len(wrapped_dek)),
        wrapped_dek,
        dek_nonce,
        ciphertext,
    ])


def decrypt(blob: bytes, key_id: str | None = None, unwrap=None) -> bytes:
    """Decrypt an Archon v2 envelope produced by :func:`encrypt`.

    ``unwrap`` is the DEK-unwrapping seam (``wrapped_dek -> dek``); it defaults to
    a live KMS Decrypt against ``key_id`` (or ``DOC_ENCRYPTION_KMS_KEY_ID``).
    """
    if not is_encrypted(blob):
        raise DocEncryptionError("not an Archon envelope (missing magic header)")
    key_id = key_id or _kms_key_id()
    if unwrap is None:
        if key_id is None:
            raise DocEncryptionError(
                "encrypted object present but no KMS key configured "
                "(set DOC_ENCRYPTION_KMS_KEY_ID)"
            )
        unwrap = lambda w: _kms_unwrap(w, key_id)  # noqa: E731
    try:
        pos = len(MAGIC)
        (wrapped_len,) = _HEADER.unpack_from(blob, pos)
        pos += _HEADER.size
        wrapped_dek = blob[pos:pos + wrapped_len]; pos += wrapped_len
        dek_nonce = blob[pos:pos + _NONCE_LEN]; pos += _NONCE_LEN
        ciphertext = blob[pos:]
        dek = unwrap(wrapped_dek)
        return AESGCM(dek).decrypt(dek_nonce, ciphertext, MAGIC)
    except DocEncryptionError:
        raise
    except Exception as exc:  # KMS/GCM raise InvalidTag, RpcError, etc. — normalise
        raise DocEncryptionError(f"decryption failed: {type(exc).__name__}") from exc


def maybe_encrypt(plaintext: bytes) -> bytes:
    """WRITE path: encrypt iff enabled + keyed, else return plaintext unchanged."""
    return encrypt(plaintext) if encryption_enabled() else plaintext


def maybe_decrypt(blob: bytes) -> bytes:
    """READ path: decrypt iff the blob is an envelope, else return it unchanged.

    Transparent + backward-compatible: legacy plaintext objects and flag-off
    writes pass straight through; only genuine envelopes are unwrapped (which
    requires KMS access — a configuration error surfaces loudly, never silently).
    """
    return decrypt(blob) if is_encrypted(blob) else blob
