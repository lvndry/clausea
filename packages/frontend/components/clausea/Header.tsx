"use client";

import { Menu, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { startTransition, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuth } from "@clerk/nextjs";

export function Header() {
  const [isOpen, setIsOpen] = useState(false);
  const pathname = usePathname();
  const { isSignedIn, isLoaded } = useAuth();
  const prevPathnameRef = useRef(pathname);

  // Close mobile menu on route change
  useEffect(() => {
    if (prevPathnameRef.current !== pathname && isOpen) {
      startTransition(() => {
        setIsOpen(false);
      });
    }
    prevPathnameRef.current = pathname;
  }, [pathname, isOpen]);

  const navLinks = [
    { name: "Archive", href: "/archive" },
    { name: "Methodology", href: "/methodology" },
  ];

  return (
    <>
      <nav className="col-span-12 flex justify-between items-center px-6 md:px-10 py-8 border-b border-border w-full">
        {/* Logo */}
        <Link
          href="/"
          className="font-display text-2xl md:text-3xl font-medium tracking-widest uppercase text-foreground transition-colors hover:text-primary"
        >
          CLAUSEA
        </Link>

        {/* Desktop Nav */}
        <div className="hidden md:flex items-center gap-6 md:gap-10 text-[10px] md:text-[11px] uppercase tracking-widest font-medium">
          {navLinks.map((link) => (
            <Link
              key={link.name}
              href={link.href}
              className={cn(
                "transition-colors",
                pathname === link.href
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {link.name}
            </Link>
          ))}
          {isLoaded && !isSignedIn && (
            <Link
              href="/sign-in"
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              Login
            </Link>
          )}

          {isLoaded && (
            <Link href={isSignedIn ? "/products" : "/sign-up"}>
              <button className="px-5 py-2.5 md:px-7 md:py-3 border border-foreground text-foreground hover:bg-foreground hover:text-background transition-colors cursor-pointer">
                {isSignedIn ? "Dashboard" : "New Analysis"}
              </button>
            </Link>
          )}
        </div>

        {/* Mobile Menu Toggle */}
        <button
          className="md:hidden flex items-center justify-center text-foreground hover:text-primary transition-colors"
          onClick={() => setIsOpen(!isOpen)}
          aria-label="Toggle menu"
        >
          {isOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </nav>

      {/* Mobile Menu */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="fixed inset-0 z-40 bg-background md:hidden flex flex-col items-center justify-center gap-8 p-8 overflow-y-auto"
          >
            <button
              className="absolute top-8 right-6 text-foreground hover:text-primary transition-colors"
              onClick={() => setIsOpen(false)}
              aria-label="Close menu"
            >
              <X className="w-6 h-6" />
            </button>

            {/* Mobile Logo */}
            <Link
              href="/"
              onClick={() => setIsOpen(false)}
              className="font-display text-3xl font-medium tracking-widest uppercase mb-8"
            >
              CLAUSEA
            </Link>

            {navLinks.map((link, index) => (
              <motion.div
                key={link.name}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
              >
                <Link
                  href={link.href}
                  onClick={() => setIsOpen(false)}
                  className={cn(
                    "text-sm uppercase tracking-widest font-medium transition-colors",
                    pathname === link.href
                      ? "text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {link.name}
                </Link>
              </motion.div>
            ))}

            {isLoaded && !isSignedIn && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: navLinks.length * 0.1 }}
              >
                <Link
                  href="/sign-in"
                  onClick={() => setIsOpen(false)}
                  className="text-sm uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  Login
                </Link>
              </motion.div>
            )}

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: (navLinks.length + 1) * 0.1 }}
              className="mt-8 w-full max-w-xs"
            >
              {isLoaded && (
                <Link
                  href={isSignedIn ? "/products" : "/sign-up"}
                  onClick={() => setIsOpen(false)}
                >
                  <button className="w-full py-4 border border-foreground text-sm uppercase tracking-widest font-medium text-foreground hover:bg-foreground hover:text-background transition-colors">
                    {isSignedIn ? "Dashboard" : "New Analysis"}
                  </button>
                </Link>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
