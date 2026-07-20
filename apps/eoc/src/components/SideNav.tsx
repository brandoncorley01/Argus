import Link from "next/link";

import { logoutAction } from "@/lib/actions/auth";
import { roleLabel } from "@/lib/rbac";
import type { CurrentUser } from "@/lib/types";

const NAV = [
  { href: "/overview", label: "Executive Overview" },
  { href: "/operations", label: "Operations" },
  { href: "/services", label: "Services" },
  { href: "/workers", label: "Workers" },
  { href: "/incidents", label: "Incidents" },
  { href: "/market", label: "Market Intelligence" },
  { href: "/strategies", label: "Strategy Laboratory" },
  { href: "/paper", label: "Paper Trading" },
  { href: "/micro-live", label: "Micro-Live Institution" },
  { href: "/audit", label: "Audit Explorer" },
  { href: "/configurations", label: "Configurations" },
  { href: "/policies", label: "Policies" },
  { href: "/administration", label: "Administration", founderOnly: true },
] as const;

export function SideNav({
  user,
  pathname,
}: {
  user: CurrentUser;
  pathname: string;
}) {
  const isFounder = user.roles.includes("FOUNDER");
  const primary = user.roles.includes("FOUNDER")
    ? "FOUNDER"
    : user.roles.includes("OPERATOR")
      ? "OPERATOR"
      : "VIEWER";

  return (
    <aside className="side-nav" aria-label="Primary">
      <div className="brand">
        <div className="brand-mark">Argus</div>
        <div className="brand-sub">Executive Operations Center</div>
      </div>
      <ul className="nav-list">
        {NAV.filter((item) => !("founderOnly" in item && item.founderOnly) || isFounder).map(
          (item) => {
            const current =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className="nav-link"
                  aria-current={current ? "page" : undefined}
                >
                  {item.label}
                </Link>
              </li>
            );
          },
        )}
      </ul>
      <div className="nav-meta">
        <div>
          <strong>{user.username}</strong>
        </div>
        <div>{roleLabel(primary)}</div>
        <form action={logoutAction} style={{ marginTop: "0.75rem" }}>
          <button type="submit" className="btn secondary">
            Sign out
          </button>
        </form>
      </div>
    </aside>
  );
}
