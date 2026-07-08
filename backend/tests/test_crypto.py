"""
Round-trip suite for document envelope encryption (backend/services/crypto.py).

Offline, deterministic: the Nebius KMS Encrypt/Decrypt seam is replaced by a
local AES-256-GCM "fake KMS" wrapped with a fixed test key, so the FULL envelope
round-trip is exercised without any network call. Proves the safety-critical
behaviours the live pipeline depends on:
  1. encrypt -> decrypt round-trip recovers the exact bytes (v2 KMS envelope);
  2. READ passes plaintext through unchanged (no magic header);
  3. WRITE stays plaintext when the flag is off;
  4. self-describing read + loud failure when an envelope has no key/KMS access.
Plus wrong-key / tamper failure modes and MAGIC v2.
"""
import base64

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from services import crypto

_KMS_KEY_ID = "kms-symmetric-key-test-0001"
# Fake KMS: wrap the DEK with a local AES-256-GCM key (fixed nonce is fine for a
# test double). Variable-length output (32-byte DEK -> 48-byte wrap) exercises
# the u16 length prefix, exactly as a real KMS ciphertext would.
_FAKE_KEK = b"k" * 32
_OTHER_KEK = b"z" * 32
_FAKE_NONCE = b"\x00" * 12
DOC = "INVOICE\nτιμολόγιο 1234,56 EUR\n".encode()  # bytes incl. non-ASCII


def _fake_wrap(kek=_FAKE_KEK):
    return lambda dek: AESGCM(kek).encrypt(_FAKE_NONCE, dek, crypto.MAGIC)


def _fake_unwrap(kek=_FAKE_KEK):
    return lambda w: AESGCM(kek).decrypt(_FAKE_NONCE, w, crypto.MAGIC)


def _enable(monkeypatch, kid=_KMS_KEY_ID):
    """Turn the feature on and route the KMS seam to the local fake."""
    monkeypatch.setenv("DOC_ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("DOC_ENCRYPTION_KMS_KEY_ID", kid)
    monkeypatch.setattr(crypto, "_kms_wrap", lambda dek, key_id: _fake_wrap()(dek))
    monkeypatch.setattr(crypto, "_kms_unwrap", lambda w, key_id: _fake_unwrap()(w))


def test_round_trip_recovers_exact_bytes():
    blob = crypto.encrypt(DOC, wrap=_fake_wrap())
    assert crypto.is_encrypted(blob)
    assert blob != DOC
    assert crypto.decrypt(blob, unwrap=_fake_unwrap()) == DOC


def test_magic_is_v2():
    assert crypto.MAGIC == b"ARCHENV2"
    blob = crypto.encrypt(DOC, wrap=_fake_wrap())
    assert blob[:8] == b"ARCHENV2"


def test_round_trip_via_env(monkeypatch):
    _enable(monkeypatch)
    blob = crypto.maybe_encrypt(DOC)
    assert crypto.is_encrypted(blob)
    assert crypto.maybe_decrypt(blob) == DOC


def test_read_passes_plaintext_through(monkeypatch):
    # A legacy / flag-off object (no magic) is returned untouched on read.
    _enable(monkeypatch)  # even with the flag ON, non-envelope bytes pass through
    assert crypto.maybe_decrypt(DOC) == DOC
    assert not crypto.is_encrypted(DOC)


def test_write_stays_plaintext_when_disabled(monkeypatch):
    monkeypatch.delenv("DOC_ENCRYPTION_ENABLED", raising=False)
    monkeypatch.setenv("DOC_ENCRYPTION_KMS_KEY_ID", _KMS_KEY_ID)
    assert crypto.encryption_enabled() is False
    out = crypto.maybe_encrypt(DOC)
    assert out == DOC and not crypto.is_encrypted(out)


def test_encryption_enabled_needs_flag_and_key(monkeypatch):
    monkeypatch.setenv("DOC_ENCRYPTION_ENABLED", "true")
    monkeypatch.delenv("DOC_ENCRYPTION_KMS_KEY_ID", raising=False)
    assert crypto.encryption_enabled() is False  # flag on but no KMS key id
    monkeypatch.setenv("DOC_ENCRYPTION_KMS_KEY_ID", _KMS_KEY_ID)
    assert crypto.encryption_enabled() is True


def test_encryption_enabled_is_network_free(monkeypatch):
    # The write-side gate runs on every upload — it must never touch KMS.
    def _boom(*a, **k):
        raise AssertionError("encryption_enabled must not call KMS")

    monkeypatch.setattr(crypto, "_kms_wrap", _boom)
    monkeypatch.setattr(crypto, "_kms_unwrap", _boom)
    monkeypatch.setenv("DOC_ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("DOC_ENCRYPTION_KMS_KEY_ID", _KMS_KEY_ID)
    assert crypto.encryption_enabled() is True


def test_each_encryption_is_unique():
    a = crypto.encrypt(DOC, wrap=_fake_wrap())
    b = crypto.encrypt(DOC, wrap=_fake_wrap())
    assert a != b  # fresh per-object DEK + nonce
    assert crypto.decrypt(a, unwrap=_fake_unwrap()) == DOC
    assert crypto.decrypt(b, unwrap=_fake_unwrap()) == DOC


def test_wrong_key_fails():
    blob = crypto.encrypt(DOC, wrap=_fake_wrap())
    with pytest.raises(crypto.DocEncryptionError):
        crypto.decrypt(blob, unwrap=_fake_unwrap(_OTHER_KEK))  # KMS unwraps a bad DEK


def test_tampered_ciphertext_fails():
    blob = bytearray(crypto.encrypt(DOC, wrap=_fake_wrap()))
    blob[-1] ^= 0xFF  # flip a ciphertext bit -> GCM auth failure
    with pytest.raises(crypto.DocEncryptionError):
        crypto.decrypt(bytes(blob), unwrap=_fake_unwrap())


def test_encrypt_without_key_raises(monkeypatch):
    monkeypatch.delenv("DOC_ENCRYPTION_KMS_KEY_ID", raising=False)
    with pytest.raises(crypto.DocEncryptionError):
        crypto.encrypt(DOC)  # no key id + no injected wrap seam


def test_decrypt_non_envelope_raises():
    with pytest.raises(crypto.DocEncryptionError):
        crypto.decrypt(b"not an envelope")


def test_maybe_decrypt_envelope_without_key_raises(monkeypatch):
    blob = crypto.encrypt(DOC, wrap=_fake_wrap())
    monkeypatch.delenv("DOC_ENCRYPTION_KMS_KEY_ID", raising=False)
    with pytest.raises(crypto.DocEncryptionError):
        crypto.maybe_decrypt(blob)  # encrypted object present but no KMS key = loud failure


def test_unwrap_error_propagates_without_double_wrapping():
    # A DocEncryptionError raised by the KMS unwrap seam (e.g. key disabled /
    # access denied surfaced as our error type) must pass through unchanged, not
    # be re-wrapped as a generic "decryption failed".
    blob = crypto.encrypt(DOC, wrap=_fake_wrap())

    def _boom(_w):
        raise crypto.DocEncryptionError("kms access denied")

    with pytest.raises(crypto.DocEncryptionError, match="kms access denied"):
        crypto.decrypt(blob, unwrap=_boom)


def test_kms_key_id_reads_env(monkeypatch):
    monkeypatch.delenv("DOC_ENCRYPTION_KMS_KEY_ID", raising=False)
    assert crypto._kms_key_id() is None
    monkeypatch.setenv("DOC_ENCRYPTION_KMS_KEY_ID", "  " + _KMS_KEY_ID + "  ")
    assert crypto._kms_key_id() == _KMS_KEY_ID
