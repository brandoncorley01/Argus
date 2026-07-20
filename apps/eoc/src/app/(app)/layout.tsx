import { headers } from "next/headers";

import { SideNav } from "@/components/SideNav";
import { requireUser } from "@/lib/actions/auth";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireUser();
  const h = await headers();
  const pathname = h.get("x-pathname") || h.get("x-url") || "/overview";

  return (
    <div className="app-shell">
      <SideNav user={user} pathname={pathname} />
      <main id="main" className="main">
        {children}
      </main>
    </div>
  );
}
