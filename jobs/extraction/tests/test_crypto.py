"""
Round-trip suite for document envelope encryption (jobs/extraction/crypto.py).

Offline, deterministic: uses a fixed test KEK via env, never a real key service.
Proves the three safety-critical behaviours the live pipeline depends on:
  1. encrypt -> decrypt round-trip recovers the exact bytes;
  2. READ passes plaintext through unchanged (no magic header);
  3. WRITE stays plaintext when the flag is off.
Plus KEK handling and tamper/wrong-key failure modes.
"""
import base64

import pytest

import crypto

_KEK = base64.b64encode(b"k" * 32).decode()
_OTHER_KEK = base64.b64encode(b"z" * 32).decode()
DOC = "INVOICE\nτιμολόγιο 1234,56 EUR\n".encode()  # bytes incl. non-ASCII


def _enable(monkeypatch, kek=_KEK):
    monkeypatch.setenv("DOC_ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("DOC_ENCRYPTION_KEK", kek)


def test_round_trip_recovers_exact_bytes():
    blob = crypto.encrypt(DOC, kek=base64.b64decode(_KEK))
    assert crypto.is_encrypted(blob)
    assert blob != DOC
    assert crypto.decrypt(blob, kek=base64.b64decode(_KEK)) == DOC


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
    monkeypatch.setenv("DOC_ENCRYPTION_KEK", _KEK)
    assert crypto.encryption_enabled() is False
    out = crypto.maybe_encrypt(DOC)
    assert out == DOC and not crypto.is_encrypted(out)


def test_encryption_enabled_needs_flag_and_key(monkeypatch):
    monkeypatch.setenv("DOC_ENCRYPTION_ENABLED", "true")
    monkeypatch.delenv("DOC_ENCRYPTION_KEK", raising=False)
    assert crypto.encryption_enabled() is False  # flag on but no key
    monkeypatch.setenv("DOC_ENCRYPTION_KEK", _KEK)
    assert crypto.encryption_enabled() is True


def test_each_encryption_is_unique():
    kek = base64.b64decode(_KEK)
    a, b = crypto.encrypt(DOC, kek=kek), crypto.encrypt(DOC, kek=kek)
    assert a != b  # fresh per-object DEK + nonces
    assert crypto.decrypt(a, kek=kek) == crypto.decrypt(b, kek=kek) == DOC


def test_wrong_kek_fails():
    blob = crypto.encrypt(DOC, kek=base64.b64decode(_KEK))
    with pytest.raises(crypto.DocEncryptionError):
        crypto.decrypt(blob, kek=base64.b64decode(_OTHER_KEK))


def test_tampered_ciphertext_fails():
    blob = bytearray(crypto.encrypt(DOC, kek=base64.b64decode(_KEK)))
    blob[-1] ^= 0xFF  # flip a ciphertext bit -> GCM auth failure
    with pytest.raises(crypto.DocEncryptionError):
        crypto.decrypt(bytes(blob), kek=base64.b64decode(_KEK))


def test_encrypt_without_kek_raises(monkeypatch):
    monkeypatch.delenv("DOC_ENCRYPTION_KEK", raising=False)
    with pytest.raises(crypto.DocEncryptionError):
        crypto.encrypt(DOC)


def test_bad_kek_length_raises(monkeypatch):
    monkeypatch.setenv("DOC_ENCRYPTION_KEK", base64.b64encode(b"short").decode())
    with pytest.raises(crypto.DocEncryptionError):
        crypto._load_kek()


def test_decrypt_non_envelope_raises():
    with pytest.raises(crypto.DocEncryptionError):
        crypto.decrypt(b"not an envelope")


def test_maybe_decrypt_envelope_without_kek_raises(monkeypatch):
    blob = crypto.encrypt(DOC, kek=base64.b64decode(_KEK))
    monkeypatch.delenv("DOC_ENCRYPTION_KEK", raising=False)
    with pytest.raises(crypto.DocEncryptionError):
        crypto.maybe_decrypt(blob)  # encrypted object present but no key = loud failure
