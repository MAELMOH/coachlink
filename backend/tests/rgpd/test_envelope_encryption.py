"""Envelope encryption of the 🔒 columns (ARCHITECTURE.md §5.1).

    "AES-256-GCM via ``cryptography``, AAD = ``f"{table}:{row_id}:{column}"`` pour empêcher
    le déplacement d'un chiffré d'une ligne à l'autre."

Three properties are tested, in increasing order of how easy they are to get wrong:

1. **Round-trip** — encrypt then decrypt gives the original. The easy one.
2. **AAD binding** — a ciphertext lifted from one row must not decrypt in another. This is
   what stops an attacker with UPDATE access from copying coach B's client's weight into
   their own row and reading it through the API. Without AAD the ciphertext is perfectly
   portable and the whole per-column scheme buys much less than it appears to.
3. **Crypto-shredding** — destroying a user's DEK renders their data permanently
   unreadable. This is what makes erasure (§5.3) real rather than a flag flip.

Spec-first: the service does not exist yet.
"""

from __future__ import annotations

import pytest

from app.domain.ids import uuid7
from tests.support.pending import require_any

pytestmark = pytest.mark.rgpd

SERVICE_CANDIDATES = [
    ("app.services.crypto", "EncryptionService"),
    ("app.core.crypto", "EncryptionService"),
    ("app.services.encryption", "EncryptionService"),
]


@pytest.fixture
def crypto():
    return require_any(SERVICE_CANDIDATES)()


class TestRoundTrip:
    def test_decrypt_returns_the_original_value(self, crypto) -> None:
        user_id, row_id = uuid7(), uuid7()
        ciphertext = crypto.encrypt(
            "72.5", user_id=user_id, table="body_measurement", row_id=row_id, column="weight_kg"
        )
        plaintext = crypto.decrypt(
            ciphertext,
            user_id=user_id,
            table="body_measurement",
            row_id=row_id,
            column="weight_kg",
        )
        assert plaintext == "72.5"

    def test_ciphertext_does_not_contain_the_plaintext(self, crypto) -> None:
        """The reason the column exists: raw SQL on the table must reveal nothing."""
        user_id, row_id = uuid7(), uuid7()
        ciphertext = crypto.encrypt(
            "Rendez-vous lundi 18h",
            user_id=user_id,
            table="message",
            row_id=row_id,
            column="body",
        )
        blob = ciphertext if isinstance(ciphertext, bytes) else str(ciphertext).encode()
        assert b"Rendez-vous" not in blob
        assert b"lundi" not in blob

    def test_same_plaintext_encrypts_differently_each_time(self, crypto) -> None:
        """A fresh nonce per encryption.

        Deterministic ciphertext would let anyone with table access build a frequency map:
        equal weights produce equal blobs, and a client's plateau, or two clients sharing a
        weight, becomes readable without decrypting anything.
        """
        user_id, row_id = uuid7(), uuid7()
        kwargs = {
            "user_id": user_id,
            "table": "body_measurement",
            "row_id": row_id,
            "column": "weight_kg",
        }
        first = crypto.encrypt("72.5", **kwargs)
        second = crypto.encrypt("72.5", **kwargs)
        assert first != second, "deterministic ciphertext leaks equality between rows"

    def test_handles_unicode_and_long_values(self, crypto) -> None:
        user_id, row_id = uuid7(), uuid7()
        value = "Séance déplacée — objectif 80 kg 💪 " * 40
        kwargs = {"user_id": user_id, "table": "message", "row_id": row_id, "column": "body"}
        assert crypto.decrypt(crypto.encrypt(value, **kwargs), **kwargs) == value


class TestAadBinding:
    """The property that makes per-column encryption worth its cost."""

    def test_ciphertext_moved_to_another_row_fails_to_decrypt(self, crypto) -> None:
        """The headline case from §5.1, stated exactly.

        Attack it prevents: someone with write access copies the ``weight_kg`` blob from
        another coach's client into a row they legitimately own, then reads their own row
        through the API and gets the other client's weight back in clear text.
        """
        user_id = uuid7()
        source_row, target_row = uuid7(), uuid7()
        kwargs = {"user_id": user_id, "table": "body_measurement", "column": "weight_kg"}

        ciphertext = crypto.encrypt("72.5", row_id=source_row, **kwargs)

        with pytest.raises(Exception) as caught:
            crypto.decrypt(ciphertext, row_id=target_row, **kwargs)
        assert "72.5" not in str(caught.value), "the failure path echoed the plaintext"

    def test_ciphertext_moved_to_another_column_fails_to_decrypt(self, crypto) -> None:
        """Waist measurement replayed into the weight column would corrupt the chart."""
        user_id, row_id = uuid7(), uuid7()
        kwargs = {"user_id": user_id, "table": "body_measurement", "row_id": row_id}
        ciphertext = crypto.encrypt("72.5", column="waist_cm", **kwargs)
        with pytest.raises(Exception):  # noqa: B017
            crypto.decrypt(ciphertext, column="weight_kg", **kwargs)

    def test_ciphertext_moved_to_another_table_fails_to_decrypt(self, crypto) -> None:
        user_id, row_id = uuid7(), uuid7()
        ciphertext = crypto.encrypt(
            "72.5", user_id=user_id, table="body_measurement", row_id=row_id, column="weight_kg"
        )
        with pytest.raises(Exception):  # noqa: B017
            crypto.decrypt(
                ciphertext,
                user_id=user_id,
                table="nutrition_log",
                row_id=row_id,
                column="weight_kg",
            )

    def test_another_users_key_cannot_decrypt(self, crypto) -> None:
        """Per-user DEKs: coach B's key must be useless against client A's ciphertext."""
        row_id = uuid7()
        kwargs = {"table": "body_measurement", "row_id": row_id, "column": "weight_kg"}
        ciphertext = crypto.encrypt("72.5", user_id=uuid7(), **kwargs)
        with pytest.raises(Exception):  # noqa: B017
            crypto.decrypt(ciphertext, user_id=uuid7(), **kwargs)

    def test_tampered_ciphertext_is_rejected(self, crypto) -> None:
        """GCM is authenticated: a flipped bit must raise, never yield garbage."""
        user_id, row_id = uuid7(), uuid7()
        kwargs = {
            "user_id": user_id,
            "table": "body_measurement",
            "row_id": row_id,
            "column": "weight_kg",
        }
        ciphertext = crypto.encrypt("72.5", **kwargs)
        raw = bytearray(ciphertext if isinstance(ciphertext, bytes) else bytes(ciphertext))
        raw[-1] ^= 0x01
        with pytest.raises(Exception):  # noqa: B017
            crypto.decrypt(bytes(raw), **kwargs)


class TestCryptoShredding:
    """Erasure (§5.3) relies on this: destroy the DEK, the data is gone for good."""

    def test_destroying_the_key_makes_data_permanently_unreadable(self, crypto) -> None:
        user_id, row_id = uuid7(), uuid7()
        kwargs = {
            "user_id": user_id,
            "table": "body_measurement",
            "row_id": row_id,
            "column": "weight_kg",
        }
        ciphertext = crypto.encrypt("72.5", **kwargs)
        assert crypto.decrypt(ciphertext, **kwargs) == "72.5"

        crypto.destroy_user_key(user_id)

        with pytest.raises(Exception) as caught:
            crypto.decrypt(ciphertext, **kwargs)
        assert "72.5" not in str(caught.value)

    def test_destroying_one_users_key_does_not_affect_another(self, crypto) -> None:
        """A deletion request must not collaterally shred a different user's history."""
        victim, bystander = uuid7(), uuid7()
        row_id = uuid7()
        shared = {"table": "body_measurement", "row_id": row_id, "column": "weight_kg"}

        victim_blob = crypto.encrypt("72.5", user_id=victim, **shared)
        bystander_blob = crypto.encrypt("81.0", user_id=bystander, **shared)

        crypto.destroy_user_key(victim)

        assert crypto.decrypt(bystander_blob, user_id=bystander, **shared) == "81.0"
        with pytest.raises(Exception):  # noqa: B017
            crypto.decrypt(victim_blob, user_id=victim, **shared)

    def test_destroying_a_key_twice_is_idempotent(self, crypto) -> None:
        """The purge job is replayable (§5.3); a retry must not crash it."""
        user_id = uuid7()
        crypto.encrypt(
            "72.5", user_id=user_id, table="body_measurement", row_id=uuid7(), column="weight_kg"
        )
        crypto.destroy_user_key(user_id)
        crypto.destroy_user_key(user_id)


class TestKekRotation:
    """§5.1: rotating the KEK re-encrypts DEKs only — data must stay readable."""

    def test_data_survives_a_kek_rotation(self, crypto) -> None:
        rotate = getattr(crypto, "rotate_kek", None)
        if rotate is None:
            pytest.xfail("KEK rotation not implemented yet")

        user_id, row_id = uuid7(), uuid7()
        kwargs = {
            "user_id": user_id,
            "table": "body_measurement",
            "row_id": row_id,
            "column": "weight_kg",
        }
        ciphertext = crypto.encrypt("72.5", **kwargs)
        rotate()
        assert crypto.decrypt(ciphertext, **kwargs) == "72.5", (
            "KEK rotation made existing data unreadable — it must re-wrap the DEKs, not "
            "invalidate them"
        )
