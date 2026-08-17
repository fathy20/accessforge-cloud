"""Session and password-policy contracts added by the hardening audit.

Covers: password-stamped tokens (a password change or admin reset revokes
every outstanding token), one shared password policy for registration and
change-password, the self-service profile route, and the bounded login
rate-limiter map.
"""

import unittest

from backend.tests.test_rbac_permissions import AppHarness


class TestTokenRevocationOnPasswordChange(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()

    def tearDown(self):
        self.app.close()

    def test_admin_reset_revokes_the_users_outstanding_tokens(self):
        self.app.create_user("victim@example.test", roles=["viewer"])
        self.app.create_user("resetter@example.test", roles=["admin"])
        victim_headers = self.app.headers("victim@example.test")
        victim_id = self.app.user_id("victim@example.test")

        # The stolen-token scenario: the session works until the reset lands.
        self.assertEqual(
            self.app.client.get("/api/auth/me", headers=victim_headers).status_code, 200
        )

        reset = self.app.client.post(
            f"/api/admin/users/{victim_id}/reset-password",
            headers=self.app.headers("resetter@example.test"),
        )
        self.assertEqual(reset.status_code, 200)

        self.assertEqual(
            self.app.client.get("/api/auth/me", headers=victim_headers).status_code, 401
        )

    def test_change_password_returns_a_working_replacement_token(self):
        self.app.create_user("rotator@example.test", roles=["viewer"])
        old_headers = self.app.headers("rotator@example.test")

        changed = self.app.client.post(
            "/api/auth/change-password",
            headers=old_headers,
            json={
                "current_password": "RBAC_TEST_PASSWORD_123",
                "new_password": "ROTATED_PASSWORD_123456",
            },
        )
        self.assertEqual(changed.status_code, 200, changed.text)

        fresh_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
        self.assertEqual(
            self.app.client.get("/api/auth/me", headers=old_headers).status_code, 401
        )
        self.assertEqual(
            self.app.client.get("/api/auth/me", headers=fresh_headers).status_code, 200
        )


class TestSharedPasswordPolicy(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()

    def tearDown(self):
        self.app.close()

    def test_register_enforces_the_same_minimum_as_change_password(self):
        response = self.app.client.post(
            "/api/auth/register",
            json={"email": "short-pw@example.test", "password": "elevenchars"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"], "Password must be at least 12 characters long"
        )

    def test_register_rejects_passwords_beyond_the_bcrypt_limit(self):
        response = self.app.client.post(
            "/api/auth/register",
            json={"email": "long-pw@example.test", "password": "x" * 80},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("at most 72 bytes", response.json()["detail"])


class TestProfileRoute(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()

    def tearDown(self):
        self.app.close()

    def test_me_returns_profile_fields_and_profile_put_updates_them(self):
        self.app.create_user("profiled@example.test", roles=["viewer"])
        headers = self.app.headers("profiled@example.test")

        updated = self.app.client.put(
            "/api/auth/profile",
            headers=headers,
            json={"department": "Line Maintenance", "phone": "+20 100 000 0000"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["updated"], ["department", "phone"])

        me = self.app.client.get("/api/auth/me", headers=headers).json()
        self.assertEqual(me["department"], "Line Maintenance")
        self.assertEqual(me["phone"], "+20 100 000 0000")
        self.assertEqual(me["status"], "active")

        # No-op update stays quiet and records nothing new.
        again = self.app.client.put(
            "/api/auth/profile",
            headers=headers,
            json={"department": "Line Maintenance"},
        )
        self.assertEqual(again.json()["updated"], [])

    def test_profile_field_length_is_bounded(self):
        self.app.create_user("bounded@example.test", roles=["viewer"])
        response = self.app.client.put(
            "/api/auth/profile",
            headers=self.app.headers("bounded@example.test"),
            json={"phone": "9" * 100},
        )
        self.assertEqual(response.status_code, 400)

    def test_profile_audit_contains_field_names_but_no_values(self):
        self.app.create_user("audited@example.test", roles=["viewer"])
        self.app.client.put(
            "/api/auth/profile",
            headers=self.app.headers("audited@example.test"),
            json={"phone": "+20 111 222 3333"},
        )
        from backend.models import AuditLog

        with self.app.database.SessionLocal() as session:
            event = (
                session.query(AuditLog)
                .filter(AuditLog.action == "profile_update")
                .one()
            )
            self.assertEqual(event.metadata_json, {"fields": ["phone"]})


class TestLoginRateLimiterBound(unittest.TestCase):
    def test_expired_keys_are_swept_once_the_map_is_full(self):
        import backend.auth as auth

        original = dict(auth._login_attempts)
        original_max = auth.MAX_TRACKED_LOGIN_KEYS
        try:
            auth._login_attempts.clear()
            auth.MAX_TRACKED_LOGIN_KEYS = 3
            stale = -(auth.WINDOW_SECONDS + 1)
            import time as _time

            now = _time.time()
            for key in ("a@x", "b@x", "c@x"):
                auth._login_attempts[key] = [now + stale]

            auth._check_rate_limit("d@x")

            self.assertIn("d@x", auth._login_attempts)
            for key in ("a@x", "b@x", "c@x"):
                self.assertNotIn(key, auth._login_attempts)
        finally:
            auth.MAX_TRACKED_LOGIN_KEYS = original_max
            auth._login_attempts.clear()
            auth._login_attempts.update(original)


if __name__ == "__main__":
    unittest.main()
