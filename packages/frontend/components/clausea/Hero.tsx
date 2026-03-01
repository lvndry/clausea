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
      className="col-span-12 px-6 md:px-10 py-16 md:py-20 border-b border-border flex flex-col gap-5 w-full bg-background"
    >
      <motion.span
        initial={{ opacity: 0, y: 10 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="text-[10px] md:text-xs uppercase tracking-[0.3em] text-muted-foreground"
      >
        Volume 01 / Document Intelligence
      </motion.span>
      <motion.h1
        initial={{ opacity: 0, y: 20 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.8, delay: 0.1, ease: "easeOut" }}
        className="font-display text-5xl sm:text-6xl md:text-[140px] leading-[0.85] font-medium tracking-tight md:-ml-1.5 text-foreground"
      >
        Automated
        <br />
        Legal Analysis.
      </motion.h1>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
        className="flex flex-col md:flex-row justify-between md:items-end mt-10 gap-8 md:gap-0"
      >
        <div className="max-w-[480px] w-full">
          <p className="text-base md:text-lg leading-relaxed text-muted-foreground mb-6 md:mb-8">
            Transforming complex privacy policies and legal agreements into
            high-fidelity risk signals and plain-language summaries for modern
            teams.
          </p>
          <div className="flex gap-4">
            <Link href="/products">
              <Button
                size="lg"
                className="rounded-none px-6 md:px-8 py-6 text-xs uppercase tracking-widest font-medium bg-foreground text-background hover:bg-muted-foreground transition-colors cursor-pointer"
                onClick={() => {
                  posthog.capture("cta_hero_clicked", {
                    cta_text: "Start Exploring",
                    cta_destination: "/products",
                    cta_type: "primary",
                  });
                }}
              >
                Start Exploring
              </Button>
            </Link>
          </div>
        </div>
        <div className="flex items-center gap-4 text-[10px] md:text-[11px] uppercase tracking-[0.15em] font-medium">
          <span className="text-foreground">Active Monitoring</span>
          <span className="text-muted-foreground">●</span>
          <span className="text-muted-foreground">24 Services Analyzed</span>
        </div>
      </motion.div>
    </section>
  );
}
