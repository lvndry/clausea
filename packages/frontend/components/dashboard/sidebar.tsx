"use client";

import { Building2, Menu, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Logo } from "@/data/logo";
import { cn } from "@/lib/utils";

import { Sheet, SheetContent, SheetTrigger } from "../ui/sheet";

interface SidebarProps extends React.HTMLAttributes<HTMLDivElement> {}

export function Sidebar({ className }: SidebarProps) {
  const pathname = usePathname();

  const routes = [
    {
      label: "Products",
      icon: Building2,
      href: "/products",
      active: pathname?.startsWith("/products") || pathname?.startsWith("/c/"),
      description: "Privacy analysis",
    },
  ];

  return (
    <div className={cn("h-full flex flex-col", className)}>
      {/* Logo Section */}
      <div className="p-6 border-b border-border">
        <Link href="/" className="flex items-center gap-3 group">
          <Logo className="w-10 h-10" />
          <div className="flex flex-col">
            <span className="font-display font-bold text-lg tracking-tight text-foreground">
              Clausea
            </span>
            <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest">
              Intelligence
            </span>
          </div>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3">
        <div className="space-y-1">
          {routes.map((route) => (
            <Link key={route.href} href={route.href}>
              <div
                className={cn(
                  "group relative flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors",
                  route.active
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
                )}
              >
                {/* Active indicator */}
                {route.active && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-primary rounded-r-full" />
                )}

                <div
                  className={cn(
                    "flex items-center justify-center w-8 h-8 rounded-md transition-colors",
                    route.active
                      ? "bg-primary/15"
                      : "bg-transparent group-hover:bg-muted",
                  )}
                >
                  <route.icon className="h-[18px] w-[18px]" />
                </div>

                <div className="flex flex-col">
                  <span className="font-medium text-sm">{route.label}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {route.description}
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </nav>

      {/* Bottom Section */}
      <div className="p-4 border-t border-border">
        <div className="rounded-lg bg-muted/50 border border-border p-3">
          <div className="flex items-start gap-2.5">
            <div className="w-7 h-7 rounded-md bg-secondary/10 flex items-center justify-center shrink-0">
              <Sparkles className="w-3.5 h-3.5 text-secondary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-xs text-foreground">
                AI-Powered Analysis
              </p>
              <p className="text-[10px] text-muted-foreground mt-0.5 leading-relaxed">
                Legal docs simplified
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function MobileSidebar() {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden h-9 w-9 rounded-lg hover:bg-muted"
        >
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="p-0 w-72 border-r-0 bg-card">
        <Sidebar />
      </SheetContent>
    </Sheet>
  );
}
