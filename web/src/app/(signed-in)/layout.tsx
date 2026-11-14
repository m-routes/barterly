import { SessionProvider } from "@/lib/session/session";

/** Pages behind sign-in share one session, loaded once from /api/v1/me/. */
export default function SignedInLayout({ children }: { children: React.ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
