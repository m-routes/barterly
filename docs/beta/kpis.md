# Beta KPIs

Back office → **Beta KPIs** (Ops, Trust, Finance and super admins). Pick a 7, 28 or
90-day window ending today (IST). Each card shows the value, the target, whether it's
met, and how many gigs, bookings or reviews it's based on. The trend table shows the
28-day values each week, from the daily `analytics_kpi_snapshot` job (00:30 IST).

The KPIs come from the marketplace's own records (gigs, applications, bookings,
reviews), not from product analytics. They need no consent, cover everyone, and no
person can be picked out of them. `backend/apps/analytics/kpis.py` is the source of
truth for each definition; this page explains them.

| KPI | Definition | Target |
| --- | --- | --- |
| Applications per gig | Gigs first published in the window and at least 14 days old: the average number of applications each got in its first 14 days. | **8 or more** |
| Fill rate within 14 days | Of the same gigs: the share with a booking created within 14 days of publishing. | **70% or more** |
| Time to first applicant | Gigs first published in the window: the median hours from publishing to the first application. Gigs with none yet are counted in the note. | Lower is better (no target) |
| Completion rate | Confirmed stays that ended in the window and are settled: the share completed or reviewed (vs no-show, disputed, refunded or cancelled). | Watch (go/no-go: 85%) |
| No-show rate | Confirmed stays due to start in the window (not cancelled): the share marked no-show. | **Under 5%** |
| Disputes | Bookings moved to *disputed* in the window, and the rate per 100 stays started. | Watch (go/no-go: under 3 per 100) |
| Average rating | Reviews published in the window: the average overall stars, and separately for hosts and for talent. | Watch (go/no-go: 4.3 or more) |
| Host churn | Hosts who had a gig live in the previous window of the same length but none in this one, as a share of the former. | Lower is better (go/no-go: under 20%) |

**Small numbers.** Early on a card may say "Not enough data yet", or rest on a handful
of gigs. Read the "Based on" line before acting on a percentage.

**Why "mature" gigs.** A gig published yesterday hasn't had its 14 days, so counting it
would make applications and fill rate look worse than they are. The two 14-day KPIs only
count gigs published at least 14 days before now.
