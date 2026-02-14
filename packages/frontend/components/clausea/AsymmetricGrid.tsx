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

const features = [
  {
    title: "RAG-Powered Queries",
    description:
      "Search across thousands of policies with semantic precision. Ask complex legal questions and get referenced answers.",
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
      className="py-8 md:py-12 px-4 md:px-8 bg-background overflow-hidden relative"
    >
      {/* Background ambience - warm tones */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none">
        <div className="absolute top-1/4 left-0 w-[400px] h-[400px] bg-primary/5 rounded-full blur-[120px]" />
        <div className="absolute bottom-1/4 right-0 w-[500px] h-[500px] bg-secondary/4 rounded-full blur-[140px]" />
      </div>

      <div className="max-w-6xl mx-auto relative z-10">
        {/* Section Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-16 md:mb-20 space-y-4"
        >
          <span className="inline-flex items-center gap-2 text-xs font-medium tracking-wider uppercase text-primary bg-primary/10 border border-primary/20 px-4 py-2 rounded-full">
            <Layers className="w-4 h-4" />
            Capabilities
          </span>
          <h2 className="text-3xl md:text-5xl lg:text-6xl font-display font-bold text-foreground tracking-tight">
            Surface the{" "}
            <span className="text-gradient-warm font-serif italic font-normal tracking-normal">
              Hidden Depths.
            </span>
          </h2>
          <p className="text-muted-foreground text-lg md:text-xl max-w-2xl mx-auto">
            Powerful AI tools designed to navigate complex legal waters with
            precision and speed.
          </p>
        </motion.div>

        {/* Feature Grid */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 md:gap-6 md:auto-rows-[260px] lg:auto-rows-[280px]">
          {features.map((feature, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 40 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.6, delay: index * 0.1 }}
              className={`group relative p-6 md:p-8 rounded-2xl bg-card border border-border hover:border-primary/30 transition-all duration-500 cursor-pointer overflow-hidden min-h-[220px] ${
                feature.size === "lg" ? "lg:col-span-2" : ""
              }`}
            >
              {/* Card content */}
              <div className="relative z-10 h-full flex flex-col">
                {/* Icon */}
                <div className="w-12 h-12 rounded-xl flex items-center justify-center mb-5 border border-border bg-muted/50 text-primary group-hover:scale-110 group-hover:bg-primary group-hover:text-primary-foreground group-hover:border-primary transition-all duration-500">
                  <feature.icon className="w-6 h-6" />
                </div>

                {/* Title */}
                <h3 className="text-xl md:text-2xl font-display font-bold text-foreground mb-3 group-hover:translate-x-1 transition-transform duration-500">
                  {feature.title}
                </h3>

                {/* Description */}
                <p className="text-muted-foreground text-sm md:text-base leading-relaxed max-w-sm group-hover:text-foreground/70 transition-colors duration-500">
                  {feature.description}
                </p>

                {/* Hover CTA */}
                <div className="mt-auto pt-4 opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all duration-500 flex items-center gap-2 text-sm font-medium text-primary">
                  Explore Feature <ArrowRight className="w-4 h-4" />
                </div>
              </div>

              {/* Decorative background icon */}
              <div className="absolute top-0 right-0 p-6 opacity-0 group-hover:opacity-[0.04] transition-opacity duration-700">
                <feature.icon className="w-40 h-40 -rotate-12 translate-x-12 -translate-y-12" />
              </div>

              {/* Hover glow effect */}
              <div className="absolute -inset-1 bg-linear-to-r from-primary/0 via-primary/5 to-primary/0 opacity-0 group-hover:opacity-100 transition-opacity duration-700 -z-10 blur-xl" />
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
