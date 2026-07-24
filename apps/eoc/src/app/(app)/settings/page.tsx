import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader, Panel } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";

export const metadata: Metadata = { title: "Settings" };

export default async function SettingsPage() {
  await requireUser();

  return (
    <>
      <PageHeader title="Settings" description="Live trading stays locked." />

      <Panel title="Controls">
        <p style={{ marginTop: 0, color: "var(--ink-soft)" }}>
          Start and Stop are on <strong>Home</strong>. Use those two buttons there.
        </p>
        <div className="form-actions">
          <Link className="btn" href="/today">
            Go to Home
          </Link>
        </div>
      </Panel>
    </>
  );
}
