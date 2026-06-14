import { MobileSidebar, Sidebar } from "@/components/dashboard/sidebar";
import { ThemeToggle } from "@/components/dashboard/theme-toggle";
import { UserButton } from "@clerk/nextjs";
import { cookies } from "next/headers";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const sidebarCollapsed =
    (await cookies()).get("sidebar-collapsed")?.value === "true";

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:border focus:border-border focus:bg-background focus:px-4 focus:py-2 focus:text-xs focus:uppercase focus:tracking-widest focus:text-foreground"
      >
        Skip to content
      </a>
      <Sidebar defaultCollapsed={sidebarCollapsed} />

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header - Simple, solid */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background px-6 z-10">
          <MobileSidebar />
          <div className="flex w-full items-center justify-end gap-4">
            <div className="hidden md:block">
              <ThemeToggle />
            </div>
            <div className="h-8 w-px bg-border hidden md:block" />
            <UserButton
              appearance={{
                elements: {
                  avatarBox:
                    "h-9 w-9 ring-2 ring-primary/10 hover:ring-primary/20 transition-all",
                },
              }}
            />
          </div>
        </header>

        {/* Content */}
        <main id="main-content" tabIndex={-1} className="flex-1 overflow-y-auto">
          <div className="min-h-full p-4 sm:p-6 md:p-8 lg:p-10">{children}</div>
        </main>
      </div>
    </div>
  );
}
