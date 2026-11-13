import Link from "next/link";

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="logo" aria-label="Barterly home">
      <span className="logo__mark" aria-hidden="true">
        b
      </span>
      <span className="logo__word">Barterly</span>
    </Link>
  );
}
