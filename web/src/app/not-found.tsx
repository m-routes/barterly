import { ErrorState } from "@/components/ui/states";

export default function NotFound() {
  return (
    <main id="main" className="page-center">
      <ErrorState
        title="Page not found"
        description="We couldn't find that page. It may have moved, or the link may be wrong."
        action={{ label: "Home", href: "/" }}
      />
    </main>
  );
}
