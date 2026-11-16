"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { FormError, TextField } from "@/components/ui/fields";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { AgreementVersion, SignChallenge } from "@/lib/api/types";
import { phoneAuthMessage, type PendingCode, type PhoneSignIn } from "@/lib/firebase/phoneAuth";

/**
 * Signing one version: read the consent statement, tick it, re-confirm the phone with a
 * one-time code (when the API asks for it), and sign. The API records the time, IP
 * address and device with the signature.
 */
export function SignPanel({
  version,
  phone,
  phoneSignIn,
  onSigned,
}: {
  version: AgreementVersion;
  /** The signer's own number (E.164); the code goes there. */
  phone: string;
  /** Null when this site has no phone sign-in set up. */
  phoneSignIn: PhoneSignIn | null;
  onSigned: () => void;
}) {
  const [challenge, setChallenge] = useState<SignChallenge | null>(null);
  const [consent, setConsent] = useState(false);
  const [pending, setPending] = useState<PendingCode | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recaptchaHost, setRecaptchaHost] = useState<HTMLDivElement | null>(null);
  const path = { params: { path: { version_id: version.id } } };

  async function start() {
    setBusy(true);
    setError("");
    try {
      setChallenge(await unwrap(api.GET("/api/v1/agreement-versions/{version_id}/sign/", path)));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function sendCode() {
    if (!phoneSignIn || !recaptchaHost) return;
    setBusy(true);
    setError("");
    try {
      setPending(await phoneSignIn.sendCode(phone, recaptchaHost));
    } catch (err) {
      setError(phoneAuthMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function sign(event: React.FormEvent) {
    event.preventDefault();
    if (!challenge) return;
    setBusy(true);
    setError("");
    let otpToken = "";
    try {
      if (challenge.method === "otp") {
        if (!pending) return;
        try {
          otpToken = await pending.confirm(code.trim());
        } catch (err) {
          setError(phoneAuthMessage(err));
          return;
        }
      }
      await unwrap(
        api.POST("/api/v1/agreement-versions/{version_id}/sign/", {
          ...path,
          body: { consent, document_sha256: challenge.document_sha256, otp_token: otpToken },
        }),
      );
      onSigned();
    } catch (err) {
      setError(describeError(err));
      setPending(null);
      setCode("");
    } finally {
      setBusy(false);
      if (otpToken) void phoneSignIn?.reset();
    }
  }

  if (!challenge) {
    return (
      <div className="stack-sm">
        <FormError message={error} />
        <div>
          <Button busy={busy} onClick={() => void start()}>
            Sign version {version.number}
          </Button>
        </div>
      </div>
    );
  }

  const needsOtp = challenge.method === "otp";
  const ready = consent && (!needsOtp || (pending && /^\d{6}$/.test(code.trim())));

  return (
    <form className="sign-panel stack-sm" onSubmit={(e) => void sign(e)} noValidate>
      <label className="checkbox checkbox--top">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>{challenge.consent_text}</span>
      </label>
      {needsOtp ? (
        phoneSignIn ? (
          pending ? (
            <TextField
              label={`Code sent to ${challenge.phone_hint}`}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              hint="Confirming your phone is part of your signature."
            />
          ) : (
            <div className="stack-sm">
              <p className="field__hint">
                To sign, confirm it&apos;s you with a code sent to {challenge.phone_hint}.
              </p>
              <div>
                <Button
                  variant="secondary"
                  busy={busy}
                  disabled={!consent}
                  onClick={() => void sendCode()}
                >
                  Send code
                </Button>
              </div>
            </div>
          )
        ) : (
          <p className="form-error">
            Signing needs phone confirmation, which isn&apos;t set up here.
          </p>
        )
      ) : null}
      <div ref={setRecaptchaHost} />
      <FormError message={error} />
      <div className="actions-row actions-row--start">
        <Button type="submit" busy={busy && (!needsOtp || !!pending)} disabled={!ready}>
          Sign
        </Button>
      </div>
    </form>
  );
}
