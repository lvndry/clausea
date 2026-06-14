"use client";

import {
  Building2,
  ChevronLeft,
  ChevronRight,
  Menu,
  Settings,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { Sheet, SheetContent, SheetTrigger } from "../ui/sheet";

const routes = [
  {
    label: "Products",
    icon: Building2,
    href: "/products",
    match: (pathname: string) => pathname.startsWith("/products"),
  },
  {
    label: "Settings",
    icon: Settings,
    href: "/settings",
    match: (pathname: string) => pathname.startsWith("/settings"),
  },
];

function SidebarNav({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle?: () => void;
}) {
  const pathname = usePathname() ?? "";

  return (
    <div className="h-full flex flex-col">
      <div
        className={cn(
          "relative border-b border-border flex items-center justify-center h-16 shrink-0",
          collapsed ? "px-2" : "px-3",
        )}
      >
        {!collapsed && (
          <Link href="/" className="flex items-center group">
            <span className="font-display font-medium text-xl tracking-widest uppercase text-foreground group-hover:text-primary transition-colors">
              CLAUSEA
            </span>
          </Link>
        )}
        {onToggle && (
          <button
            type="button"
            onClick={onToggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "flex items-center justify-center h-8 w-8 text-muted-foreground transition-colors hover:text-foreground",
              !collapsed && "absolute right-2",
            )}
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" strokeWidth={1.5} />
            ) : (
              <ChevronLeft className="h-4 w-4" strokeWidth={1.5} />
            )}
          </button>
        )}
      </div>

      <nav className="flex-1 py-6 px-2">
        <div className="space-y-2">
          {routes.map((route) => {
            const active = route.match(pathname);
            return (
              <Link
                key={route.href}
                href={route.href}
                title={collapsed ? route.label : undefined}
              >
                <div
                  className={cn(
                    "group relative flex items-center justify-center rounded-none py-3 transition-colors",
                    collapsed ? "px-0" : "gap-3 px-3",
                    active
                      ? "bg-muted/10 text-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/5",
                  )}
                >
                  <route.icon className="h-5 w-5 shrink-0" strokeWidth={1.5} />
                  {!collapsed && (
                    <span className="text-xs uppercase tracking-widest font-medium">
                      {route.label}
                    </span>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

export function Sidebar({
  defaultCollapsed = false,
}: {
  defaultCollapsed?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  const toggle = () =>
    setCollapsed((prev) => {
      const next = !prev;
      document.cookie = `sidebar-collapsed=${next}; path=/; max-age=31536000; samesite=lax`;
      return next;
    });

  return (
    <aside
      className={cn(
        "hidden h-full shrink-0 border-r border-border bg-background transition-[width] duration-200 ease-out md:block",
        collapsed ? "w-16" : "w-48",
      )}
    >
      <SidebarNav collapsed={collapsed} onToggle={toggle} />
    </aside>
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
      <SheetContent side="left" className="p-0 w-60 border-r-0 bg-card">
        <SidebarNav collapsed={false} />
      </SheetContent>
    </Sheet>
  );
}
