"use client";

import { Menu, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { startTransition, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Logo } from "@/data/logo";
import { cn } from "@/lib/utils";
import { useAuth } from "@clerk/nextjs";

export function Header() {
  const [isOpen, setIsOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const pathname = usePathname();
  const { isSignedIn, isLoaded } = useAuth();
  const headerRef = useRef<HTMLElement>(null);
  const prevPathnameRef = useRef(pathname);

  // Handle scroll state
  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 50);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

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
    { name: "Features", href: "/features" },
    { name: "Pricing", href: "/pricing" },
    { name: "Contact", href: "/contact" },
  ];

  return (
    <header
      ref={headerRef}
      className={cn(
        "fixed top-0 left-0 w-full z-40 transition-all duration-500",
        scrolled ? "py-4 px-4 md:px-6" : "py-6 px-4 md:px-8",
      )}
    >
      <nav
        className={cn(
          "mx-auto flex items-center justify-between px-6 md:px-8 transition-all duration-500",
          scrolled
            ? "bg-background/80 backdrop-blur-xl border border-border/50 shadow-lg py-3 rounded-full max-w-6xl"
            : "bg-transparent border-transparent py-2 max-w-7xl",
        )}
      >
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3 group">
          <div className="w-10 h-10 bg-primary/10 border border-primary/20 rounded-xl flex items-center justify-center group-hover:bg-primary/20 group-hover:border-primary/40 group-hover:rotate-3 transition-all duration-500 overflow-hidden">
            <Logo className="w-7 h-7" />
          </div>
          <span className="font-display font-bold text-xl tracking-tight text-foreground">
            Clausea
          </span>
        </Link>

        {/* Desktop Nav */}
        <ul className="hidden md:flex items-center gap-8">
          {navLinks.map((link) => (
            <li key={link.name}>
              <Link
                href={link.href}
                className={cn(
                  "relative text-sm font-medium transition-all duration-300 py-2",
                  pathname === link.href
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {link.name}
                {pathname === link.href && (
                  <motion.span
                    layoutId="nav-underline"
                    className="absolute -bottom-1 left-0 right-0 h-0.5 bg-primary rounded-full"
                  />
                )}
              </Link>
            </li>
          ))}
        </ul>

        {/* CTA Buttons */}
        <div className="flex items-center gap-3">
          {isLoaded && (
            <>
              {isSignedIn ? (
                <Link href="/products">
                  <Button className="hidden sm:flex rounded-full px-6 h-10 font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-all duration-300">
                    Dashboard
                  </Button>
                </Link>
              ) : (
                <Link href="/sign-in">
                  <Button className="hidden sm:flex rounded-full px-6 h-10 font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-all duration-300 cursor-pointer">
                    Get Started
                  </Button>
                </Link>
              )}
            </>
          )}

          {/* Mobile Menu Toggle */}
          <button
            className="md:hidden w-10 h-10 flex items-center justify-center rounded-full bg-muted/50 border border-border hover:border-primary/30 transition-colors"
            onClick={() => setIsOpen(!isOpen)}
            aria-label="Toggle menu"
          >
            {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </nav>

      {/* Mobile Menu */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="fixed inset-0 z-40 bg-background/98 backdrop-blur-xl md:hidden flex flex-col items-center justify-center gap-6 p-8"
          >
            <button
              className="absolute top-6 right-6 w-12 h-12 flex items-center justify-center rounded-full bg-muted/50 border border-border hover:border-primary/30 transition-colors"
              onClick={() => setIsOpen(false)}
              aria-label="Close menu"
            >
              <X className="w-5 h-5" />
            </button>

            {/* Mobile Logo */}
            <div className="mb-6 flex items-center gap-3">
              <div className="w-12 h-12 bg-primary/10 border border-primary/20 rounded-xl flex items-center justify-center overflow-hidden">
                <Logo className="w-8 h-8" />
              </div>
            </div>

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
                    "text-3xl font-display font-bold transition-colors",
                    pathname === link.href
                      ? "text-primary"
                      : "text-foreground hover:text-primary",
                  )}
                >
                  {link.name}
                </Link>
              </motion.div>
            ))}

            <div className="mt-8 flex flex-col gap-4 w-full max-w-xs">
              {isLoaded && (
                <>
                  {isSignedIn ? (
                    <Link href="/products" onClick={() => setIsOpen(false)}>
                      <Button
                        size="lg"
                        className="w-full rounded-full h-14 text-lg font-medium bg-primary text-primary-foreground"
                      >
                        Dashboard
                      </Button>
                    </Link>
                  ) : (
                    <Link href="/sign-in" onClick={() => setIsOpen(false)}>
                      <Button
                        size="lg"
                        className="w-full rounded-full h-14 text-lg font-medium bg-primary text-primary-foreground"
                      >
                        Get Started
                      </Button>
                    </Link>
                  )}
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
