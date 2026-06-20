"use client";

import { Menu, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { startTransition, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { useAuth } from "@clerk/nextjs";

export function Header() {
  const [isOpen, setIsOpen] = useState(false);
  const pathname = usePathname();
  const { isSignedIn, isLoaded } = useAuth();
  const prevPathnameRef = useRef(pathname);

  // Default to signed-out nav until Clerk confirms a session (safe for marketing pages).
  const showSignedInCta = isLoaded && isSignedIn;
  const ctaHref = showSignedInCta
    ? "/products"
    : "/sign-in?redirect_url=%2Fproducts";
  const ctaLabel = showSignedInCta ? "Dashboard" : "Get Started";
  const showSignIn = !showSignedInCta;

  const ctaButtonClassName =
    "border border-foreground text-foreground transition-colors hover:bg-foreground hover:text-background cursor-pointer";

  // Close mobile menu on route change
  useEffect(() => {
    if (prevPathnameRef.current !== pathname && isOpen) {
      startTransition(() => {
        setIsOpen(false);
      });
    }
    prevPathnameRef.current = pathname;
  }, [pathname, isOpen]);

  const navLinks: { name: string; href: string }[] = [];

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
          {showSignIn && (
            <Link
              href="/sign-in"
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              Sign In
            </Link>
          )}

          <Link href={ctaHref}>
            <button
              type="button"
              className={cn("px-5 py-2.5 md:px-7 md:py-3", ctaButtonClassName)}
            >
              {ctaLabel}
            </button>
          </Link>
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

            {showSignIn && (
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
                  Sign In
                </Link>
              </motion.div>
            )}

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: (navLinks.length + 1) * 0.1 }}
              className="mt-8 w-full max-w-xs"
            >
              <Link href={ctaHref} onClick={() => setIsOpen(false)}>
                <button
                  type="button"
                  className={cn(
                    "w-full py-4 text-sm uppercase tracking-widest font-medium",
                    ctaButtonClassName,
                  )}
                >
                  {ctaLabel}
                </button>
              </Link>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
