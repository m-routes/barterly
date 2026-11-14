"use client";

/** Last resort when the root layout itself fails; it must render its own <html>. */
export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="en-IN">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          background: "#FBF8F3",
          color: "#1F2A24",
          padding: "2rem",
        }}
      >
        <h1>Something went wrong</h1>
        <p>Barterly hit a problem loading this page.</p>
        <button type="button" onClick={reset} style={{ minHeight: 44, padding: "0 1rem" }}>
          Try again
        </button>
      </body>
    </html>
  );
}
