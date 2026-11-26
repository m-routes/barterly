"use client";

import { useState } from "react";

import { Chip } from "@/components/ui/StatusChip";
import {
  type PipelineApplicant,
  type Stage,
  STAGES,
  columns,
  initials,
  moveFor,
  stageLabel,
  targetsFor,
  tintFor,
} from "@/lib/vendor/pipeline";

import { badgeLabel } from "../ApplicantTable";

type Props = {
  items: readonly PipelineApplicant[];
  selected: ReadonlySet<string>;
  pending: ReadonlySet<string>;
  onToggle: (id: string) => void;
  onMove: (applicant: PipelineApplicant, to: Stage) => void;
  onReject: (applicant: PipelineApplicant) => void;
  onOpen: (applicant: PipelineApplicant, tab?: "profile" | "chat" | "offer") => void;
  onAnnounce: (message: string) => void;
};

const MIME = "application/x-barterly-applicant";
const PRIMARY: Record<Stage, string> = {
  applied: "Shortlist",
  shortlisted: "Interview",
  interview: "Send offer",
  offered: "Awaiting reply",
};

/**
 * The canvas's four-column pipeline. Every move has three ways in:
 * - drag a card to a column (mouse or touch);
 * - the keyboard: focus a card's "Move" handle, Space or Enter to pick it up, Left and
 *   Right to choose a column, Enter to drop, Escape to cancel (announced as you go);
 * - buttons: the card's main action, or "Move to" for any allowed column.
 */
export function Board(props: Props) {
  const { items, onMove, onAnnounce } = props;
  const [dragging, setDragging] = useState<string | null>(null);
  const [over, setOver] = useState<Stage | null>(null);
  const [lifted, setLifted] = useState<{ id: string; target: Stage } | null>(null);
  const byId = new Map(items.map((a) => [a.id, a]));
  const draggingCard = dragging ? byId.get(dragging) : undefined;
  const liftedCard = lifted ? byId.get(lifted.id) : undefined;

  function drop(id: string, to: Stage) {
    const card = byId.get(id);
    if (!card) return;
    const move = moveFor(card.status, to);
    if (move.kind === "none") {
      onAnnounce(move.reason);
      return;
    }
    onMove(card, to);
  }

  function lift(card: PipelineApplicant) {
    const targets = targetsFor(card.status);
    if (!targets.length) {
      onAnnounce(`${card.applicant.display_name} can't move from here.`);
      return;
    }
    setLifted({ id: card.id, target: targets[0]! });
    onAnnounce(
      `Picked up ${card.applicant.display_name}. Left and right arrows choose a column, ` +
        `Enter drops, Escape cancels. Over ${stageLabel(targets[0]!)}.`,
    );
  }

  function onHandleKey(event: React.KeyboardEvent, card: PipelineApplicant) {
    if (!lifted || lifted.id !== card.id) {
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        lift(card);
      }
      return;
    }
    const targets = targetsFor(card.status);
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const at = targets.indexOf(lifted.target);
      const next =
        targets[(at + (event.key === "ArrowRight" ? 1 : -1) + targets.length) % targets.length]!;
      setLifted({ id: card.id, target: next });
      onAnnounce(`Over ${stageLabel(next)}.`);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setLifted(null);
      drop(card.id, lifted.target);
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      setLifted(null);
      onAnnounce(
        `Cancelled. ${card.applicant.display_name} stays in ${stageLabel(card.status as Stage)}.`,
      );
    }
  }

  return (
    <div className="board-scroll">
      <div className="board">
        {columns(items).map((col) => {
          const allowed =
            (draggingCard && moveFor(draggingCard.status, col.status).kind !== "none") ||
            (liftedCard && lifted?.target === col.status);
          return (
            <section
              key={col.status}
              className={[
                "board__column",
                allowed ? "board__column--target" : "",
                over === col.status && allowed ? "board__column--over" : "",
              ].join(" ")}
              aria-labelledby={`col-${col.status}`}
              onDragOver={(e) => {
                if (!draggingCard || moveFor(draggingCard.status, col.status).kind === "none") {
                  return;
                }
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                setOver(col.status);
              }}
              onDragLeave={() => setOver((o) => (o === col.status ? null : o))}
              onDrop={(e) => {
                e.preventDefault();
                const id = e.dataTransfer.getData(MIME) || dragging;
                setOver(null);
                setDragging(null);
                if (id) drop(id, col.status);
              }}
            >
              <header className="board__column-header">
                <h2 id={`col-${col.status}`} className="board__column-title">
                  {col.label}
                </h2>
                <span className="board__count" aria-label={`${col.cards.length} applicants`}>
                  {col.cards.length}
                </span>
              </header>
              {col.cards.length === 0 ? (
                <p className="board__empty">Nobody here yet.</p>
              ) : (
                <ul className="board__cards">
                  {col.cards.map((card) => (
                    <li key={card.id}>
                      <Card
                        {...props}
                        card={card}
                        lifted={lifted?.id === card.id}
                        onDragStart={(e) => {
                          e.dataTransfer.setData(MIME, card.id);
                          e.dataTransfer.effectAllowed = "move";
                          setDragging(card.id);
                        }}
                        onDragEnd={() => {
                          setDragging(null);
                          setOver(null);
                        }}
                        onHandleKey={(e) => onHandleKey(e, card)}
                        onHandleBlur={() => {
                          if (lifted?.id === card.id) {
                            setLifted(null);
                            onAnnounce("Move cancelled.");
                          }
                        }}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function Card({
  card,
  selected,
  pending,
  lifted,
  onToggle,
  onMove,
  onReject,
  onOpen,
  onDragStart,
  onDragEnd,
  onHandleKey,
  onHandleBlur,
}: Props & {
  card: PipelineApplicant;
  lifted: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  onHandleKey: (e: React.KeyboardEvent) => void;
  onHandleBlur: () => void;
}) {
  const person = card.applicant;
  const name = person.display_name || "Applicant";
  const stage = card.status as Stage;
  const busy = pending.has(card.id);
  const targets = targetsFor(stage);
  const next = targets[0];
  const verified = person.badges.includes("id_verified");

  function primary() {
    if (stage === "offered") return;
    if (next) onMove(card, next);
  }

  return (
    <article
      className={[
        "applicant-card",
        selected.has(card.id) ? "applicant-card--selected" : "",
        lifted ? "applicant-card--lifted" : "",
        busy ? "applicant-card--busy" : "",
      ].join(" ")}
      draggable={targets.length > 0 && !busy}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      aria-busy={busy || undefined}
      aria-labelledby={`card-${card.id}`}
    >
      <div className="applicant-card__top">
        <span className="avatar" style={{ background: tintFor(card.id) }} aria-hidden="true">
          {initials(name)}
        </span>
        <div className="applicant-card__who">
          <button
            type="button"
            id={`card-${card.id}`}
            className="applicant-card__name"
            onClick={() => onOpen(card)}
          >
            {name}
          </button>
          <span className="applicant-card__role">
            {[person.talent_type, person.home_city].filter(Boolean).join(" · ")}
          </span>
        </div>
        <span className="fit-chip">{card.fit.score} fit</span>
      </div>

      <div className="chip-row">
        {verified ? <Chip tone="success">ID verified</Chip> : null}
        {person.badges
          .filter((b) => b !== "id_verified")
          .map((b) => (
            <Chip key={b}>{badgeLabel(b)}</Chip>
          ))}
        {card.tags.map((t) => (
          <span key={t} className="tag">
            {t}
          </span>
        ))}
      </div>

      <div className="applicant-card__meta">
        {card.note_count ? (
          <span>
            {card.note_count} note{card.note_count === 1 ? "" : "s"}
          </span>
        ) : null}
        {card.attachment_count ? (
          <span>
            {card.attachment_count} file{card.attachment_count === 1 ? "" : "s"}
          </span>
        ) : null}
        {card.unread_messages ? (
          <span className="applicant-card__unread">{card.unread_messages} unread</span>
        ) : null}
      </div>

      <div className="applicant-card__actions">
        <button
          type="button"
          className="button button--primary button--small"
          aria-label={
            stage === "offered" ? `${PRIMARY[stage]}: ${name}` : `${PRIMARY[stage]} ${name}`
          }
          disabled={busy || stage === "offered"}
          onClick={primary}
        >
          {PRIMARY[stage]}
        </button>
        {stage === "applied" || stage === "shortlisted" ? (
          <button
            type="button"
            className="button button--secondary button--small"
            disabled={busy}
            aria-label={`Reject ${name}`}
            onClick={() => onReject(card)}
          >
            Reject
          </button>
        ) : (
          <button
            type="button"
            className="button button--secondary button--small"
            aria-label={`Message ${name}`}
            onClick={() => onOpen(card, "chat")}
          >
            Message
          </button>
        )}
      </div>

      <div className="applicant-card__move">
        <input
          type="checkbox"
          className="applicant-card__select"
          aria-label={`Select ${name}`}
          checked={selected.has(card.id)}
          onChange={() => onToggle(card.id)}
        />
        {targets.length ? (
          <>
            <label className="visually-hidden" htmlFor={`move-${card.id}`}>
              Move {name} to
            </label>
            <select
              id={`move-${card.id}`}
              className="field__control field__control--select field__control--small"
              value=""
              disabled={busy}
              onChange={(e) => {
                if (e.target.value) onMove(card, e.target.value as Stage);
              }}
            >
              <option value="">Move to…</option>
              {STAGES.filter((s) => targets.includes(s.status)).map((s) => (
                <option key={s.status} value={s.status}>
                  {s.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="move-handle"
              aria-pressed={lifted}
              aria-describedby="board-move-help"
              disabled={busy}
              aria-label={`Move ${name} with the keyboard`}
              onKeyDown={onHandleKey}
              onBlur={onHandleBlur}
            >
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                <path
                  d="M9 5h.01M15 5h.01M9 12h.01M15 12h.01M9 19h.01M15 19h.01"
                  stroke="currentColor"
                  strokeWidth="3"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </>
        ) : null}
      </div>
    </article>
  );
}
