"""Gig vocabulary and the status machine.

TRANSITIONS is the one place that says which status changes exist and who may make
them. apps.gigs.services.transition() refuses anything not listed.
"""

from django.db import models

MIN_AGE_YEARS = 18  # fixed for every gig; not editable
MAX_HOURS_PER_DAY = 6
MAX_DAYS_PER_WEEK = 6  # at least one day off
MAX_SCREENING_QUESTIONS = 5
MAX_DELIVERABLES = 10


class RoleTemplate(models.TextChoices):
    VOLUNTEER = "volunteer", "Volunteer"
    CONTENT_CREATOR = "content_creator", "Content creator"
    TRIP_LEADER = "trip_leader", "Trip leader"
    SPECIALIST = "specialist", "Specialist"


class CompensationModel(models.TextChoices):
    VOLUNTEER = "volunteer", "Volunteer (work for stay)"
    BARTER = "barter", "Barter (content for stay)"
    HYBRID = "hybrid", "Hybrid (stay plus stipend)"
    PAID = "paid", "Paid"


STIPEND_MODELS = frozenset({CompensationModel.HYBRID, CompensationModel.PAID})
DELIVERABLE_MODELS = frozenset({CompensationModel.BARTER, CompensationModel.HYBRID})


class StipendPeriod(models.TextChoices):
    TOTAL = "total", "For the whole gig"
    PER_WEEK = "per_week", "Per week"
    PER_MONTH = "per_month", "Per month"


class StayType(models.TextChoices):
    NONE = "none", "No stay"
    DORM_BED = "dorm_bed", "Dorm bed"
    SHARED_ROOM = "shared_room", "Shared room"
    PRIVATE_ROOM = "private_room", "Private room"
    TENT = "tent", "Tent / camping"


class Meals(models.TextChoices):
    NONE = "none", "No meals"
    BREAKFAST = "breakfast", "Breakfast"
    TWO_MEALS = "two_meals", "Two meals a day"
    ALL_MEALS = "all_meals", "All meals"


class DeliverableType(models.TextChoices):
    INSTAGRAM_POST = "instagram_post", "Instagram post"
    INSTAGRAM_REEL = "instagram_reel", "Instagram reel"
    INSTAGRAM_STORY = "instagram_story", "Instagram story"
    YOUTUBE_VIDEO = "youtube_video", "YouTube video"
    BLOG_POST = "blog_post", "Blog post"
    PHOTO_SET = "photo_set", "Edited photo set"
    MURAL = "mural", "Mural / artwork"
    OTHER = "other", "Other"


class GigStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    IN_REVIEW = "in_review", "In review"
    LIVE = "live", "Live"
    PAUSED = "paused", "Paused"
    FILLED = "filled", "Filled"
    CLOSED = "closed", "Closed"
    ARCHIVED = "archived", "Archived"


class Actor(models.TextChoices):
    VENDOR = "vendor", "The gig's vendor"
    ADMIN = "admin", "Barterly admin"
    SYSTEM = "system", "Scheduled job or another service"


G, A = GigStatus, Actor
# (from, to) -> who may make that change.
TRANSITIONS: dict[tuple[str, str], frozenset[str]] = {
    (G.DRAFT, G.IN_REVIEW): frozenset({A.VENDOR}),  # submit
    (G.DRAFT, G.ARCHIVED): frozenset({A.VENDOR, A.ADMIN}),
    (G.IN_REVIEW, G.LIVE): frozenset({A.ADMIN}),  # approve
    (G.IN_REVIEW, G.DRAFT): frozenset({A.VENDOR, A.ADMIN}),  # withdraw / send back
    (G.LIVE, G.IN_REVIEW): frozenset({A.SYSTEM}),  # pay, hours or dates edited
    (G.LIVE, G.PAUSED): frozenset({A.VENDOR, A.ADMIN}),
    (G.LIVE, G.FILLED): frozenset({A.SYSTEM}),  # confirmed bookings reached slots
    (G.LIVE, G.CLOSED): frozenset({A.VENDOR, A.ADMIN, A.SYSTEM}),
    (G.PAUSED, G.LIVE): frozenset({A.VENDOR}),
    (G.PAUSED, G.IN_REVIEW): frozenset({A.SYSTEM}),
    (G.PAUSED, G.CLOSED): frozenset({A.VENDOR, A.ADMIN, A.SYSTEM}),
    (G.FILLED, G.LIVE): frozenset({A.SYSTEM}),  # a booking was cancelled
    (G.FILLED, G.CLOSED): frozenset({A.VENDOR, A.ADMIN, A.SYSTEM}),
    (G.CLOSED, G.ARCHIVED): frozenset({A.VENDOR, A.ADMIN}),
}

# Statuses the vendor may edit in, and the fields whose change on a live or paused gig
# sends it back to review.
EDITABLE = frozenset({G.DRAFT, G.IN_REVIEW, G.LIVE, G.PAUSED})
REVIEWED_FIELDS = frozenset(
    {
        "compensation_model",
        "stipend_amount",
        "stipend_period",
        "hours_per_day",
        "days_per_week",
        "start_date",
        "end_date",
        "duration_days",
        "apply_by",
    }
)
MONEY_FIELDS = ("compensation_model", "stipend_amount", "stipend_period")
