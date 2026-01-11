"use client";

import { CheckCircle2, Mail } from "lucide-react";
import { motion, useInView } from "motion/react";
import Link from "next/link";
import posthog from "posthog-js";
import { FaGithub } from "react-icons/fa";
import { FaTwitter } from "react-icons/fa6";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Logo } from "@/data/logo";

/**
 * Pricing Component - Warm Theme
 */
export function Pricing() {
  const containerRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(containerRef, { once: true, amount: 0.2 });

  const tiers = [
    {
      name: "Explorer",
      price: "0",
      description: "Perfect for individuals testing the waters.",
      features: [
        "10 Documents per month",
        "Basic RAG search",
        "Standard Summarization",
        "Email Support",
      ],
      cta: "Start Free",
      popular: false,
    },
    {
      name: "Navigator",
      price: "49",
      description: "Advanced tools for legal professionals.",
      features: [
        "Unlimited Documents",
        "Advanced Semantic Search",
        "Clause Comparison",
        "Priority Support",
        "Export to PDF/JSON",
      ],
      cta: "Go Navigator",
      popular: true,
    },
    {
      name: "Fleet",
      price: "Custom",
      description: "Seamless integration for law firms.",
      features: [
        "Custom AI Models",
        "API access",
        "Dedicated Account Manager",
        "On-premise deployment",
        "SLA Guarantee",
      ],
      cta: "Contact Sales",
      popular: false,
    },
  ];

  return (
    <section
      ref={containerRef}
      id="pricing"
      className="py-8 md:py-12 px-4 md:px-8 bg-muted/30 relative overflow-hidden"
    >
      {/* Background ambience */}
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/5 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-secondary/5 rounded-full blur-[120px] pointer-events-none" />

      <div className="max-w-6xl mx-auto relative z-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-10"
        >
          <span className="inline-flex items-center gap-2 text-xs font-medium tracking-wider uppercase text-primary bg-primary/10 border border-primary/20 px-4 py-2 rounded-full mb-6">
            Pricing
          </span>
          <h2 className="text-3xl md:text-5xl lg:text-6xl font-display font-bold text-foreground tracking-tight">
            Choose Your{" "}
            <span className="text-gradient-warm font-serif italic font-normal tracking-normal">
              Plan.
            </span>
          </h2>
          <p className="text-muted-foreground text-lg mt-4 max-w-xl mx-auto">
            From solo explorers to enterprise teams, find the right plan for
            your needs.
          </p>
        </motion.div>

        {/* Pricing Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">
          {tiers.map((tier, index) => (
            <motion.div
              key={tier.name}
              initial={{ opacity: 0, y: 40 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.6, delay: index * 0.15 }}
              className={`relative p-8 lg:p-10 rounded-2xl border transition-all duration-500 ${
                tier.popular
                  ? "bg-card border-primary/30 shadow-lg scale-100 md:scale-105 z-10"
                  : "bg-card/50 border-border hover:border-primary/20"
              } ${index === 1 ? "md:mt-0" : "md:mt-6"}`}
            >
              {tier.popular && (
                <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-primary text-primary-foreground px-5 py-1 rounded-full text-xs font-medium">
                  Most Popular
                </div>
              )}

              <h4 className="text-sm font-medium uppercase tracking-wider mb-3 text-primary">
                {tier.name}
              </h4>
              <div className="flex items-baseline gap-2 mb-4">
                <span className="text-4xl font-display font-bold text-foreground">
                  {tier.price !== "Custom" && "$"}
                  {tier.price}
                </span>
                {tier.price !== "Custom" && (
                  <span className="text-sm text-muted-foreground">/month</span>
                )}
              </div>

              <p className="text-sm leading-relaxed mb-6 text-muted-foreground pb-6 border-b border-border">
                {tier.description}
              </p>

              <ul className="space-y-3 mb-8">
                {tier.features.map((feature) => (
                  <li
                    key={feature}
                    className="flex items-start gap-3 text-sm text-foreground/80"
                  >
                    <CheckCircle2 className="w-5 h-5 shrink-0 text-primary" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>

              <Button
                variant={tier.popular ? "default" : "outline"}
                className={`w-full h-12 rounded-full font-medium transition-all duration-500 ${
                  tier.popular
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "border-border hover:bg-primary/5 hover:border-primary/30"
                }`}
                onClick={() => {
                  posthog.capture("pricing_plan_clicked", {
                    plan_name: tier.name,
                    plan_price: tier.price,
                    is_popular: tier.popular,
                    cta_text: tier.cta,
                  });
                }}
              >
                {tier.cta}
              </Button>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

/**
 * Footer Component - Warm Theme
 */
export function Footer() {
  const [newsletterEmail, setNewsletterEmail] = useState("");

  const handleNewsletterSubmit = () => {
    if (newsletterEmail && newsletterEmail.includes("@")) {
      posthog.capture("newsletter_subscribed", {
        email_domain: newsletterEmail.split("@")[1],
        source: "footer",
      });
      setNewsletterEmail("");
    }
  };

  return (
    <footer className="bg-background text-foreground pt-20 pb-10 px-4 md:px-8 border-t border-border overflow-hidden relative">
      {/* Subtle wave pattern */}
      <div className="absolute inset-0 wave-pattern opacity-30 pointer-events-none" />

      <div className="max-w-6xl mx-auto relative z-10">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-10 lg:gap-12 mb-16">
          {/* Brand Column */}
          <div className="col-span-1">
            <Link href="/" className="flex items-center gap-3 mb-6 group">
              <div className="w-10 h-10 bg-primary/10 border border-primary/20 rounded-xl flex items-center justify-center group-hover:bg-primary/20 group-hover:rotate-3 transition-all duration-500 overflow-hidden">
                <Logo className="w-6 h-6" />
              </div>
              <span className="font-display font-bold text-xl tracking-tight">
                Clausea
              </span>
            </Link>
            <p className="text-muted-foreground leading-relaxed mb-6 text-sm max-w-xs">
              Navigating the depths of legal complexity. Because clarity
              shouldn&apos;t be a luxury.
            </p>
            <div className="flex items-center gap-3">
              {[
                { icon: FaTwitter, href: "https://x.com/clausea_ai" },
                { icon: FaGithub, href: "https://github.com/lvndry/clausea" },
              ].map(({ icon: Icon, href }, i) => (
                <a
                  key={i}
                  href={href}
                  className="w-9 h-9 rounded-full border border-border flex items-center justify-center hover:bg-primary hover:text-primary-foreground hover:border-primary transition-all duration-300"
                >
                  <Icon className="w-4 h-4" />
                </a>
              ))}
            </div>
          </div>

          {/* Links Columns */}
          <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-3 gap-8 lg:gap-10">
            <div className="space-y-4">
              <h5 className="font-medium text-xs uppercase tracking-wider text-foreground">
                Product
              </h5>
              <ul className="space-y-3">
                {["Features", "Pricing", "API", "Integrations"].map((l) => (
                  <li key={l}>
                    <Link
                      href="#"
                      className="text-sm text-muted-foreground hover:text-primary transition-colors"
                    >
                      {l}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
            <div className="space-y-4">
              <h5 className="font-medium text-xs uppercase tracking-wider text-foreground">
                Resources
              </h5>
              <ul className="space-y-3">
                {["Security", "Support", "Blog"].map((l) => (
                  <li key={l}>
                    <Link
                      href="#"
                      className="text-sm text-muted-foreground hover:text-primary transition-colors"
                    >
                      {l}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
            <div className="space-y-4">
              <h5 className="font-medium text-xs uppercase tracking-wider text-foreground">
                Legal
              </h5>
              <ul className="space-y-3">
                <li>
                  <Link
                    href="/privacy"
                    className="text-sm text-muted-foreground hover:text-primary transition-colors"
                  >
                    Privacy Policy
                  </Link>
                </li>
                <li>
                  <Link
                    href="/terms"
                    className="text-sm text-muted-foreground hover:text-primary transition-colors"
                  >
                    Terms of Service
                  </Link>
                </li>
                <li>
                  <Link
                    href="#"
                    className="text-sm text-muted-foreground hover:text-primary transition-colors"
                  >
                    Cookie Policy
                  </Link>
                </li>
                <li>
                  <Link
                    href="#"
                    className="text-sm text-muted-foreground hover:text-primary transition-colors"
                  >
                    GDPR
                  </Link>
                </li>
              </ul>
            </div>
          </div>

          {/* Newsletter */}
          <div className="space-y-4">
            <h5 className="font-medium text-xs uppercase tracking-wider text-foreground">
              Stay Updated
            </h5>
            <p className="text-muted-foreground text-sm">
              Get legal AI insights delivered monthly.
            </p>
            <div className="flex gap-2 p-1 bg-muted/50 border border-border rounded-full focus-within:border-primary/50 transition-all duration-300">
              <input
                type="email"
                placeholder="your@email.com"
                value={newsletterEmail}
                onChange={(e) => setNewsletterEmail(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    handleNewsletterSubmit();
                  }
                }}
                className="bg-transparent px-4 py-2 text-sm flex-1 outline-none text-foreground placeholder:text-muted-foreground/50"
                aria-label="Email address"
              />
              <Button
                size="icon"
                className="rounded-full w-9 h-9 bg-primary text-primary-foreground hover:bg-primary/90 shrink-0"
                onClick={handleNewsletterSubmit}
              >
                <Mail className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="pt-8 border-t border-border flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-xs text-muted-foreground">
            © 2025 Clausea AI. All rights reserved.
          </p>
          <div className="flex items-center gap-6 text-xs text-muted-foreground">
            <Link href="#" className="hover:text-primary transition-colors">
              Status
            </Link>
            <Link href="#" className="hover:text-primary transition-colors">
              Security
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
