"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { GigStatusChip } from "@/components/ui/StatusChip";
import { FormError, SelectField, TextArea } from "@/components/ui/fields";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { notify } from "@/lib/api/events";
import type { components } from "@/lib/api/schema";
import { requestBody } from "@/lib/api/types";
import { useLoad } from "@/lib/hooks/useLoad";
import {
  type FilterParams,
  type PipelineApplicant,
  type Stage,
  cleanFilters,
  listQuery,
  moveFor,
  sameFilters,
  stageLabel,
  withStatus,
} from "@/lib/vendor/pipeline";

import { ApplicantDrawer, type DrawerTab } from "./ApplicantDrawer";
import { Board } from "./Board";

type SavedFilter = components["schemas"]["SavedFilter"];
type RejectReason = "not_a_fit" | "dates" | "filled" | "language" | "incomplete" | "other";

/**
 * A gig's applicants as the canvas's kanban: Applied, Shortlisted, Interview, Offered.
 * Moves and bulk actions show at once and are put back if the server says no.
 */
export function Pipeline() {
  const { gigId } = useParams<{ gigId: string }>();
  const [filters, setFilters] = useState<FilterParams>({ sort: "fit" });
  const gig = useLoad(
    () => unwrap(api.GET("/api/v1/gigs/{gig_id}/", { params: { path: { gig_id: gigId } } })),
    gigId,
  );
  const list = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/gigs/{gig_id}/applications/", {
          params: { path: { gig_id: gigId }, query: listQuery(filters) },
        }),
      ),
    `${gigId}:${JSON.stringify(cleanFilters(filters))}`,
  );

  // The board's own copy, so moves show before the server answers.
  const [items, setItems] = useState<PipelineApplicant[]>([]);
  const itemsRef = useRef(items);
  useEffect(() => {
    itemsRef.current = items;
  });
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [rejecting, setRejecting] = useState<PipelineApplicant[] | null>(null);
  const [drawer, setDrawer] = useState<{ id: string; tab: DrawerTab } | null>(null);
  const [announcement, setAnnouncement] = useState("");

  const listData = list.state.status === "ready" ? list.state.data : null;
  useEffect(() => {
    if (!listData) return;
    // The server's answer replaces the board's copy.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setItems(listData.results);
    setSelected((s) => new Set([...s].filter((id) => listData.results.some((a) => a.id === id))));
  }, [listData]);

  const announce = useCallback((message: string) => setAnnouncement(message), []);

  /**
   * Show a change now; on failure put back the cards it touched (only those, so other
   * changes made meanwhile survive) and say what happened.
   */
  async function optimistic(
    ids: string[],
    change: (items: PipelineApplicant[]) => PipelineApplicant[],
    request: () => Promise<Set<string> | void>,
    failure: (err: unknown) => string,
  ) {
    const before = new Map(
      itemsRef.current.filter((a) => ids.includes(a.id)).map((a) => [a.id, a]),
    );
    setItems((current) => change(current));
    setPending((p) => new Set([...p, ...ids]));
    const rollback = (failed: Iterable<string>) => {
      const back = new Set(failed);
      setItems((current) => {
        const present = new Set(current.map((a) => a.id));
        const restored = current.map((a) => (back.has(a.id) ? (before.get(a.id) ?? a) : a));
        // Cards the change removed come back too.
        const missing = [...back].filter((id) => !present.has(id) && before.has(id));
        return [...restored, ...missing.map((id) => before.get(id)!)];
      });
    };
    try {
      const failed = await request();
      if (failed && failed.size) {
        rollback(failed);
        const message = `${failed.size} of ${ids.length} couldn't be changed and were put back.`;
        notify(message);
        announce(message);
      }
    } catch (err) {
      rollback(ids);
      const message = failure(err);
      notify(message);
      announce(message);
    } finally {
      setPending((p) => new Set([...p].filter((id) => !ids.includes(id))));
    }
  }

  function move(card: PipelineApplicant, to: Stage) {
    const name = card.applicant.display_name;
    const plan = moveFor(card.status, to);
    if (plan.kind === "none") {
      announce(plan.reason);
      return;
    }
    if (plan.kind === "offer") {
      setDrawer({ id: card.id, tab: "offer" });
      announce(`Send ${name} the terms to move them to Offered.`);
      return;
    }
    announce(`${name} moved to ${stageLabel(to)}.`);
    void optimistic(
      [card.id],
      (current) => withStatus(current, [card.id], plan.to),
      async () => {
        await unwrap(
          api.POST("/api/v1/applications/{application_id}/status/", {
            params: { path: { application_id: card.id } },
            body: { status: plan.to },
          }),
        );
      },
      (err) =>
        `Couldn't move ${name} to ${stageLabel(to)}: ${describeError(err)} ` +
        `They're back in ${stageLabel(card.status as Stage)}.`,
    );
  }

  function bulkShortlist() {
    const ids = itemsRef.current
      .filter((a) => selected.has(a.id) && a.status === "applied")
      .map((a) => a.id);
    if (!ids.length) {
      announce("Only applicants in Applied can be shortlisted.");
      return;
    }
    announce(`Shortlisting ${ids.length}.`);
    setSelected(new Set());
    void optimistic(
      ids,
      (current) => withStatus(current, ids, "shortlisted"),
      () => bulk("shortlist", ids),
      (err) => `Couldn't shortlist them: ${describeError(err)} They were put back.`,
    );
  }

  async function bulk(
    action: "shortlist" | "reject",
    ids: string[],
    reason?: RejectReason,
    message?: string,
  ): Promise<Set<string>> {
    // prettier-ignore
    const results = await unwrap(
      api.POST("/api/v1/gigs/{gig_id}/applications/bulk/", {
        params: { path: { gig_id: gigId } },
        body: {
          action,
          application_ids: ids,
          ...(reason ? { reason_code: reason } : {}),
          ...(message ? { message } : {}),
        },
      }),
    );
    return new Set(results.filter((r) => !r.ok).map((r) => r.id));
  }

  function reject(cards: PipelineApplicant[], reason: RejectReason, message: string) {
    const ids = cards.map((c) => c.id);
    setRejecting(null);
    setSelected(new Set());
    announce(
      `Rejected ${cards.length === 1 ? cards[0]!.applicant.display_name : `${ids.length} applicants`}.`,
    );
    void optimistic(
      ids,
      (current) => current.filter((a) => !ids.includes(a.id)),
      () => bulk("reject", ids, reason, message),
      (err) => `Couldn't reject: ${describeError(err)} They were put back.`,
    );
  }

  if (gig.state.status === "error" || list.state.status === "error") {
    const error =
      gig.state.status === "error" ? gig.state.error : (list.state as { error: unknown }).error;
    return (
      <div className="page">
        <ErrorState
          title="We couldn't load the applicants"
          description={describeError(error)}
          retry={() => {
            void gig.reload();
            void list.reload();
          }}
          action={{ label: "All gigs", href: "/console/applicants" }}
        />
      </div>
    );
  }

  const selectedCards = items.filter((a) => selected.has(a.id));
  return (
    <div className="page page--wide pipeline">
      <header className="page__header">
        <Link href="/console/applicants" className="back-link">
          All gigs with applicants
        </Link>
        {gig.state.status === "ready" ? (
          <>
            <div className="page__title-row">
              <h1 className="page__title">{gig.state.data.title}</h1>
              <GigStatusChip status={gig.state.data.status} />
            </div>
            <p className="page__lead">
              {gig.state.data.slots ?? 1} slot{gig.state.data.slots === 1 ? "" : "s"} ·{" "}
              <Link href={`/console/gigs/${gigId}/applicants/list`}>
                List view, with rejected and closed applications
              </Link>
            </p>
          </>
        ) : (
          <h1 className="page__title">Applicants</h1>
        )}
      </header>

      <Filters gigId={gigId} filters={filters} onChange={setFilters} />

      <p id="board-move-help" className="visually-hidden">
        Space or Enter picks the card up. Left and right arrows choose a column, Enter drops it,
        Escape cancels.
      </p>
      <div className="visually-hidden" role="status" aria-live="polite">
        {announcement}
      </div>

      {selectedCards.length ? (
        <div className="bulk-bar" role="region" aria-label="Bulk actions">
          <span>{selectedCards.length} selected</span>
          <Button variant="secondary" onClick={bulkShortlist}>
            Shortlist
          </Button>
          <Button variant="secondary" onClick={() => setRejecting(selectedCards)}>
            Reject…
          </Button>
          <Button variant="ghost" onClick={() => setSelected(new Set())}>
            Clear selection
          </Button>
        </div>
      ) : null}

      {list.state.status === "loading" && !items.length ? (
        <LoadingState label="Loading applicants…" />
      ) : (
        <>
          {listData && listData.count > listData.results.length ? (
            <p className="note">
              Showing the best {listData.results.length} of {listData.count}. Narrow the filters to
              see the rest.
            </p>
          ) : null}
          <Board
            items={items}
            selected={selected}
            pending={pending}
            onToggle={(id) =>
              setSelected((s) => {
                const next = new Set(s);
                if (next.has(id)) next.delete(id);
                else next.add(id);
                return next;
              })
            }
            onMove={move}
            onReject={(card) => setRejecting([card])}
            onOpen={(card, tab = "profile") => setDrawer({ id: card.id, tab })}
            onAnnounce={announce}
          />
        </>
      )}

      {rejecting ? (
        <RejectDialog
          cards={rejecting}
          onCancel={() => setRejecting(null)}
          onReject={(reason, message) => reject(rejecting, reason, message)}
        />
      ) : null}

      {drawer ? (
        <ApplicantDrawer
          applicationId={drawer.id}
          tab={drawer.tab}
          onTab={(tab) => setDrawer({ ...drawer, tab })}
          onClose={() => setDrawer(null)}
          onChanged={() => void list.refresh()}
        />
      ) : null}
    </div>
  );
}

function RejectDialog({
  cards,
  onCancel,
  onReject,
}: {
  cards: PipelineApplicant[];
  onCancel: () => void;
  onReject: (reason: RejectReason, message: string) => void;
}) {
  const reasons = useLoad(() => unwrap(api.GET("/api/v1/hiring/rejection-reasons/")), "reasons");
  const [reason, setReason] = useState<RejectReason | "">("");
  const [message, setMessage] = useState("");
  const chosen =
    reasons.state.status === "ready" ? reasons.state.data.find((r) => r.code === reason) : null;
  const who = cards.length === 1 ? cards[0]!.applicant.display_name : `${cards.length} applicants`;
  return (
    <Dialog
      title={`Reject ${who}`}
      description="They're told kindly, with the reason you pick."
      onClose={onCancel}
      footer={
        <>
          <Button disabled={!reason} onClick={() => reason && onReject(reason, message.trim())}>
            Reject
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </>
      }
    >
      {reasons.state.status === "loading" ? <LoadingState label="Loading reasons…" /> : null}
      {reasons.state.status === "error" ? (
        <FormError message={describeError(reasons.state.error)} />
      ) : null}
      {reasons.state.status === "ready" ? (
        <div className="stack-sm">
          <SelectField
            label="Reason"
            options={reasons.state.data.map((r) => ({ value: r.code, label: r.label }))}
            value={reason}
            onChange={(e) => setReason(e.target.value as RejectReason)}
          />
          {chosen ? <p className="note">They&apos;ll read: “{chosen.text}”</p> : null}
          <TextArea
            label="Add a line of your own"
            optional
            maxLength={500}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
        </div>
      ) : null}
    </Dialog>
  );
}

const MIN_FITS = [
  { value: "50", label: "50 or more" },
  { value: "70", label: "70 or more" },
  { value: "85", label: "85 or more" },
];
// "Best fit" is the select's empty choice: the default.
const SORTS = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
];

function Filters({
  gigId,
  filters,
  onChange,
}: {
  gigId: string;
  filters: FilterParams;
  onChange: (f: FilterParams) => void;
}) {
  const ids = useId();
  const [query, setQuery] = useState(filters.q ?? "");
  const saved = useLoad(() => unwrap(api.GET("/api/v1/applicant-filters/")), "saved-filters");
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  // Search as you type, a moment after the typing stops.
  const latest = useRef(filters);
  useEffect(() => {
    latest.current = filters;
  });
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if ((latest.current.q ?? "") !== query.trim()) {
        onChange({ ...latest.current, q: query.trim() || undefined });
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [query, onChange]);

  const mine =
    saved.state.status === "ready" ? saved.state.data.filter((f) => !f.gig || f.gig === gigId) : [];
  const current = mine.find((f) => sameFilters(f.params, filters));

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const created = await unwrap(
        api.POST("/api/v1/applicant-filters/", {
          body: requestBody<SavedFilter>({
            name: name.trim(),
            gig: gigId,
            params: cleanFilters(filters),
          }),
        }),
      );
      saved.setData((list) => [created, ...list]);
      setNaming(false);
      setName("");
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function remove(id: string) {
    const before = saved.state.status === "ready" ? saved.state.data : [];
    saved.setData((list) => list.filter((f) => f.id !== id));
    try {
      await unwrap(
        api.DELETE("/api/v1/applicant-filters/{filter_id}/", {
          params: { path: { filter_id: id } },
        }),
      );
    } catch (err) {
      saved.setData(() => before);
      notify(`Couldn't delete the saved filter: ${describeError(err)}`);
    }
  }

  return (
    <div className="pipeline-filters" role="search" aria-label="Filter applicants">
      <div className="field pipeline-filters__search">
        <label className="visually-hidden" htmlFor={`${ids}-q`}>
          Search applicants
        </label>
        <input
          id={`${ids}-q`}
          type="search"
          className="field__control"
          placeholder="Search applicants"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <SelectField
        label="Sort"
        options={SORTS}
        placeholder="Best fit"
        value={filters.sort && filters.sort !== "fit" ? filters.sort : ""}
        onChange={(e) =>
          onChange({ ...filters, sort: (e.target.value || "fit") as FilterParams["sort"] })
        }
      />
      <SelectField
        label="Fit"
        options={MIN_FITS}
        placeholder="Any fit"
        value={filters.min_score ? String(filters.min_score) : ""}
        onChange={(e) =>
          onChange({ ...filters, min_score: e.target.value ? Number(e.target.value) : undefined })
        }
      />
      <label className={`toggle-chip${filters.badge === "id_verified" ? " toggle-chip--on" : ""}`}>
        <input
          type="checkbox"
          className="toggle-chip__input"
          checked={filters.badge === "id_verified"}
          onChange={(e) =>
            onChange({ ...filters, badge: e.target.checked ? "id_verified" : undefined })
          }
        />
        ID verified only
      </label>
      <div className="field">
        <label className="field__label" htmlFor={`${ids}-tag`}>
          Tag
        </label>
        <input
          id={`${ids}-tag`}
          className="field__control"
          value={filters.tag ?? ""}
          onChange={(e) => onChange({ ...filters, tag: e.target.value || undefined })}
        />
      </div>

      <div className="pipeline-filters__saved">
        <SelectField
          label="Saved filters"
          placeholder={mine.length ? "Choose…" : "None saved yet"}
          options={mine.map((f) => ({ value: f.id, label: f.name }))}
          value={current?.id ?? ""}
          onChange={(e) => {
            const picked = mine.find((f) => f.id === e.target.value);
            if (picked) {
              setQuery(picked.params.q ?? "");
              onChange({ sort: "fit", ...picked.params });
            }
          }}
        />
        {current ? (
          <Button variant="ghost" onClick={() => void remove(current.id)}>
            Delete “{current.name}”
          </Button>
        ) : naming ? (
          <form className="inline-form" onSubmit={(e) => void save(e)}>
            <label className="visually-hidden" htmlFor={`${ids}-name`}>
              Name this filter
            </label>
            <input
              id={`${ids}-name`}
              className="field__control"
              placeholder="Name this filter"
              maxLength={60}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <Button type="submit" variant="secondary" disabled={!name.trim()}>
              Save
            </Button>
            <Button variant="ghost" onClick={() => setNaming(false)}>
              Cancel
            </Button>
          </form>
        ) : (
          <Button variant="ghost" onClick={() => setNaming(true)}>
            Save these filters
          </Button>
        )}
        <FormError message={error} />
      </div>
    </div>
  );
}
