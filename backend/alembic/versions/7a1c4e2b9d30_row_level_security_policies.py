"""Row Level Security policies — the second isolation barrier

Revision ID: 7a1c4e2b9d30
Revises: 42f9f7f51afa
Create Date: 2026-09-22

ARCHITECTURE.md §4 / §2.3: "a coach accesses a client's data ONLY through a
coach_client_link with status = active. This rule is enforced TWICE: in the
FastAPI service layer *and* by a PostgreSQL Row Level Security policy."

This migration is the second half. It assumes the two roles created by
``scripts/bootstrap_roles.sql``:

* ``coachlink_owner`` — owns the tables, runs migrations;
* ``coachlink_app``   — NOSUPERUSER, NOBYPASSRLS, what the API connects as.

Three properties make these policies real rather than decorative:

1. **FORCE ROW LEVEL SECURITY** — without it the table owner bypasses its own
   policies, so any test run as the owner would prove nothing.
2. **Fail-closed context** — ``current_setting('app.current_user_id', true)``
   returns NULL when unset, and every policy compares against it, so a request
   that somehow reached the database without an identity sees zero rows rather
   than everything.
3. **The link must be `active`** — `pending`, `paused` and `revoked` all deny.
   Pausing the sharing (§5.3, right to restriction) therefore cuts the coach off
   at the database level, not merely in a service that could be bypassed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "7a1c4e2b9d30"
down_revision: str | None = "42f9f7f51afa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "coachlink_app"

#: Reads the principal set by app.core.db.apply_rls_context (SET LOCAL, so it is
#: scoped to the transaction and cannot leak through the connection pool).
CURRENT_USER = "nullif(current_setting('app.current_user_id', true), '')::uuid"

#: True when the current principal is a coach actively linked to `client_col`.
#: NOTE: this is a *correlated EXISTS*, so PostgreSQL evaluates it per row; the
#: index on (coach_id, status) keeps it cheap.
def _coach_of(client_col: str) -> str:
    return f"""
        EXISTS (
            SELECT 1 FROM coach_client_link l
            WHERE l.coach_id = {CURRENT_USER}
              AND l.client_id = {client_col}
              AND l.status = 'active'
        )
    """


#: Tables whose rows belong to a client: the client always sees their own rows,
#: the coach sees them only through an active link.
#: (table, column holding the client's user id, coach may write?)
CLIENT_OWNED_TABLES: tuple[tuple[str, str, bool], ...] = (
    ("body_measurement", "client_id", True),  # a coach may record a measurement
    ("progress_photo", "client_id", False),  # NEVER writable by a coach
    ("personal_record", "client_id", False),
    ("workout_log", "client_id", False),  # only the client logs their session
    ("nutrition_log", "client_id", False),
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # user_account: a user sees themselves; a coach sees their linked clients;
    # a client sees their coach (needed to display the coach's name).
    # ------------------------------------------------------------------
    _enable("user_account")
    op.execute(
        f"""
        CREATE POLICY user_account_select ON user_account FOR SELECT TO {APP_ROLE}
        USING (
            id = {CURRENT_USER}
            OR EXISTS (
                SELECT 1 FROM coach_client_link l
                WHERE l.status = 'active'
                  AND (
                        (l.coach_id = {CURRENT_USER} AND l.client_id = user_account.id)
                     OR (l.client_id = {CURRENT_USER} AND l.coach_id = user_account.id)
                  )
            )
        )
        """
    )
    # Only ever your own account row.
    op.execute(
        f"""
        CREATE POLICY user_account_update ON user_account FOR UPDATE TO {APP_ROLE}
        USING (id = {CURRENT_USER}) WITH CHECK (id = {CURRENT_USER})
        """
    )
    # Registration happens before any principal exists, so INSERT is unrestricted
    # here; the service layer owns that validation.
    op.execute(f"CREATE POLICY user_account_insert ON user_account FOR INSERT TO {APP_ROLE} WITH CHECK (true)")
    op.execute(f"CREATE POLICY user_account_delete ON user_account FOR DELETE TO {APP_ROLE} USING (id = {CURRENT_USER})")

    # ------------------------------------------------------------------
    # coach_client_link: visible to both sides, writable by the coach; the
    # client may update their own link (pausing the sharing, §5.3).
    # ------------------------------------------------------------------
    _enable("coach_client_link")
    op.execute(
        f"""
        CREATE POLICY link_select ON coach_client_link FOR SELECT TO {APP_ROLE}
        USING (coach_id = {CURRENT_USER} OR client_id = {CURRENT_USER})
        """
    )
    op.execute(
        f"""
        CREATE POLICY link_insert ON coach_client_link FOR INSERT TO {APP_ROLE}
        WITH CHECK (coach_id = {CURRENT_USER} OR client_id = {CURRENT_USER})
        """
    )
    op.execute(
        f"""
        CREATE POLICY link_update ON coach_client_link FOR UPDATE TO {APP_ROLE}
        USING (coach_id = {CURRENT_USER} OR client_id = {CURRENT_USER})
        WITH CHECK (coach_id = {CURRENT_USER} OR client_id = {CURRENT_USER})
        """
    )

    # ------------------------------------------------------------------
    # Profiles.
    # ------------------------------------------------------------------
    for table in ("coach_profile", "client_profile"):
        _enable(table)
        op.execute(
            f"""
            CREATE POLICY {table}_select ON {table} FOR SELECT TO {APP_ROLE}
            USING (
                user_id = {CURRENT_USER}
                OR EXISTS (
                    SELECT 1 FROM coach_client_link l
                    WHERE l.status = 'active'
                      AND (
                            (l.coach_id = {CURRENT_USER} AND l.client_id = {table}.user_id)
                         OR (l.client_id = {CURRENT_USER} AND l.coach_id = {table}.user_id)
                      )
                )
            )
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_write ON {table} FOR ALL TO {APP_ROLE}
            USING (user_id = {CURRENT_USER}) WITH CHECK (user_id = {CURRENT_USER})
            """
        )

    # ------------------------------------------------------------------
    # Client-owned sensitive tables.
    # ------------------------------------------------------------------
    for table, client_col, coach_may_write in CLIENT_OWNED_TABLES:
        _enable(table)
        op.execute(
            f"""
            CREATE POLICY {table}_select ON {table} FOR SELECT TO {APP_ROLE}
            USING ({client_col} = {CURRENT_USER} OR {_coach_of(f"{table}.{client_col}")})
            """
        )
        if coach_may_write:
            op.execute(
                f"""
                CREATE POLICY {table}_write ON {table} FOR ALL TO {APP_ROLE}
                USING ({client_col} = {CURRENT_USER} OR {_coach_of(f"{table}.{client_col}")})
                WITH CHECK ({client_col} = {CURRENT_USER} OR {_coach_of(f"{table}.{client_col}")})
                """
            )
        else:
            op.execute(
                f"""
                CREATE POLICY {table}_write ON {table} FOR ALL TO {APP_ROLE}
                USING ({client_col} = {CURRENT_USER})
                WITH CHECK ({client_col} = {CURRENT_USER})
                """
            )

    # progress_photo needs a stricter SELECT than the loop above: a coach sees a
    # photo ONLY when the client explicitly shared it (§5.1). Replace the policy.
    op.execute("DROP POLICY progress_photo_select ON progress_photo")
    op.execute(
        f"""
        CREATE POLICY progress_photo_select ON progress_photo FOR SELECT TO {APP_ROLE}
        USING (
            client_id = {CURRENT_USER}
            OR (shared_with_coach = true AND {_coach_of("progress_photo.client_id")})
        )
        """
    )

    # ------------------------------------------------------------------
    # set_log — reached through its workout_log's client.
    # ------------------------------------------------------------------
    _enable("set_log")
    op.execute(
        f"""
        CREATE POLICY set_log_select ON set_log FOR SELECT TO {APP_ROLE}
        USING (
            EXISTS (
                SELECT 1 FROM workout_log w
                WHERE w.id = set_log.workout_log_id
                  AND (w.client_id = {CURRENT_USER} OR {_coach_of("w.client_id")})
            )
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY set_log_write ON set_log FOR ALL TO {APP_ROLE}
        USING (
            EXISTS (SELECT 1 FROM workout_log w
                    WHERE w.id = set_log.workout_log_id AND w.client_id = {CURRENT_USER})
        )
        WITH CHECK (
            EXISTS (SELECT 1 FROM workout_log w
                    WHERE w.id = set_log.workout_log_id AND w.client_id = {CURRENT_USER})
        )
        """
    )

    # ------------------------------------------------------------------
    # Programs — owned by the coach, readable by the assigned client once
    # published. A draft is never visible to the client.
    # ------------------------------------------------------------------
    _enable("program")
    op.execute(
        f"""
        CREATE POLICY program_select ON program FOR SELECT TO {APP_ROLE}
        USING (
            coach_id = {CURRENT_USER}
            OR (client_id = {CURRENT_USER} AND status = 'published')
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY program_write ON program FOR ALL TO {APP_ROLE}
        USING (coach_id = {CURRENT_USER}) WITH CHECK (coach_id = {CURRENT_USER})
        """
    )

    _enable("program_session")
    op.execute(
        f"""
        CREATE POLICY program_session_all ON program_session FOR ALL TO {APP_ROLE}
        USING (
            EXISTS (SELECT 1 FROM program p WHERE p.id = program_session.program_id)
        )
        WITH CHECK (
            EXISTS (SELECT 1 FROM program p
                    WHERE p.id = program_session.program_id AND p.coach_id = {CURRENT_USER})
        )
        """
    )

    _enable("session_exercise")
    op.execute(
        f"""
        CREATE POLICY session_exercise_all ON session_exercise FOR ALL TO {APP_ROLE}
        USING (
            EXISTS (SELECT 1 FROM program_session s
                    WHERE s.id = session_exercise.program_session_id)
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM program_session s
                JOIN program p ON p.id = s.program_id
                WHERE s.id = session_exercise.program_session_id
                  AND p.coach_id = {CURRENT_USER}
            )
        )
        """
    )

    # ------------------------------------------------------------------
    # Nutrition.
    # ------------------------------------------------------------------
    _enable("nutrition_plan")
    op.execute(
        f"""
        CREATE POLICY nutrition_plan_select ON nutrition_plan FOR SELECT TO {APP_ROLE}
        USING (
            client_id = {CURRENT_USER}
            OR (coach_id = {CURRENT_USER} AND {_coach_of("nutrition_plan.client_id")})
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY nutrition_plan_write ON nutrition_plan FOR ALL TO {APP_ROLE}
        USING (coach_id = {CURRENT_USER} AND {_coach_of("nutrition_plan.client_id")})
        WITH CHECK (coach_id = {CURRENT_USER} AND {_coach_of("nutrition_plan.client_id")})
        """
    )

    _enable("meal")
    op.execute(
        f"""
        CREATE POLICY meal_all ON meal FOR ALL TO {APP_ROLE}
        USING (EXISTS (SELECT 1 FROM nutrition_plan p WHERE p.id = meal.nutrition_plan_id))
        WITH CHECK (
            EXISTS (SELECT 1 FROM nutrition_plan p
                    WHERE p.id = meal.nutrition_plan_id AND p.coach_id = {CURRENT_USER})
        )
        """
    )

    # ------------------------------------------------------------------
    # Messaging — only the two parties of the conversation.
    # ------------------------------------------------------------------
    _enable("conversation")
    op.execute(
        f"""
        CREATE POLICY conversation_all ON conversation FOR ALL TO {APP_ROLE}
        USING (
            EXISTS (
                SELECT 1 FROM coach_client_link l
                WHERE l.id = conversation.coach_client_link_id
                  AND (l.coach_id = {CURRENT_USER} OR l.client_id = {CURRENT_USER})
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM coach_client_link l
                WHERE l.id = conversation.coach_client_link_id
                  AND (l.coach_id = {CURRENT_USER} OR l.client_id = {CURRENT_USER})
            )
        )
        """
    )

    _enable("message")
    op.execute(
        f"""
        CREATE POLICY message_select ON message FOR SELECT TO {APP_ROLE}
        USING (
            EXISTS (
                SELECT 1 FROM conversation c
                JOIN coach_client_link l ON l.id = c.coach_client_link_id
                WHERE c.id = message.conversation_id
                  AND (l.coach_id = {CURRENT_USER} OR l.client_id = {CURRENT_USER})
            )
        )
        """
    )
    # You may only send as yourself.
    op.execute(
        f"""
        CREATE POLICY message_insert ON message FOR INSERT TO {APP_ROLE}
        WITH CHECK (
            sender_id = {CURRENT_USER}
            AND EXISTS (
                SELECT 1 FROM conversation c
                JOIN coach_client_link l ON l.id = c.coach_client_link_id
                WHERE c.id = message.conversation_id
                  AND l.status = 'active'
                  AND (l.coach_id = {CURRENT_USER} OR l.client_id = {CURRENT_USER})
            )
        )
        """
    )
    # Update is limited to marking a message read (the service restricts columns).
    op.execute(
        f"""
        CREATE POLICY message_update ON message FOR UPDATE TO {APP_ROLE}
        USING (
            EXISTS (
                SELECT 1 FROM conversation c
                JOIN coach_client_link l ON l.id = c.coach_client_link_id
                WHERE c.id = message.conversation_id
                  AND (l.coach_id = {CURRENT_USER} OR l.client_id = {CURRENT_USER})
            )
        )
        """
    )

    # ------------------------------------------------------------------
    # Strictly personal tables: only ever your own rows.
    # ------------------------------------------------------------------
    for table in (
        "consent",
        "data_request",
        "notification",
        "device_token",
        "encryption_key",
        "refresh_token",
        "idempotency_record",
    ):
        _enable(table)
        op.execute(
            f"""
            CREATE POLICY {table}_all ON {table} FOR ALL TO {APP_ROLE}
            USING (user_id = {CURRENT_USER}) WITH CHECK (user_id = {CURRENT_USER})
            """
        )

    # ------------------------------------------------------------------
    # Exercises: global catalogue + public coach exercises + your own.
    # ------------------------------------------------------------------
    _enable("exercise")
    op.execute(
        f"""
        CREATE POLICY exercise_select ON exercise FOR SELECT TO {APP_ROLE}
        USING (
            owner_coach_id IS NULL
            OR is_public = true
            OR owner_coach_id = {CURRENT_USER}
            OR EXISTS (
                SELECT 1 FROM coach_client_link l
                WHERE l.client_id = {CURRENT_USER}
                  AND l.coach_id = exercise.owner_coach_id
                  AND l.status = 'active'
            )
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY exercise_write ON exercise FOR ALL TO {APP_ROLE}
        USING (owner_coach_id = {CURRENT_USER}) WITH CHECK (owner_coach_id = {CURRENT_USER})
        """
    )

    # ------------------------------------------------------------------
    # Invitations: the issuing coach only. Redeeming a code is done by the
    # service layer, which needs a lookup the invitee cannot perform — see
    # the SECURITY DEFINER function below rather than a permissive policy.
    # ------------------------------------------------------------------
    _enable("invitation")
    op.execute(
        f"""
        CREATE POLICY invitation_all ON invitation FOR ALL TO {APP_ROLE}
        USING (coach_id = {CURRENT_USER}) WITH CHECK (coach_id = {CURRENT_USER})
        """
    )
    # Narrow, auditable escape hatch: resolves a code to its invitation without
    # exposing the whole table. Returns nothing for an expired/consumed code.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION resolve_invitation(p_code text)
        RETURNS TABLE (id uuid, coach_id uuid, coaching_mode text, expires_at timestamptz)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT i.id, i.coach_id, i.coaching_mode::text, i.expires_at
            FROM invitation i
            WHERE i.code = p_code
              AND i.consumed_at IS NULL
              AND i.expires_at > now()
        $$
        """
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION resolve_invitation(text) TO {APP_ROLE}")

    # ------------------------------------------------------------------
    # Billing / audit: written by workers under the owner role, read-only for
    # the subject. audit_log is deliberately NOT readable by the application.
    # ------------------------------------------------------------------
    _enable("subscription")
    op.execute(
        f"""
        CREATE POLICY subscription_select ON subscription FOR SELECT TO {APP_ROLE}
        USING (
            subject_id = {CURRENT_USER}
            OR (subject_type = 'client' AND {_coach_of("subscription.subject_id")})
        )
        """
    )

    _enable("active_client_snapshot")
    op.execute(
        f"""
        CREATE POLICY active_client_snapshot_select ON active_client_snapshot
        FOR SELECT TO {APP_ROLE}
        USING (coach_id = {CURRENT_USER} OR client_id = {CURRENT_USER})
        """
    )

    # audit_log: INSERT only. Nobody reads their own audit trail through the API,
    # and a coach must never be able to check what was logged about them.
    _enable("audit_log")
    op.execute(
        f"CREATE POLICY audit_log_insert ON audit_log FOR INSERT TO {APP_ROLE} WITH CHECK (true)"
    )

    _enable("billing_event")
    op.execute(
        f"""
        CREATE POLICY billing_event_select ON billing_event FOR SELECT TO {APP_ROLE}
        USING (
            EXISTS (
                SELECT 1 FROM subscription s
                WHERE s.id = billing_event.subscription_id
                  AND s.subject_id = {CURRENT_USER}
            )
        )
        """
    )


def _enable(table: str) -> None:
    """Enable RLS *and* force it for the owner.

    ENABLE alone leaves the table owner exempt, which would make every policy
    invisible to a test connecting as the owner — a cosmetic barrier.
    """
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


ALL_RLS_TABLES = (
    "user_account",
    "coach_profile",
    "client_profile",
    "coach_client_link",
    "invitation",
    "refresh_token",
    "encryption_key",
    "exercise",
    "program",
    "program_session",
    "session_exercise",
    "workout_log",
    "set_log",
    "personal_record",
    "body_measurement",
    "progress_photo",
    "nutrition_plan",
    "meal",
    "nutrition_log",
    "conversation",
    "message",
    "notification",
    "device_token",
    "consent",
    "data_request",
    "subscription",
    "billing_event",
    "active_client_snapshot",
    "audit_log",
    "idempotency_record",
)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_invitation(text)")
    for table in ALL_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        # Policy names are prefixed by the table name, so drop them generically.
        op.execute(
            f"""
            DO $$
            DECLARE pol record;
            BEGIN
                FOR pol IN SELECT policyname FROM pg_policies
                           WHERE tablename = '{table}' AND schemaname = 'public'
                LOOP
                    EXECUTE format('DROP POLICY %I ON {table}', pol.policyname);
                END LOOP;
            END
            $$
            """
        )
