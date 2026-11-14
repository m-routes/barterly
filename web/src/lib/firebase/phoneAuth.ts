/**
 * Firebase phone (OTP) sign-in, behind a small interface so the login form can be
 * tested with a fake. Firebase is only used to prove the phone number: once we have
 * its ID token, the API issues our own session and the Firebase session is dropped.
 */

export type FirebaseWebConfig = {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
};

export type PendingCode = {
  /** Check the code; resolves to the Firebase ID token for the API's exchange. */
  confirm(code: string): Promise<string>;
};

export interface PhoneSignIn {
  /** Send an OTP to an E.164 number. `container` hosts the invisible reCAPTCHA. */
  sendCode(phoneE164: string, container: HTMLElement): Promise<PendingCode>;
  /** Drop the Firebase session and reCAPTCHA once the API session exists. */
  reset(): Promise<void>;
}

/** Friendly messages for the Firebase error codes a person can cause. */
const MESSAGES: Record<string, string> = {
  "auth/invalid-phone-number": "That number doesn't look right. Check it and try again.",
  "auth/missing-phone-number": "Enter your mobile number.",
  "auth/too-many-requests": "Too many attempts. Wait a few minutes and try again.",
  "auth/quota-exceeded": "We can't send codes right now. Try again later.",
  "auth/invalid-verification-code": "That code isn't right. Check the SMS and try again.",
  "auth/code-expired": "That code has expired. Send a new one.",
  "auth/captcha-check-failed": "We couldn't verify this browser. Reload the page and try again.",
  "auth/network-request-failed": "You seem to be offline. Check your connection and try again.",
  "auth/user-disabled": "This number has been blocked from signing in.",
};

export function phoneAuthMessage(error: unknown): string {
  const code =
    typeof error === "object" && error !== null && "code" in error
      ? String((error as { code: unknown }).code)
      : "";
  return MESSAGES[code] ?? "We couldn't sign you in. Try again.";
}

/** The real implementation. Firebase is imported on first use, not in the page bundle. */
export function firebasePhoneSignIn(config: FirebaseWebConfig): PhoneSignIn {
  let verifier: { clear(): void } | null = null;

  async function auth() {
    const [{ initializeApp, getApps }, authModule] = await Promise.all([
      import("@firebase/app"),
      import("@firebase/auth"),
    ]);
    const app = getApps()[0] ?? initializeApp(config);
    const instance = authModule.getAuth(app);
    instance.languageCode = "en";
    return { authModule, instance };
  }

  return {
    async sendCode(phoneE164, container) {
      const { authModule, instance } = await auth();
      verifier?.clear();
      const recaptcha = new authModule.RecaptchaVerifier(instance, container, {
        size: "invisible",
      });
      verifier = recaptcha;
      const confirmation = await authModule.signInWithPhoneNumber(instance, phoneE164, recaptcha);
      return {
        async confirm(code) {
          const credential = await confirmation.confirm(code);
          return credential.user.getIdToken();
        },
      };
    },
    async reset() {
      verifier?.clear();
      verifier = null;
      const { authModule, instance } = await auth();
      await authModule.signOut(instance);
    },
  };
}
