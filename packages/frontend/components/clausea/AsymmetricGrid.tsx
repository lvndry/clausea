"use client";

import {
  ArrowRight,
  Cpu,
  FileText,
  Globe,
  History,
  Layers,
  Search,
} from "lucide-react";
import { motion, useInView } from "motion/react";

import { useRef } from "react";

import { cn } from "@/lib/utils";

const features = [
  {
    title: "High-Precision Search",
    description:
      "Purpose-built AI agents search across thousands of policies with legal-grade precision. Ask complex questions and get referenced answers.",
    icon: Search,
    size: "lg",
  },
  {
    title: "Multi-Document Context",
    description:
      "Compare terms of service across multiple products side-by-side automatically.",
    icon: Layers,
    size: "sm",
  },
  {
    title: "Instant Summarization",
    description:
      "Condense 100-page privacy policies into 5 actionable bullet points.",
    icon: FileText,
    size: "sm",
  },
  {
    title: "Version Intelligence",
    description:
      "Track how policies change over time and see exactly what's new for you.",
    icon: History,
    size: "sm",
  },
  {
    title: "AI Compliance Officer",
    description:
      "Automated risk assessment based on industry standards and local regulations.",
    icon: Cpu,
    size: "lg",
  },
  {
    title: "Global Regulation Map",
    description:
      "Cross-reference documents against GDPR, CCPA, and hundreds of global laws.",
    icon: Globe,
    size: "sm",
  },
];

export default function AsymmetricGrid() {
  const containerRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(containerRef, { once: true, amount: 0.2 });

  return (
    <section
      ref={containerRef}
      className="col-span-12 grid grid-cols-1 md:grid-cols-12 border-b border-border bg-background"
    >
      {/* Section Header */}
      <div className="col-span-12 md:col-span-4 px-6 md:px-10 py-16 md:py-20 border-b md:border-b-0 md:border-r border-border flex flex-col justify-between">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
        >
          <span className="text-[10px] md:text-xs uppercase tracking-[0.3em] text-muted-foreground block mb-8">
            Capabilities
          </span>
          <h2 className="text-4xl md:text-6xl font-display font-medium text-foreground tracking-tight leading-[0.9]">
            Surface the
            <br />
            Hidden Depths.
          </h2>
        </motion.div>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="text-muted-foreground text-sm leading-relaxed max-w-[280px] mt-12 md:mt-0"
        >
          Powerful AI tools designed to navigate complex legal waters with
          precision and speed.
        </motion.p>
      </div>

      {/* Feature Grid */}
      <div className="col-span-12 md:col-span-8 grid grid-cols-1 md:grid-cols-2">
        {features.map((feature, index) => (
          <motion.article
            key={index}
            initial={{ opacity: 0, y: 20 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.6, delay: index * 0.1 }}
            className={cn(
              "px-6 md:px-10 py-12 border-b border-border flex flex-col justify-between min-h-[320px] group transition-colors hover:bg-muted/10 cursor-pointer",
              index % 2 === 0 ? "md:border-r" : "",
              index >= features.length - 2 ? "border-b-0" : "", // Remove bottom border for last row
            )}
          >
            <div className="flex justify-between items-start">
              <feature.icon
                className="w-8 h-8 text-foreground"
                strokeWidth={1.5}
              />
              <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px] uppercase tracking-widest font-medium text-primary">
                Explore
              </span>
            </div>

            <div className="mt-16">
              <h3 className="font-display text-3xl md:text-4xl text-foreground font-medium mb-4 tracking-tight leading-none">
                {feature.title}
              </h3>
              <p className="text-muted-foreground text-sm leading-relaxed max-w-[280px]">
                {feature.description}
              </p>
            </div>
          </motion.article>
        ))}
      </div>
    </section>
  );
}
