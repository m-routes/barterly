"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Chip, type ChipTone } from "@/components/ui/StatusChip";
import { FormError, TextField } from "@/components/ui/fields";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { BillingOverview, BillingPlan, BillingSubscription, Invoice } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";

import { rupees } from "./money";

const FEATURE_LABELS: Record<string, string> = {
  talent_search: "Talent search",
  agreements: "Agreements",
  ai_fit_scores: "AI fit scores",
  team_roles: "Team roles",
};

const STATUS: Record<BillingSubscription["status"], { label: string; tone: ChipTone }> = {
  created: { label: "Waiting for checkout", tone: "pending" },
  authenticated: { label: "Trial", tone: "success" },
  active: { label: "Active", tone: "success" },
  past_due: { label: "Payment failed", tone: "danger" },
  halted: { label: "Payment failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  completed: { label: "Ended", tone: "neutral" },
};

/** Go to Razorpay's hosted checkout (also where a card is updated). */
function goToCheckout(url: string) {
  window.location.assign(url);
}

/** The vendor's plan, what it allows, other plans, and GST invoices. */
export function BillingPage() {
  const overview = useLoad(() => unwrap(api.GET("/api/v1/billing/")), "billing");
  const plans = useLoad(() => unwrap(api.GET("/api/v1/billing/plans/")), "plans");

  if (overview.state.status === "loading" || plans.state.status === "loading") {
    return <LoadingState label="Loading your plan…" />;
  }
  if (overview.state.status === "error" || plans.state.status === "error") {
    const error =
      overview.state.status === "error"
        ? overview.state.error
        : (plans.state as { error: unknown }).error;
    return (
      <div className="page">
        <ErrorState
          title="We couldn't load billing"
          description={describeError(error)}
          retry={() => {
            void overview.reload();
            void plans.reload();
          }}
        />
      </div>
    );
  }
  return (
    <div className="page page--wide">
      <header className="page__header">
        <h1 className="page__title">Billing</h1>
        <p className="page__lead">
          Your plan, what it lets you do, and your GST invoices. Payments go through Razorpay.
        </p>
      </header>
      <div className="stack">
        <CurrentPlan
          overview={overview.state.data}
          onChanged={(next) => overview.setData(() => next)}
        />
        <PlanChooser
          plans={plans.state.data}
          overview={overview.state.data}
          onChanged={() => void overview.refresh()}
        />
        <Invoices />
      </div>
    </div>
  );
}

function CurrentPlan({
  overview,
  onChanged,
}: {
  overview: BillingOverview;
  onChanged: (next: BillingOverview) => void;
}) {
  const { subscription: sub, entitlements: ent } = overview;
  const [cancelling, setCancelling] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const failing = sub && (sub.status === "past_due" || sub.status === "halted");

  async function cancel() {
    setBusy(true);
    setError("");
    try {
      const updated = await unwrap(
        api.POST("/api/v1/billing/cancel/", { body: { at_period_end: true } }),
      );
      setCancelling(false);
      onChanged({ ...overview, subscription: updated });
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel stack-sm" aria-labelledby="plan-title">
      <div className="panel__header panel__header--row">
        <h2 id="plan-title" className="panel__title">
          Your plan: {ent.plan_name}
        </h2>
        {sub ? <Chip tone={STATUS[sub.status].tone}>{STATUS[sub.status].label}</Chip> : null}
      </div>
      {failing ? (
        <div className="note note--warning" role="alert">
          <p>
            We couldn&apos;t take your last payment. Razorpay will try again
            {sub.grace_until
              ? `; your plan's features stay on until ${formatDate(sub.grace_until)}`
              : ""}
            . Live gigs keep running either way.
          </p>
          {sub.checkout_url ? (
            <Button onClick={() => goToCheckout(sub.checkout_url)}>Update payment method</Button>
          ) : null}
        </div>
      ) : null}
      {sub?.status === "created" && sub.checkout_url ? (
        <div className="note">
          <p>Your {sub.plan.name} plan starts once you finish paying at checkout.</p>
          <Button onClick={() => goToCheckout(sub.checkout_url)}>Finish checkout</Button>
        </div>
      ) : null}
      <dl className="summary">
        <div>
          <dt>Live gigs</dt>
          <dd>
            {ent.live_gigs} of {ent.max_live_gigs ?? "unlimited"}
          </dd>
        </div>
        {sub?.trial_ends_at && sub.status === "authenticated" ? (
          <div>
            <dt>Free trial</dt>
            <dd>Until {formatDate(sub.trial_ends_at)}, then billed monthly</dd>
          </div>
        ) : null}
        {sub?.current_period_end && sub.status === "active" ? (
          <div>
            <dt>{sub.cancel_at_period_end ? "Ends" : "Renews"}</dt>
            <dd>{formatDate(sub.current_period_end)}</dd>
          </div>
        ) : null}
        {sub?.pending_plan ? (
          <div>
            <dt>Changing to</dt>
            <dd>
              {sub.pending_plan.name} at the end of this period. Live gigs keep running; new ones
              need to fit its limit.
            </dd>
          </div>
        ) : null}
      </dl>
      {!ent.can_post_gig ? <p className="note note--warning">{ent.reason}</p> : null}
      <ul className="feature-list" aria-label="What your plan includes">
        {Object.entries(ent.features).map(([flag, on]) => (
          <li key={flag} className={on ? "feature-list__on" : "feature-list__off"}>
            <span aria-hidden="true">{on ? "✓" : "–"}</span> {FEATURE_LABELS[flag] ?? flag}
            <span className="visually-hidden">{on ? " included" : " not included"}</span>
          </li>
        ))}
      </ul>
      <p className="field__hint">
        Invoices use the business name, GSTIN and address on your{" "}
        <Link href="/onboarding/vendor">business profile</Link>.
      </p>
      {sub && ["authenticated", "active"].includes(sub.status) && !sub.cancel_at_period_end ? (
        <div>
          <Button variant="ghost" onClick={() => setCancelling(true)}>
            Cancel plan
          </Button>
        </div>
      ) : null}
      {cancelling ? (
        <Dialog
          title="Cancel your plan?"
          description="It stays on until the end of the period you've paid for, then you move to Free: one live gig, no paid features."
          onClose={() => setCancelling(false)}
          footer={
            <>
              <Button busy={busy} onClick={() => void cancel()}>
                Cancel at period end
              </Button>
              <Button variant="ghost" onClick={() => setCancelling(false)}>
                Keep my plan
              </Button>
            </>
          }
        >
          <FormError message={error} />
        </Dialog>
      ) : null}
    </section>
  );
}

function PlanChooser({
  plans,
  overview,
  onChanged,
}: {
  plans: BillingPlan[];
  overview: BillingOverview;
  onChanged: () => void;
}) {
  const sub = overview.subscription;
  const paying = sub && ["authenticated", "active"].includes(sub.status);
  const current = paying ? sub.plan : null;
  const [coupon, setCoupon] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function choose(plan: BillingPlan) {
    setBusy(plan.code);
    setError("");
    try {
      if (paying) {
        await unwrap(api.POST("/api/v1/billing/change-plan/", { body: { plan: plan.code } }));
        onChanged();
      } else {
        const created = await unwrap(
          api.POST("/api/v1/billing/subscribe/", {
            body: { plan: plan.code, ...(coupon.trim() ? { coupon: coupon.trim() } : {}) },
          }),
        );
        goToCheckout(created.checkout_url);
      }
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel stack-sm" aria-labelledby="plans-title">
      <h2 id="plans-title" className="panel__title">
        Plans
      </h2>
      <ul className="plan-grid">
        {plans.map((plan) => {
          const isCurrent = current?.code === plan.code;
          const pending = sub?.pending_plan?.code === plan.code;
          const upgrade = current ? plan.price_paise > current.price_paise : true;
          return (
            <li
              key={plan.code}
              className={`plan-card${isCurrent ? " plan-card--current" : ""}`}
              aria-labelledby={`plan-${plan.code}`}
            >
              <h3 id={`plan-${plan.code}`} className="plan-card__name">
                {plan.name}
              </h3>
              <p className="plan-card__price">
                {rupees(plan.price_paise)}
                <span className="plan-card__per"> / month + {plan.gst_percent}% GST</span>
              </p>
              <p className="field__hint">{plan.description}</p>
              <ul className="feature-list">
                <li className="feature-list__on">
                  <span aria-hidden="true">✓</span>{" "}
                  {plan.max_live_gigs == null
                    ? "Unlimited live gigs"
                    : `${plan.max_live_gigs} live gig${plan.max_live_gigs === 1 ? "" : "s"}`}
                </li>
                {Object.entries(plan.features).map(([flag, on]) => (
                  <li key={flag} className={on ? "feature-list__on" : "feature-list__off"}>
                    <span aria-hidden="true">{on ? "✓" : "–"}</span> {FEATURE_LABELS[flag] ?? flag}
                    <span className="visually-hidden">{on ? " included" : " not included"}</span>
                  </li>
                ))}
              </ul>
              {isCurrent ? (
                <Chip tone="success">Your plan</Chip>
              ) : pending ? (
                <Chip tone="pending">From your next period</Chip>
              ) : (
                <Button
                  variant={upgrade ? "primary" : "secondary"}
                  busy={busy === plan.code}
                  disabled={busy !== null}
                  onClick={() => void choose(plan)}
                >
                  {!paying ? `Choose ${plan.name}` : upgrade ? "Upgrade now" : "Downgrade"}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      {!paying ? (
        <TextField
          label="Have a code?"
          optional
          hint="Launch codes give a free trial before the first charge."
          value={coupon}
          onChange={(e) => setCoupon(e.target.value)}
        />
      ) : (
        <p className="field__hint">
          Upgrades start now (Razorpay charges the difference). Downgrades start at the end of the
          period you&apos;ve paid for; live gigs keep running.
        </p>
      )}
      <FormError message={error} />
    </section>
  );
}

function Invoices() {
  const { state, reload } = useLoad(
    () => unwrap(api.GET("/api/v1/billing/invoices/", { params: { query: { page_size: 50 } } })),
    "invoices",
  );
  const [error, setError] = useState("");

  async function download(invoice: Invoice) {
    setError("");
    try {
      const link = await unwrap(
        api.GET("/api/v1/billing/invoices/{invoice_id}/pdf/", {
          params: { path: { invoice_id: invoice.id } },
        }),
      );
      window.open(link.url, "_blank", "noopener");
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <section className="panel stack-sm" aria-labelledby="invoices-title">
      <h2 id="invoices-title" className="panel__title">
        GST invoices
      </h2>
      {state.status === "loading" ? <LoadingState label="Loading invoices…" /> : null}
      {state.status === "error" ? (
        <ErrorState
          title="We couldn't load your invoices"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      ) : null}
      {state.status === "ready" && state.data.results.length === 0 ? (
        <p className="field__hint">
          No invoices yet. One is made, and emailed to you, for every payment.
        </p>
      ) : null}
      {state.status === "ready" && state.data.results.length ? (
        <div className="table-wrap">
          <table className="table">
            <caption className="visually-hidden">GST invoices, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Invoice</th>
                <th scope="col">Date</th>
                <th scope="col">Plan</th>
                <th scope="col" className="num">
                  Taxable
                </th>
                <th scope="col" className="num">
                  GST
                </th>
                <th scope="col" className="num">
                  Total
                </th>
                <th scope="col">
                  <span className="visually-hidden">Download</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {state.data.results.map((invoice) => (
                <tr key={invoice.id}>
                  <th scope="row">{invoice.number}</th>
                  <td>{formatDate(invoice.issued_at)}</td>
                  <td>{invoice.plan_name}</td>
                  <td className="num">{rupees(invoice.taxable_paise)}</td>
                  <td className="num">
                    {rupees(invoice.tax_paise)}
                    <span className="table__sub">
                      {invoice.igst_paise ? " IGST" : " CGST + SGST"}
                    </span>
                  </td>
                  <td className="num">{rupees(invoice.total_paise)}</td>
                  <td>
                    <Button
                      variant="ghost"
                      disabled={!invoice.pdf_ready}
                      onClick={() => void download(invoice)}
                    >
                      {invoice.pdf_ready ? "Download PDF" : "Preparing"}
                      <span className="visually-hidden"> {invoice.number}</span>
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <FormError message={error} />
    </section>
  );
}
