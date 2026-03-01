"use client";

import { Building2, Menu, Settings, Sparkles } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
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
    {
      label: "Settings",
      icon: Settings,
      href: "/settings",
      active: pathname?.startsWith("/settings"),
      description: "Account & billing",
    },
  ];

  return (
    <div className={cn("h-full flex flex-col", className)}>
      {/* Logo Section */}
      <div className="p-6 border-b border-border flex items-center h-16 shrink-0">
        <Link href="/" className="flex items-center group">
          <span className="font-display font-medium text-2xl tracking-widest uppercase text-foreground group-hover:text-primary transition-colors">
            CLAUSEA
          </span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-6 px-4">
        <div className="space-y-2">
          {routes.map((route) => (
            <Link key={route.href} href={route.href}>
              <div
                className={cn(
                  "group relative flex items-center gap-4 px-4 py-3 rounded-none transition-colors border-l-2",
                  route.active
                    ? "bg-muted/5 text-foreground border-foreground"
                    : "text-muted-foreground border-transparent hover:text-foreground hover:bg-muted/5",
                )}
              >
                <route.icon className="h-5 w-5 shrink-0" strokeWidth={1.5} />
                <span className="text-xs uppercase tracking-widest font-medium">
                  {route.label}
                </span>
              </div>
            </Link>
          ))}
        </div>
      </nav>

      {/* Bottom Section */}
      <div className="p-6 border-t border-border">
        <div className="border border-foreground bg-background p-4 flex flex-col gap-3">
          <Sparkles className="w-5 h-5 text-foreground" strokeWidth={1.5} />
          <div>
            <p className="font-medium text-[10px] uppercase tracking-widest text-foreground">
              AI-Powered Analysis
            </p>
            <p className="text-[10px] text-muted-foreground mt-1 leading-relaxed">
              Legal docs simplified
            </p>
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
