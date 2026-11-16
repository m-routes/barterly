"""In-app chat. A conversation belongs to one application; it opens when the vendor
shortlists the applicant or messages them first. Before a booking is confirmed the
contact-sharing guard masks phone numbers, emails, links and the like (apps.chat.leakage);
after confirmation contact details may be shared.

Sending locks the conversation row, so each message gets the next seq with no gaps:
clients fetch "everything after seq N" (the cursor) and never miss one.
"""

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Count, F, IntegerField, Max, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.applications.constants import ApplicationStatus as A
from apps.applications.models import Application
from apps.bookings.lifecycle import BookingStatus
from apps.bookings.models import Booking
from apps.chat import leakage
from apps.chat.filters import FilterResult, get_filter
from apps.chat.models import (
    MAX_ATTACHMENTS,
    MAX_BODY,
    Block,
    Conversation,
    LeakageEvent,
    Message,
    MessageAttachment,
    MessageReport,
    OpenedBy,
)
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action
from apps.media.models import MediaFile
from apps.media.policy import IMAGE_TYPES, MB, PDF
from apps.media.services.uploads import is_servable

# Chat stays readable but no one can send once the application has ended without a
# booking.
CLOSED = frozenset({A.REJECTED, A.WITHDRAWN, A.DECLINED, A.EXPIRED})
# The vendor can open a chat while the application is still being decided.
OPENABLE = frozenset({A.APPLIED, A.SHORTLISTED, A.INTERVIEW, A.OFFERED, A.CONFIRMED})
ATTACHMENT_TYPES = frozenset({*IMAGE_TYPES, PDF})
MAX_ATTACHMENT_BYTES = 10 * MB
PAGE = 50
MAX_PAGE = 100
PREVIEW = 120


class ChatError(Exception):
    """The chat action can't happen; the message says why. `status` is the HTTP one."""

    def __init__(self, message: str, *, code: str = "chat_refused", status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


def display_name(user) -> str:
    if user.is_vendor:
        profile = getattr(user, "vendor_profile", None)
        return (profile.business_name if profile else "") or "Host"
    profile = getattr(user, "talent_profile", None)
    return (profile.display_name if profile else "") or "Applicant"


# ---------- Opening ----------


def open_conversation(application: Application, opened_by: str, *, user=None, request=None):
    """The application's conversation, created if needed. Idempotent."""
    conversation, created = Conversation.objects.get_or_create(
        application=application,
        defaults={
            "talent_id": application.talent_id,
            "vendor_id": application.gig.vendor_id,
            "opened_by": opened_by,
        },
    )
    if created:
        log_action(
            actor=user,
            action="chat.opened",
            obj=conversation,
            after={"application": str(application.pk), "opened_by": opened_by},
            request=request,
        )
    return conversation


def open_on_shortlist(event: DomainEvent) -> None:
    """Subscribed to application.shortlisted (see ChatConfig.ready)."""
    application = Application.objects.select_related("gig").get(pk=event.payload["application_id"])
    open_conversation(application, OpenedBy.SHORTLIST)


def vendor_open(application_id, *, vendor, request=None) -> Conversation:
    application = (
        Application.objects.select_related("gig")
        .filter(pk=application_id, gig__vendor=vendor)
        .first()
    )
    if application is None:
        raise ChatError("No such application.", code="not_found", status=404)
    existing = Conversation.objects.filter(application=application).first()
    if existing:
        return existing
    if application.status not in OPENABLE:
        raise ChatError("This application is closed, so you can't start a chat.")
    return open_conversation(application, OpenedBy.VENDOR_MESSAGE, user=vendor, request=request)


# ---------- Rules ----------


def contact_sharing_allowed(conversation: Conversation) -> bool:
    """True once the application has a booking that wasn't cancelled."""
    return (
        Booking.objects.filter(application_id=conversation.application_id)
        .exclude(status=BookingStatus.CANCELLED)
        .exists()
    )


def blocked_by(user, other) -> bool:
    return Block.objects.filter(blocker=user, blocked=other).exists()


def why_cant_send(conversation: Conversation, user) -> str:
    """'' when `user` may send in this conversation, otherwise the reason."""
    if conversation.application.status in CLOSED:
        return "This application is closed, so the chat is read-only."
    other = conversation.other(user)
    if blocked_by(user, other):
        return "You blocked this person. Unblock them to send a message."
    if blocked_by(other, user):
        return "You can't message this person."
    return ""


# ---------- Sending ----------


@dataclass
class Sent:
    message: Message
    notice: str = ""  # tells the sender what was hidden, and why


def _attachments(sender, ids) -> list[MediaFile]:
    ids = list(dict.fromkeys(str(i) for i in ids))
    if len(ids) > MAX_ATTACHMENTS:
        raise ChatError(f"Attach at most {MAX_ATTACHMENTS} files.", code="invalid", status=400)
    files = {str(m.pk): m for m in MediaFile.objects.filter(pk__in=ids, owner=sender)}
    out = []
    for pk in ids:
        media = files.get(pk)
        if media is None or not is_servable(media):
            raise ChatError("An attachment isn't uploaded yet.", code="invalid", status=400)
        if media.content_type not in ATTACHMENT_TYPES:
            raise ChatError("Send photos (JPEG, PNG, WebP) or PDFs.", code="invalid", status=400)
        if media.size_bytes > MAX_ATTACHMENT_BYTES:
            raise ChatError("Attachments can be up to 10 MB.", code="invalid", status=400)
        out.append(media)
    return out


def _notice(kinds: list[str], filtered: bool) -> str:
    parts = [leakage.explain(kinds)] if kinds else []
    if filtered:
        parts.append("Some words were hidden.")
    return " ".join(parts)


def send(
    conversation_id,
    *,
    sender,
    body: str = "",
    attachment_ids=(),
    client_id: str = "",
    request=None,
) -> Sent:
    body = (body or "").strip()
    with transaction.atomic():
        conversation = (
            Conversation.objects.select_for_update(of=("self",))
            .select_related("application__gig")
            .filter(pk=conversation_id)
            .first()
        )
        if conversation is None or not conversation.has_member(sender):
            raise ChatError("No such conversation.", code="not_found", status=404)
        if client_id:
            earlier = Message.objects.filter(
                conversation=conversation, sender=sender, client_id=client_id
            ).first()
            if earlier:
                return Sent(earlier, _notice(earlier.masked_kinds, False))
        reason = why_cant_send(conversation, sender)
        if reason:
            raise ChatError(reason, code="chat_closed", status=403)
        if len(body) > MAX_BODY:
            raise ChatError(
                f"Keep messages under {MAX_BODY} characters.", code="invalid", status=400
            )
        media = _attachments(sender, attachment_ids)
        if not body and not media:
            raise ChatError("Write a message or attach a file.", code="invalid", status=400)

        checked = get_filter().check(body) if body else FilterResult(FilterResult.ALLOW, body)
        if checked.action == FilterResult.REFUSE:
            raise ChatError(
                checked.reason or "This message can't be sent.", code="message_refused", status=400
            )
        shown = checked.text
        scan = leakage.Result(shown)
        if shown and not contact_sharing_allowed(conversation):
            scan = leakage.scan(shown)
            shown = scan.text

        now = timezone.now()
        conversation.last_seq += 1
        conversation.last_message_at = now
        conversation.save(update_fields=["last_seq", "last_message_at"])
        message = Message.objects.create(
            conversation=conversation,
            seq=conversation.last_seq,
            sender=sender,
            body=shown,
            masked_kinds=scan.kinds,
            client_id=client_id,
        )
        MessageAttachment.objects.bulk_create(
            MessageAttachment(message=message, media=m, position=i) for i, m in enumerate(media)
        )
        if scan.masked:
            LeakageEvent.objects.create(
                conversation=conversation,
                message=message,
                sender=sender,
                kinds=scan.kinds,
                original_body=body,
            )
            # The audit row says what kind was hidden, never the hidden text itself.
            log_action(
                actor=sender,
                action="chat.contact_masked",
                obj=message,
                after={"conversation": str(conversation.pk), "kinds": scan.kinds},
                request=request,
            )
        recipient = conversation.other(sender)
        publish(
            DomainEvent(
                "chat.message",
                {
                    "conversation_id": str(conversation.pk),
                    "application_id": str(conversation.application_id),
                    "message_id": str(message.pk),
                    "seq": message.seq,
                    "sender_id": str(sender.pk),
                    "sender_name": display_name(sender),
                    "recipient_id": str(recipient.pk),
                    "gig_title": conversation.application.gig.title,
                    "preview": shown[:PREVIEW] or "Sent an attachment",
                },
                occurred_at=now,
            )
        )
    return Sent(message, _notice(scan.kinds, checked.action == FilterResult.MASK))


# ---------- Reading ----------


@dataclass
class Page:
    messages: list[Message]
    cursor: int  # pass back as `after` to get only newer messages
    has_earlier: bool
    other_read_up_to: int  # newest of my messages the other side has read


def _seq(value, name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = -1
    if number < 0:
        raise ChatError(
            f"{name} must be a cursor from an earlier fetch.", code="invalid", status=400
        )
    return number


def fetch(conversation: Conversation, user, *, after=None, before=None, limit=PAGE) -> Page:
    """Messages after a cursor (polling), before one (scrolling back), or the newest."""
    after, before = _seq(after, "after"), _seq(before, "before")
    limit = max(1, min(int(limit or PAGE), MAX_PAGE))
    qs = conversation.messages.select_related("sender").prefetch_related("attachments__media")
    if after is not None:
        messages = list(qs.filter(seq__gt=after).order_by("seq")[:limit])
    else:
        if before is not None:
            qs = qs.filter(seq__lt=before)
        messages = list(qs.order_by("-seq")[:limit])[::-1]
    newest = messages[-1].seq if messages else None
    cursor = (
        max(newest or 0, after or 0) if after is not None else (newest or conversation.last_seq)
    )
    read = (
        conversation.messages.filter(sender=user, read_at__isnull=False).aggregate(m=Max("seq"))[
            "m"
        ]
        or 0
    )
    return Page(
        messages=messages,
        cursor=cursor,
        has_earlier=bool(messages) and messages[0].seq > 1,
        other_read_up_to=read,
    )


def mark_read(conversation: Conversation, user, up_to) -> int:
    """Mark the other side's messages up to seq `up_to` as read. Returns how many."""
    up_to = _seq(up_to, "up_to")
    return (
        conversation.messages.filter(seq__lte=up_to, read_at__isnull=True)
        .exclude(sender=user)
        .update(read_at=timezone.now())
    )


def unread_by_conversation(user, conversation_ids) -> dict:
    rows = (
        Message.objects.filter(conversation_id__in=conversation_ids, read_at__isnull=True)
        .exclude(sender=user)
        .values("conversation_id")
        .annotate(n=Count("id"))
    )
    return {row["conversation_id"]: row["n"] for row in rows}


def with_chat(applications, user):
    """Annotate applications with their conversation id (conversation_ref) and how
    many messages in it `user` hasn't read (unread_messages)."""
    unread = (
        Message.objects.filter(conversation__application=OuterRef("pk"), read_at__isnull=True)
        .exclude(sender=user)
        .values("conversation__application")
        .annotate(n=Count("id"))
        .values("n")
    )
    return applications.annotate(
        conversation_ref=F("conversation__id"),
        unread_messages=Coalesce(Subquery(unread, output_field=IntegerField()), 0),
    )


def conversations_for(user):
    return Conversation.objects.filter(Q(talent=user) | Q(vendor=user)).select_related(
        "application__gig", "talent__talent_profile", "vendor__vendor_profile"
    )


def unread_total(user) -> dict:
    counts = unread_by_conversation(user, conversations_for(user).values("pk"))
    return {"unread": sum(counts.values()), "conversations": len(counts)}


# ---------- Safety ----------


def block(conversation: Conversation, user, *, request=None) -> Block:
    other = conversation.other(user)
    blocked, created = Block.objects.get_or_create(blocker=user, blocked=other)
    if created:
        log_action(
            actor=user,
            action="chat.blocked",
            obj=blocked,
            after={"blocked": str(other.pk), "conversation": str(conversation.pk)},
            request=request,
        )
    return blocked


def unblock(conversation: Conversation, user, *, request=None) -> None:
    other = conversation.other(user)
    deleted, _ = Block.objects.filter(blocker=user, blocked=other).delete()
    if deleted:
        log_action(
            actor=user,
            action="chat.unblocked",
            object_type="accounts.user",
            object_id=other.pk,
            after={"unblocked": str(other.pk), "conversation": str(conversation.pk)},
            request=request,
        )


def report(message_id, *, reporter, reason: str, note: str = "", request=None) -> MessageReport:
    message = Message.objects.select_related("conversation").filter(pk=message_id).first()
    if message is None or not message.conversation.has_member(reporter):
        raise ChatError("No such message.", code="not_found", status=404)
    if message.sender_id == reporter.pk:
        raise ChatError("You can't report your own message.", code="invalid", status=400)
    try:
        with transaction.atomic():
            created = MessageReport.objects.create(
                message=message, reporter=reporter, reason=reason, note=note.strip()
            )
    except IntegrityError as exc:
        raise ChatError("You've already reported this message.") from exc
    log_action(
        actor=reporter,
        action="chat.message_reported",
        obj=created,
        after={"message": str(message.pk), "reason": reason},
        request=request,
    )
    return created
