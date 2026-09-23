"""auth + invitation escape hatches (SECURITY DEFINER)

Revision ID: 9c3d1e7b45a2
Revises: 7a1c4e2b9d30
Create Date: 2026-09-23

Why this migration exists
-------------------------
The RLS policies of ``7a1c4e2b9d30`` are fail-closed: every one of them compares
against ``current_setting('app.current_user_id')``, which is NULL before the caller
is authenticated. That is exactly what we want everywhere except in the two places
where a request legitimately has no principal *yet*:

1. **Login.** Resolving an e-mail to a password hash happens before anyone is
   authenticated, so ``user_account_select`` matches zero rows and login is simply
   impossible. Verified against a real database, not assumed.
2. **Refresh and logout.** Same shape: the caller presents an opaque refresh token
   and no access token, so there is no principal yet, and ``refresh_token_all``
   (``user_id = current_user``) hides the very row we must look up. Without this,
   every refresh answers "unknown refresh token" and sessions die after 15 minutes.
3. **Redeeming an invitation code.** ``invitation_all`` is scoped to the issuing
   coach, so the invited client can neither read the invitation nor mark it
   consumed — the whole onboarding path is unreachable.

The alternative would be to widen the policies, which means the application role
regains blanket read access to ``user_account`` and ``invitation`` for *every*
request, not just the two that need it. Two narrow ``SECURITY DEFINER`` functions
are far easier to audit: the escape hatch is named, its signature bounds exactly
what can come back out, and ``GRANT EXECUTE`` is the only way to reach it. This
follows the pattern ``resolve_invitation`` already established in the previous
migration.

Both functions pin ``search_path`` — without it, a caller able to create objects in
a schema earlier on the path could shadow a table and have it read with the
definer's privileges. That is the classic SECURITY DEFINER privilege-escalation
bug, and the one-line defence against it.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "9c3d1e7b45a2"
down_revision: str | None = "7a1c4e2b9d30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "coachlink_app"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Login lookup.
    #
    # Returns only what authentication needs. Notably it does NOT return
    # first/last name or timezone: a caller who guesses an e-mail learns nothing
    # beyond "a row came back", and the service layer answers with the same
    # INVALID_CREDENTIALS either way.
    #
    # `deleted_at` is returned rather than filtered so the service can treat a
    # soft-deleted account exactly like a wrong password — filtering here would
    # make the two paths differ in timing.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION authenticate_lookup(p_email citext)
        RETURNS TABLE (id uuid, password_hash text, role text, deleted_at timestamptz)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT u.id, u.password_hash, u.role, u.deleted_at
            FROM user_account u
            WHERE u.email = p_email
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION authenticate_lookup(citext) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION authenticate_lookup(citext) TO {APP_ROLE}")

    # ------------------------------------------------------------------
    # 2. Refresh-token lookup.
    #
    # Takes the SHA-256 digest, never the token itself: the digest is what is
    # stored, and passing the raw secret into a function would put it in
    # pg_stat_statements and in any statement log.
    #
    # Returns the bookkeeping columns only. The service decides what they mean —
    # in particular that a row which is revoked *or already replaced* signals a
    # replayed token and must burn the whole family.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION resolve_refresh_token(p_token_hash text)
        RETURNS TABLE (
            id uuid,
            user_id uuid,
            family_id uuid,
            expires_at timestamptz,
            revoked_at timestamptz,
            replaced_by uuid
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT r.id, r.user_id, r.family_id, r.expires_at, r.revoked_at, r.replaced_by
            FROM refresh_token r
            WHERE r.token_hash = p_token_hash
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION resolve_refresh_token(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION resolve_refresh_token(text) TO {APP_ROLE}")

    # ------------------------------------------------------------------
    # 3. Atomic invitation redemption.
    #
    # A single UPDATE ... WHERE consumed_at IS NULL RETURNING is what makes this
    # race-free: two clients submitting the same code concurrently both reach the
    # UPDATE, but only one row is still unconsumed, so exactly one gets a row back
    # and the other gets none. Doing the check and the write as two statements
    # from the application would let both succeed under concurrency and create two
    # links from one invitation.
    #
    # Expiry is evaluated here too, so an expired code can never be consumed even
    # if the service layer forgot to look.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION consume_invitation(p_code text, p_client uuid)
        RETURNS TABLE (id uuid, coach_id uuid, coaching_mode text)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            UPDATE invitation i
            SET consumed_at = now(), consumed_by = p_client
            WHERE i.code = p_code
              AND i.consumed_at IS NULL
              AND i.expires_at > now()
            RETURNING i.id, i.coach_id, i.coaching_mode::text
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION consume_invitation(text, uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION consume_invitation(text, uuid) TO {APP_ROLE}")

    # ------------------------------------------------------------------
    # 4. Registration needs to insert rows for a user who does not yet have a
    #    principal bound to the transaction. Rather than widening those policies,
    #    the service binds the RLS context to the id it is about to insert — the
    #    UUID v7 is generated application-side, so it is known in advance
    #    (app.services.auth.register_user). No policy change needed.
    #
    #    What DOES need widening: `resolve_invitation` from the previous migration
    #    is now redundant with `consume_invitation` for the accept path, but it is
    #    kept because the mobile app previews an invitation (coach name, mode)
    #    before the client commits to accepting it.
    # ------------------------------------------------------------------
    op.execute("REVOKE ALL ON FUNCTION resolve_invitation(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION resolve_invitation(text) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS consume_invitation(text, uuid)")
    op.execute("DROP FUNCTION IF EXISTS resolve_refresh_token(text)")
    op.execute("DROP FUNCTION IF EXISTS authenticate_lookup(citext)")
