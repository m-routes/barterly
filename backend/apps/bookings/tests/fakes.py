from apps.bookings.scheduler import SchedulerAuthError

GOOD_TOKEN = "scheduler-ok"  # noqa: S105 (a test value)
OTHER_CALLER_TOKEN = "someone-else"  # noqa: S105 (a test value)


class FakeSchedulerVerifier:
    """Accepts GOOD_TOKEN; OTHER_CALLER_TOKEN is a valid token for the wrong account."""

    def verify(self, token: str, *, audience: str = "", email: str = "") -> dict:
        if token == GOOD_TOKEN:
            return {"email": "scheduler@example.iam.gserviceaccount.com", "email_verified": True}
        if token == OTHER_CALLER_TOKEN:
            raise SchedulerAuthError("This caller may not run jobs.", status=403)
        raise SchedulerAuthError("Invalid scheduler token.")
