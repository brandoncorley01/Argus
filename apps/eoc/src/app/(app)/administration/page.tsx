import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { CreateUserForm } from "@/components/CreateUserForm";
import { PageHeader, Panel } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import { isFounder } from "@/lib/rbac";

export const metadata: Metadata = { title: "Administration" };

export default async function AdministrationPage() {
  const user = await requireUser();
  if (!isFounder(user)) {
    redirect("/overview");
  }

  return (
    <>
      <PageHeader
        title="Administration"
        description="Founder-only institutional administration. User creation still requires backend FOUNDER authority and CSRF."
      />

      <div className="grid grid-2">
        <Panel title="Session">
          <dl style={{ margin: 0, display: "grid", gap: "0.45rem" }}>
            <div>
              <dt className="metric-label">User</dt>
              <dd style={{ margin: 0 }}>{user.username}</dd>
            </div>
            <div>
              <dt className="metric-label">Email</dt>
              <dd style={{ margin: 0 }}>{user.email ?? "—"}</dd>
            </div>
            <div>
              <dt className="metric-label">Roles</dt>
              <dd style={{ margin: 0 }}>{user.roles.join(", ")}</dd>
            </div>
            <div>
              <dt className="metric-label">Session expires</dt>
              <dd style={{ margin: 0 }}>
                {formatTimestamp(user.session_expires_at)}
              </dd>
            </div>
          </dl>
        </Panel>

        <Panel title="Create user">
          <CreateUserForm />
        </Panel>
      </div>
    </>
  );
}
