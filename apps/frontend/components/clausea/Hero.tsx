"use client";

import { ArrowRight } from "lucide-react";
import { motion, useInView } from "motion/react";
import Link from "next/link";
import posthog from "posthog-js";

import { useRef } from "react";

import { Button } from "@/components/ui/button";

export default function Hero() {
  const containerRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(containerRef, { once: true, amount: 0.3 });

  return (
    <section
      ref={containerRef}
      className="relative min-h-[80vh] flex flex-col items-center justify-center overflow-hidden px-4 md:px-8 pt-20 md:pt-32 warm-gradient"
    >
      {/* Subtle ambient glows */}
      <div className="absolute top-20 left-1/4 w-[500px] h-[500px] bg-primary/8 rounded-full blur-[150px] pointer-events-none" />
      <div className="absolute bottom-20 right-1/4 w-[400px] h-[400px] bg-secondary/6 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-accent/5 rounded-full blur-[180px] pointer-events-none" />

      <div className="relative z-10 max-w-5xl mx-auto w-full text-center">
        <motion.h1
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8, delay: 0.1, ease: "easeOut" }}
          className="mb-6 font-display font-bold leading-[1.1] tracking-tight"
        >
          <span className="block text-4xl md:text-6xl lg:text-7xl text-foreground">
            Legal documents
          </span>
          <span className="block text-4xl md:text-6xl lg:text-7xl text-primary font-serif italic font-normal tracking-normal my-3">
            were not written for you...
          </span>
          <span className="block text-4xl md:text-6xl lg:text-7xl text-foreground">
            <span className="relative inline-block">
              <span className="text-secondary underline-warm">until now</span>
            </span>
            .
          </span>
        </motion.h1>

        {/* Description */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8, delay: 0.3, ease: "easeOut" }}
          className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed"
        >
          <span className="text-foreground/90">
            Transform complexity into clarity.
          </span>{" "}
          Clausea AI analyzes dense legal jargon and surfaces the risks, rights,
          and key terms hidden in privacy policies and terms of service.
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8, delay: 0.4, ease: "easeOut" }}
          className="flex flex-col sm:flex-row items-center justify-center gap-4"
        >
          <Link href="/products">
            <Button
              size="lg"
              className="group h-14 px-8 rounded-full text-base font-medium transition-all duration-300 hover:scale-[1.02] active:scale-[0.98] bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg relative overflow-hidden cursor-pointer"
              onClick={() => {
                posthog.capture("cta_hero_clicked", {
                  cta_text: "Start Exploring",
                  cta_destination: "/products",
                  cta_type: "primary",
                });
              }}
            >
              <span className="relative z-10 flex items-center">
                Start Exploring
                <ArrowRight className="ml-2 w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </span>
              <div className="absolute inset-0 shimmer" />
            </Button>
          </Link>
          <Link href="/features">
            <Button
              size="lg"
              variant="outline"
              className="h-14 px-8 rounded-full text-base font-medium border-border hover:border-primary/50 hover:bg-primary/5 transition-all duration-300"
              onClick={() => {
                posthog.capture("cta_hero_clicked", {
                  cta_text: "See How It Works",
                  cta_destination: "/features",
                  cta_type: "secondary",
                });
              }}
            >
              See How It Works
            </Button>
          </Link>
        </motion.div>

        {/* Stats */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8, delay: 0.5, ease: "easeOut" }}
          className="mt-12 md:mt-16 flex flex-col sm:flex-row items-stretch sm:items-center sm:justify-center gap-6 sm:gap-8 md:gap-12 border-t border-border/50 pt-10 w-full max-w-3xl mx-auto"
        >
          <div className="flex flex-col items-center text-center gap-2 w-full">
            <p className="text-3xl md:text-4xl font-display font-bold text-foreground">
              10<span className="text-primary">s</span>
            </p>
            <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
              Avg. Analysis
            </p>
          </div>
          <div className="hidden sm:block h-10 w-px bg-border" />
          <div className="sm:hidden w-16 h-px bg-border/70 mx-auto" />
          <div className="flex flex-col items-center text-center gap-2 w-full">
            <p className="text-3xl md:text-4xl font-display font-bold text-foreground">
              99.8<span className="text-primary">%</span>
            </p>
            <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
              Accuracy
            </p>
          </div>
          <div className="hidden sm:block h-10 w-px bg-border" />
          <div className="sm:hidden w-16 h-px bg-border/70 mx-auto" />
          <div className="flex flex-col items-center text-center gap-2 w-full">
            <p className="text-3xl md:text-4xl font-display font-bold text-secondary">
              5k<span className="text-primary">+</span>
            </p>
            <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
              Products
            </p>
          </div>
        </motion.div>
      </div>

      {/* Decorative elements - Abstract shapes */}
      <div className="absolute bottom-0 left-0 right-0 h-32 bg-linear-to-t from-background to-transparent pointer-events-none" />

      {/* Subtle grain overlay for premium feel */}
      <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIzMDAiIGhlaWdodD0iMzAwIj48ZmlsdGVyIGlkPSJhIiB4PSIwIiB5PSIwIj48ZmVUdXJidWxlbmNlIGJhc2VGcmVxdWVuY3k9Ii43NSIgc3RpdGNoVGlsZXM9InN0aXRjaCIgdHlwZT0iZnJhY3RhbE5vaXNlIi8+PGZlQ29sb3JNYXRyaXggdHlwZT0ic2F0dXJhdGUiIHZhbHVlcz0iMCIvPjwvZmlsdGVyPjxyZWN0IHdpZHRoPSIxMDAlIiBoZWlnaHQ9IjEwMCUiIGZpbHRlcj0idXJsKCNhKSIgb3BhY2l0eT0iLjAyIi8+PC9zdmc+')] opacity-50 pointer-events-none" />
    </section>
  );
}
