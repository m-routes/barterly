"""Invite codes: made by ops in batches, used once at sign-up (the role step).

Codes are 8 characters from an alphabet without look-alikes (no 0/O, 1/I/L), shown as
ABCD-2345. People can type them with or without the dash, in any case.
"""

import re
import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.beta.models import InviteCode, InviteRedemption
from apps.common.services.audit import log_action

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
LENGTH = 8
MAX_BATCH = 500


class InviteError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


REQUIRED = InviteError(
    "invite_required",
    "Barterly is invite-only for now. Enter the code we sent you.",
    403,
)


def normalise(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def _new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def generate(
    *,
    count: int,
    cohort: str,
    role: str = "",
    labels: list[str] | None = None,
    max_uses: int = 1,
    expires_at=None,
    by=None,
    request=None,
) -> list[InviteCode]:
    """Make `count` codes (or one per label). Audited as one batch."""
    labels = labels or []
    count = len(labels) or count
    if not 1 <= count <= MAX_BATCH:
        raise ValueError(f"Make between 1 and {MAX_BATCH} codes at a time.")
    if not cohort.strip():
        raise ValueError("Give the cohort, for example wave-1.")
    if max_uses < 1:
        raise ValueError("Each code needs at least one use.")
    made: list[InviteCode] = []
    with transaction.atomic():
        for i in range(count):
            for _attempt in range(5):
                try:
                    with transaction.atomic():
                        made.append(
                            InviteCode.objects.create(
                                code=_new_code(),
                                role=role,
                                cohort=cohort.strip(),
                                label=labels[i].strip()[:200] if labels else "",
                                max_uses=max_uses,
                                expires_at=expires_at,
                                created_by=by,
                            )
                        )
                    break
                except IntegrityError:  # the same random code twice: draw again
                    continue
            else:  # pragma: no cover - 31^8 codes
                raise RuntimeError("Couldn't draw a unique invite code.")
        log_action(
            actor=by,
            action="beta.invites_created",
            object_type="beta.cohort",
            object_id=cohort.strip(),
            after={
                "count": len(made),
                "role": role,
                "max_uses": max_uses,
                "expires_at": expires_at,
            },
            request=request,
        )
    return made


def redeem(raw_code: str, *, user, role: str, request=None, now=None) -> InviteRedemption:
    """Use a code for this person's sign-up. Call inside the sign-up's transaction."""
    now = now or timezone.now()
    existing = InviteRedemption.objects.filter(user=user).select_related("invite").first()
    if existing:
        return existing
    code = normalise(raw_code)
    if not code:
        raise REQUIRED
    with transaction.atomic():
        invite = InviteCode.objects.select_for_update().filter(code=code).first()
        if invite is None:
            raise InviteError("invite_invalid", "That code isn't right. Check it and try again.")
        state = invite.state(now)
        if state == "revoked":
            raise InviteError("invite_invalid", "That code has been withdrawn.")
        if state == "expired":
            raise InviteError("invite_invalid", "That code has expired. Ask us for a new one.")
        if state == "used":
            raise InviteError("invite_invalid", "That code has already been used.")
        if invite.role and invite.role != role:
            who = "hosts" if invite.role == "vendor" else "talent"
            raise InviteError("invite_invalid", f"That code is for {who}.")
        invite.used += 1
        invite.save(update_fields=["used"])
        redemption = InviteRedemption.objects.create(
            invite=invite, user=user, role=role, redeemed_at=now
        )
        log_action(
            actor=user,
            action="beta.invite_redeemed",
            obj=invite,
            after={"user_id": user.pk, "role": role, "used": invite.used},
            request=request,
        )
    return redemption


def revoke(invite: InviteCode, *, by, reason: str = "", request=None, now=None) -> InviteCode:
    if invite.revoked_at:
        return invite
    invite.revoked_at = now or timezone.now()
    invite.save(update_fields=["revoked_at"])
    log_action(
        actor=by,
        action="beta.invite_revoked",
        obj=invite,
        after={"reason": reason, "used": invite.used},
        request=request,
    )
    return invite
