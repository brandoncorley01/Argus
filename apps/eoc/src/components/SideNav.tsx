"use client";

import Link from "next/link";
import { useState } from "react";

import { logoutAction } from "@/lib/actions/auth";
import { roleLabel } from "@/lib/rbac";
import type { CurrentUser } from "@/lib/types";

const PRIMARY = [
  { href: "/today", label: "Today" },
  { href: "/trading", label: "Trading" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/reports", label: "Reports" },
  { href: "/settings", label: "Settings" },
] as const;

const ADVANCED = [
  { href: "/overview", label: "Classic dashboard" },
  { href: "/system-health", label: "System health" },
  { href: "/services", label: "Services" },
  { href: "/workers", label: "Workers" },
  { href: "/operations", label: "Operating mode" },
  { href: "/incidents", label: "Issues" },
  { href: "/audit", label: "Audit" },
  { href: "/paper", label: "Paper details" },
  { href: "/micro-live", label: "Live controls" },
  { href: "/market", label: "Market" },
  { href: "/strategies", label: "Strategies" },
  { href: "/treasury", label: "Treasury" },
  { href: "/configurations", label: "Config" },
  { href: "/policies", label: "Policies" },
  { href: "/administration", label: "Admin", founderOnly: true },
] as const;

function current(pathname: string, href: string) {
  if (href === "/today") return pathname === "/today" || pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SideNav({
  user,
  pathname,
}: {
  user: CurrentUser;
  pathname: string;
}) {
  const [menuOpen, setMenuOpen] = useState(true);
  const onAdvancedRoute = !PRIMARY.some((p) => current(pathname, p.href));
  const [showAdvanced, setShowAdvanced] = useState(onAdvancedRoute);
  const isFounder = user.roles.includes("FOUNDER");
  const role = user.roles.includes("FOUNDER")
    ? "FOUNDER"
    : user.roles.includes("OPERATOR")
      ? "OPERATOR"
      : "VIEWER";

  return (
    <aside className="side-nav" aria-label="Primary">
      <div className="brand">
        <div className="brand-mark">Argus</div>
        <div className="brand-sub">Founder dashboard</div>
      </div>

      <button
        type="button"
        className="mobile-nav-toggle"
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen((v) => !v)}
      >
        {menuOpen ? "Close" : "Menu"}
      </button>

      <div className={`nav-collapse ${menuOpen ? "is-open" : ""}`}>
        <ul className="nav-list">
          {PRIMARY.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className="nav-link"
                aria-current={current(pathname, item.href) ? "page" : undefined}
                onClick={() => setMenuOpen(false)}
              >
                {item.label}
              </Link>
            </li>
          ))}
          <li>
            <button
              type="button"
              className="nav-link nav-link-button"
              aria-expanded={showAdvanced}
              onClick={() => setShowAdvanced((v) => !v)}
            >
              Advanced
            </button>
          </li>
        </ul>

        {showAdvanced ? (
          <>
            <ul className="nav-list nav-list-advanced">
              {ADVANCED.filter(
                (i) => !("founderOnly" in i && i.founderOnly) || isFounder,
              ).map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="nav-link"
                    aria-current={current(pathname, item.href) ? "page" : undefined}
                    onClick={() => setMenuOpen(false)}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
            <Link
              href="/today"
              className="btn secondary nav-back"
              onClick={() => setMenuOpen(false)}
            >
              Back to Today
            </Link>
          </>
        ) : null}

        <div className="nav-meta">
          <div>
            <strong>{user.username}</strong>
          </div>
          <div>{roleLabel(role)}</div>
          <form action={logoutAction} style={{ marginTop: "0.75rem" }}>
            <button type="submit" className="btn secondary">
              Sign out
            </button>
          </form>
        </div>
      </div>
    </aside>
  );
}
