"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/Button";
import { FormError, TextField } from "@/components/ui/fields";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { SignInResult } from "@/lib/api/types";
import {
  firebasePhoneSignIn,
  phoneAuthMessage,
  type FirebaseWebConfig,
  type PendingCode,
  type PhoneSignIn,
} from "@/lib/firebase/phoneAuth";
import { homeFor, safeNextPath } from "@/lib/session/routing";
import {
  normalizeIndianMobile,
  otpSchema,
  phoneSchema,
  type OtpForm,
  type PhoneForm,
} from "@/lib/validation/auth";

const RESEND_SECONDS = 30;

type Props =
  | { config: FirebaseWebConfig; phoneSignIn?: undefined }
  | { config?: undefined; phoneSignIn: PhoneSignIn };

/** Where to go after signing in: `next` if it's a page this person can use, else home. */
export function afterSignIn(result: SignInResult, next: string | null): string {
  const home = homeFor(result.user);
  if (result.needs_role || !result.profile_complete) return home;
  return safeNextPath(next) ?? home;
}

async function exchange(idToken: string): Promise<SignInResult> {
  // The BFF stores the tokens in cookies and returns the rest of the body.
  const data = await unwrap(api.POST("/api/v1/auth/exchange/", { body: { id_token: idToken } }));
  return data as unknown as SignInResult;
}

export function LoginForm(props: Props) {
  const router = useRouter();
  const next = useSearchParams().get("next");
  const signIn = useMemo(
    () => props.phoneSignIn ?? firebasePhoneSignIn(props.config as FirebaseWebConfig),
    [props.phoneSignIn, props.config],
  );
  // Hosts Firebase's invisible reCAPTCHA. State, not a ref, so handlers can read it.
  const [recaptchaHost, setRecaptchaHost] = useState<HTMLDivElement | null>(null);
  const [pending, setPending] = useState<{ phone: string; code: PendingCode } | null>(null);
  const [resendIn, setResendIn] = useState(0);

  const phoneForm = useForm<PhoneForm>({
    resolver: zodResolver(phoneSchema),
    defaultValues: { phone: "" },
  });
  const otpForm = useForm<OtpForm>({
    resolver: zodResolver(otpSchema),
    defaultValues: { code: "" },
  });

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [resendIn]);

  async function sendCode(phone: string) {
    const e164 = normalizeIndianMobile(phone);
    if (!e164 || !recaptchaHost) return;
    try {
      const code = await signIn.sendCode(e164, recaptchaHost);
      setPending({ phone: e164, code });
      setResendIn(RESEND_SECONDS);
      otpForm.reset({ code: "" });
    } catch (error) {
      // Show the error on whichever step is on screen.
      const form = pending ? otpForm : phoneForm;
      form.setError("root", { message: phoneAuthMessage(error) });
    }
  }

  const [resending, setResending] = useState(false);
  async function resend() {
    if (!pending) return;
    setResending(true);
    await sendCode(pending.phone);
    setResending(false);
  }

  async function verify({ code }: OtpForm) {
    if (!pending) return;
    let idToken: string;
    try {
      idToken = await pending.code.confirm(code);
    } catch (error) {
      otpForm.setError("code", { message: phoneAuthMessage(error) });
      return;
    }
    try {
      const result = await exchange(idToken);
      await signIn.reset().catch(() => undefined);
      router.replace(afterSignIn(result, next));
    } catch (error) {
      otpForm.setError("root", { message: describeError(error) });
    }
  }

  return (
    <div className="auth-card">
      {pending ? (
        <form noValidate onSubmit={otpForm.handleSubmit(verify)} aria-labelledby="otp-heading">
          <h1 id="otp-heading" className="auth-card__title">
            Enter your code
          </h1>
          <p className="auth-card__lead">
            We sent a 6-digit code to <strong>{pending.phone}</strong>.
          </p>
          <TextField
            label="Code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            autoFocus
            error={otpForm.formState.errors.code?.message}
            {...otpForm.register("code")}
          />
          <FormError message={otpForm.formState.errors.root?.message} />
          <Button type="submit" block busy={otpForm.formState.isSubmitting} busyLabel="Checking…">
            Verify and continue
          </Button>
          <div className="auth-card__row">
            <Button variant="ghost" onClick={() => setPending(null)}>
              Change number
            </Button>
            <Button
              variant="ghost"
              disabled={resendIn > 0}
              busy={resending}
              busyLabel="Sending…"
              onClick={() => void resend()}
            >
              {resendIn > 0 ? `Resend code in ${resendIn}s` : "Resend code"}
            </Button>
          </div>
        </form>
      ) : (
        <form
          noValidate
          onSubmit={phoneForm.handleSubmit(({ phone }) => sendCode(phone))}
          aria-labelledby="phone-heading"
        >
          <h1 id="phone-heading" className="auth-card__title">
            Sign in to Barterly
          </h1>
          <p className="auth-card__lead">
            We&apos;ll text you a code. New here? The same steps create your account.
          </p>
          <TextField
            label="Mobile number"
            hint="Indian numbers only for now, e.g. 98765 43210"
            type="tel"
            inputMode="tel"
            autoComplete="tel-national"
            autoFocus
            error={phoneForm.formState.errors.phone?.message}
            {...phoneForm.register("phone")}
          />
          <FormError message={phoneForm.formState.errors.root?.message} />
          <Button
            type="submit"
            block
            busy={phoneForm.formState.isSubmitting}
            busyLabel="Sending code…"
          >
            Send code
          </Button>
        </form>
      )}
      <div ref={setRecaptchaHost} />
    </div>
  );
}
