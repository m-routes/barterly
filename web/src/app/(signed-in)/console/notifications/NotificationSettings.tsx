"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { FormError, SelectField, TextField } from "@/components/ui/fields";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type {
  NotificationChannel,
  NotificationPreferenceChange as Change,
  NotificationPreferences,
} from "@/lib/api/types";
import { useLoad } from "@/lib/hooks/useLoad";

const CHANNEL_LABELS: Record<NotificationChannel, string> = {
  in_app: "In app",
  push: "Push",
  email: "Email",
  sms: "SMS",
  whatsapp: "WhatsApp",
};

/** Language, quiet hours, and which channels each kind of notification uses. */
export function NotificationSettings() {
  const { state, reload, setData } = useLoad(
    () => unwrap(api.GET("/api/v1/notifications/preferences/")),
    "notification-settings",
  );
  if (state.status === "loading") return <LoadingState label="Loading your settings…" />;
  if (state.status === "error") {
    return (
      <div className="page">
        <ErrorState
          title="We couldn't load your settings"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      </div>
    );
  }
  return <SettingsForm initial={state.data} onSaved={(saved) => setData(() => saved)} />;
}

function SettingsForm({
  initial,
  onSaved,
}: {
  initial: NotificationPreferences;
  onSaved: (saved: NotificationPreferences) => void;
}) {
  const [prefs, setPrefs] = useState(initial);
  const [changes, setChanges] = useState<Change[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const channels = prefs.channels_available;

  function toggle(eventType: string, channel: NotificationChannel, enabled: boolean) {
    setSaved(false);
    setPrefs((p) => ({
      ...p,
      event_types: p.event_types.map((t) =>
        t.key === eventType
          ? { ...t, channels: { ...t.channels, [channel]: { ...t.channels[channel]!, enabled } } }
          : t,
      ),
    }));
    setChanges((list) => [
      ...list.filter((c) => !(c.event_type === eventType && c.channel === channel)),
      { event_type: eventType as Change["event_type"], channel, enabled },
    ]);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const updated = await unwrap(
        api.PUT("/api/v1/notifications/preferences/", {
          body: {
            locale: prefs.locale,
            quiet_hours_enabled: prefs.quiet_hours_enabled,
            quiet_start: prefs.quiet_start,
            quiet_end: prefs.quiet_end,
            changes,
          },
        }),
      );
      setPrefs(updated);
      setChanges([]);
      setSaved(true);
      onSaved(updated);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="page page--narrow" onSubmit={(e) => void save(e)} noValidate>
      <header className="page__header">
        <Link href="/console/notifications" className="back-link">
          Notifications
        </Link>
        <h1 className="page__title">Notification settings</h1>
      </header>
      <div className="stack">
        <section className="panel stack-sm" aria-labelledby="general-title">
          <h2 id="general-title" className="panel__title">
            Language and quiet hours
          </h2>
          <SelectField
            label="Language"
            options={[
              { value: "en", label: "English" },
              { value: "hi", label: "हिन्दी (Hindi)" },
            ]}
            value={prefs.locale}
            onChange={(e) =>
              setPrefs((p) => ({
                ...p,
                locale: e.target.value as NotificationPreferences["locale"],
              }))
            }
          />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={prefs.quiet_hours_enabled}
              onChange={(e) => setPrefs((p) => ({ ...p, quiet_hours_enabled: e.target.checked }))}
            />
            Quiet hours: hold push, SMS and WhatsApp until they end
          </label>
          <div className="form-grid form-grid--two">
            <TextField
              label="From (India time)"
              type="time"
              disabled={!prefs.quiet_hours_enabled}
              value={prefs.quiet_start}
              onChange={(e) => setPrefs((p) => ({ ...p, quiet_start: e.target.value }))}
            />
            <TextField
              label="Until"
              type="time"
              disabled={!prefs.quiet_hours_enabled}
              value={prefs.quiet_end}
              onChange={(e) => setPrefs((p) => ({ ...p, quiet_end: e.target.value }))}
            />
          </div>
          <p className="field__hint">
            Urgent reminders, like an offer about to expire, still come through.
          </p>
        </section>

        <section className="panel stack-sm" aria-labelledby="channels-title">
          <h2 id="channels-title" className="panel__title">
            What you hear about, and how
          </h2>
          <div className="table-scroll">
            <table className="pref-table">
              <thead>
                <tr>
                  <th scope="col">Notification</th>
                  {channels.map((c) => (
                    <th key={c} scope="col">
                      {CHANNEL_LABELS[c]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {prefs.event_types.map((t) => (
                  <tr key={t.key}>
                    <th scope="row">
                      {t.label}
                      {t.urgent ? <span className="field__hint"> (urgent)</span> : null}
                    </th>
                    {channels.map((c) => {
                      const setting = t.channels[c];
                      if (!setting) return <td key={c} />;
                      return (
                        <td key={c}>
                          <input
                            type="checkbox"
                            aria-label={`${t.label} by ${CHANNEL_LABELS[c]}`}
                            checked={setting.enabled}
                            disabled={setting.locked}
                            onChange={(e) => toggle(t.key, c, e.target.checked)}
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="field__hint">In-app notifications are your inbox and are always on.</p>
        </section>

        <FormError message={error} />
        <div className="actions-row actions-row--start">
          <Button type="submit" busy={busy}>
            Save settings
          </Button>
          {saved ? <span role="status">Saved.</span> : null}
        </div>
      </div>
    </form>
  );
}
