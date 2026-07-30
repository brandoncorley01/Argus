import { SideNav } from "@/components/SideNav";
import { requireUser } from "@/lib/actions/auth";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireUser();

  return (
    <div className="app-shell">
      <SideNav user={user} />
      <main id="main" className="main">
        {children}
      </main>
    </div>
  );
}
