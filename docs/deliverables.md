# Deliverables (barter and hybrid gigs)

`apps/deliverables` (backend), Console → **Content** (web), and the trip's
**Deliverables** screen (mobile).

## From the agreement

When the talent checks in, each item of the agreement's `deliverables` becomes one
`Deliverable` per unit: "2 × Instagram reel" becomes "Instagram reel 1 of 2" and "2 of 2".
Bookings checked in earlier get theirs the first time they're listed.

- **Kind:** derived from the item's type. `instagram_reel` → reel, `instagram_story` →
  story, `photo_set` → photo set, `google_review` → Google review, anything else →
  custom. The agreement's own type is kept as `spec_type`.
- **Due date:** the stay's last day. The host can move it to any day of the stay or up
  to 30 days after (`PATCH /deliverables/items/<id>/`, audited, the talent told).

## Submitting and reviewing

- **Submitting:** `POST /deliverables/items/<id>/submit/` takes a post link and/or
  uploaded files (media ids the talent owns, not rejected or quarantined). Each
  submission is a numbered version. The talent can hand in again until it's approved.
- **Statuses:** `pending → submitted → changes_requested → submitted → … → approved`.
- **Reviewing:** `POST /deliverables/items/<id>/review/` with `{approve, note}`. Asking
  for changes needs a note and may happen at most **2** times per deliverable (also a
  database constraint). After that the host approves or opens a dispute on the booking.
- **Notifications:** the host on each submission and when everything's in; the talent
  on approval, changes asked for, and due-date changes.

## Disclosure (the collaboration label)

Public posts (Instagram, YouTube, blogs, Google reviews) must carry the collaboration
label: #collab, #ad, #sponsored or Instagram's paid-partnership tag (ASCI guidelines).

- Submitting one requires `disclosure_confirmed`: the talent ticks that the post has
  it.
- When the platform returns the caption (YouTube, or Instagram once enabled), the
  label is also checked automatically. `disclosure_detected` is true, false, or empty
  when it couldn't be checked.
- The host sees both: "Talent confirms the label" and "Label found / not found in the
  caption / not checked".

> **LEGAL REVIEW NEEDED: Google reviews.** Google's policies forbid reviews given in
> return for anything (a stay included), and India's rules on online reviews (IS
> 19000:2022) require paid or incentivised reviews to be disclosed. The gig builder
> warns hosts who choose it, and talent must confirm their review says they got a free
> stay. Consider removing the type before launch.

## Post stats

`SocialStatsProvider` (`stats/base.py`) has one method, `stats_for(url, handle) →
Stats | None`. `CombinedProvider` asks each configured provider in turn:

- **YouTube** (`YouTubeProvider`): the Data API v3 `videos.list` with an API key. It
  returns views, likes, comments, and the title and description for the label check.
  - Set the `youtube-api-key-<env>` secret, then the Terraform variable
    `youtube_stats_enabled = true`.
- **Instagram** (`InstagramProvider`): the Graph API's business discovery. Barterly's
  own business account looks up the talent's public media by their handle and returns
  likes, comments, views where Instagram gives them, and the caption. The token goes in
  a header, never a URL.
  - **Meta app review needed** first. Then set `instagram-graph-token-<env>` and the
    Terraform variables `instagram_stats_enabled = true` and
    `instagram_business_account_id`.

Stats are fetched:
- when a link is submitted;
- by the daily `deliverable_stats` job, at most once every 20 hours per post.

Each fetch is kept as a `PostStats` snapshot.

**Self-reported numbers:** `POST /deliverables/items/<id>/stats/` takes views, likes and
comments with a screenshot (an uploaded photo; the database refuses one without). These
are stored with `source = manual` and shown everywhere as **self-reported**, beside the
latest numbers from the platform.

## Usage rights and the library

Once a deliverable is approved, its `usage_rights` (from the agreement: scope, months,
credit) and `usable_until` (approval date plus those months) are shown beside it.

- `GET /content/library/` lists the host's approved content, newest first, with
  download links. They're signed, valid for 10 minutes, and save rather than open.
- `GET /content/to-review/` lists submissions waiting for the host, oldest first.

## Reminders

The daily `deliverable_reminders` job (09:00 IST) tells the talent when something not
yet handed in is due in two days, due today, or was due yesterday. Each reminder is
sent once.

## Escrow (hybrid gigs)

For bookings with deliverables, escrow's auto-release (`money.escrow._release_due`)
follows them instead of the single-submission flow:

- once **every** deliverable is handed in, the 72-hour window runs from the **last**
  submission, and with no answer the stipend is released (`released_by = system`);
- asking for changes on any one stops the clock until it's handed in again;
- approving the last one releases at once (`released_by = vendor`). If the kill switch
  held it back, the job retries.

Paid gigs (no deliverables) keep the single-submission flow, which is closed to
bookings that track deliverables.
