"use client";

import { useEffect } from "react";

import { ARGUS_UI_BUILD } from "@/lib/build";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Argus page error", error);
  }, [error]);

  return (
    <div className="panel rise" style={{ margin: "1.5rem" }}>
      <h1 style={{ marginTop: 0 }}>Argus hit a page error</h1>
      <p>
        The dashboard could not render this screen. Your paper trading engine is
        separate — this does not mean trades are running unsafely.
      </p>
      <p className="muted-note">
        Try Start Argus again so migrations and the latest build (
        {ARGUS_UI_BUILD}) load, then press Refresh recent prices on Home.
      </p>
      <p className="muted-note">
        Detail: {error.message || "Unknown error"}
        {error.digest ? ` (${error.digest})` : ""}
      </p>
      <div className="form-actions">
        <button type="button" className="btn" onClick={() => reset()}>
          Try again
        </button>
        <a className="btn secondary" href="/today">
          Reload Home
        </a>
      </div>
    </div>
  );
}
