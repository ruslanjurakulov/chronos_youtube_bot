import { Sidebar, MobileNav } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { getUser } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // Middleware already gates access; this reads the user for the header.
  const user = isSupabaseConfigured ? await getUser() : null;

  return (
    <div className="grid-bg flex min-h-dvh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header userEmail={user?.email} />
        <MobileNav />
        <main className="min-w-0 flex-1 overflow-y-auto p-4 sm:p-5">{children}</main>
      </div>
    </div>
  );
}
