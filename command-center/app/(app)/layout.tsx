import { Sidebar, MobileNav } from "@/components/Sidebar";
import { getUser } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { SignOutButton } from "@/components/SignOutButton";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // Middleware already gates access; this reads the user for the header.
  const user = isSupabaseConfigured ? await getUser() : null;

  return (
    <div className="grid-bg flex min-h-dvh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2.5">
          <div className="mono text-[11px] tracking-widest text-[var(--color-muted)]">
            CHRONOS · OPERATIONS
          </div>
          <div className="flex items-center gap-3">
            {user?.email && (
              <span className="mono text-[11px] text-[var(--color-muted)]">{user.email}</span>
            )}
            <SignOutButton />
          </div>
        </header>
        <MobileNav />
        <main className="min-w-0 flex-1 overflow-y-auto p-4">{children}</main>
      </div>
    </div>
  );
}
