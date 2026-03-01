"use client";

import { CheckCircle2, Loader2, Mail } from "lucide-react";
import { motion, useInView } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import posthog from "posthog-js";
import { FaGithub } from "react-icons/fa";
import { FaTwitter } from "react-icons/fa6";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useCheckout } from "@/hooks/useCheckout";
import { cn } from "@/lib/utils";

const PRO_PRICE_ID =
  process.env.NEXT_PUBLIC_PADDLE_PRICE_PRO_MONTHLY ||
  process.env.NEXT_PUBLIC_PADDLE_PRICE_INDIVIDUAL_MONTHLY ||
  "";

/**
 * Pricing Component - Warm Theme
 */
export function Pricing() {
  const containerRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(containerRef, { once: true, amount: 0.2 });
  const router = useRouter();
  const { startCheckout, isLoading, error } = useCheckout();

  const tiers = [
    {
      name: "Free",
      price: "0",
      description:
        "Perfect for trying out Clausea with basic privacy analysis.",
      features: [
        "3 analyses per month",
        "AI-powered summaries",
        "Risk scoring",
        "Chat with documents",
      ],
      cta: "Get Started",
      popular: false,
      action: () => router.push("/sign-up"),
    },
    {
      name: "Pro",
      price: "9",
      description:
        "Unlimited analysis for privacy-conscious individuals and teams.",
      features: [
        "Unlimited analyses",
        "Advanced semantic search",
        "Deep analysis (Level 3)",
        "Priority support",
        "Export reports",
      ],
      cta: "Upgrade to Pro",
      popular: true,
      action: () => {
        if (PRO_PRICE_ID) {
          startCheckout(PRO_PRICE_ID);
        } else {
          router.push("/sign-up");
        }
      },
    },
  ];

  return (
    <section
      ref={containerRef}
      id="pricing"
      className="col-span-12 grid grid-cols-1 md:grid-cols-12 border-b border-border bg-background"
    >
      <div className="col-span-12 md:col-span-4 px-6 md:px-10 py-16 md:py-20 border-b md:border-b-0 md:border-r border-border flex flex-col justify-between">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
        >
          <span className="text-[10px] md:text-xs uppercase tracking-[0.3em] text-muted-foreground block mb-8">
            Pricing
          </span>
          <h2 className="text-4xl md:text-6xl font-display font-medium text-foreground tracking-tight leading-[0.9]">
            Simple
            <br />
            Pricing.
          </h2>
        </motion.div>

        <div className="mt-12 md:mt-0">
          <p className="text-muted-foreground text-sm leading-relaxed max-w-[280px]">
            Start free, upgrade when you need more. No hidden fees.
          </p>
          {/* Error message */}
          {error && (
            <div className="mt-6 p-4 border border-foreground bg-foreground/5 text-xs font-medium text-foreground">
              {error}
            </div>
          )}
        </div>
      </div>

      {/* Pricing Grid */}
      <div className="col-span-12 md:col-span-8 grid grid-cols-1 md:grid-cols-2">
        {tiers.map((tier, index) => (
          <motion.div
            key={tier.name}
            initial={{ opacity: 0, y: 40 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.6, delay: index * 0.15 }}
            className={cn(
              "px-6 md:px-10 py-12 border-b border-border flex flex-col min-h-[480px] bg-background",
              index === 0 ? "md:border-r border-b" : "border-b-0",
              tier.popular ? "bg-muted/5" : "",
            )}
          >
            <div className="flex justify-between items-start mb-12">
              <h4 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
                {tier.name}
              </h4>
              {tier.popular && (
                <span className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
                  Most Popular
                </span>
              )}
            </div>

            <div className="flex items-baseline gap-2 mb-6">
              <span className="text-6xl font-display font-medium text-foreground tracking-tight leading-none">
                ${tier.price}
              </span>
              <span className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
                /mo
              </span>
            </div>

            <p className="text-sm leading-relaxed text-muted-foreground mb-12 grow">
              {tier.description}
            </p>

            <ul className="space-y-4 mb-12">
              {tier.features.map((feature) => (
                <li
                  key={feature}
                  className="flex items-start gap-4 text-sm text-muted-foreground"
                >
                  <CheckCircle2
                    className="w-4 h-4 shrink-0 text-foreground mt-0.5"
                    strokeWidth={1.5}
                  />
                  <span>{feature}</span>
                </li>
              ))}
            </ul>

            <Button
              variant={tier.popular ? "default" : "outline"}
              disabled={isLoading && tier.popular}
              className={cn(
                "w-full h-14 rounded-none text-xs uppercase tracking-widest font-medium transition-colors border",
                tier.popular
                  ? "bg-foreground text-background border-foreground hover:bg-muted-foreground"
                  : "bg-transparent border-foreground text-foreground hover:bg-foreground hover:text-background",
              )}
              onClick={() => {
                posthog.capture("pricing_plan_clicked", {
                  plan_name: tier.name,
                  plan_price: tier.price,
                  is_popular: tier.popular,
                  cta_text: tier.cta,
                });
                tier.action();
              }}
            >
              {isLoading && tier.popular ? (
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
              ) : null}
              {tier.cta}
            </Button>
          </motion.div>
        ))}
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
    <footer className="col-span-12 grid grid-cols-1 md:grid-cols-12 bg-background border-b border-border">
      {/* Brand Column */}
      <div className="col-span-12 md:col-span-4 px-6 md:px-10 py-16 md:py-20 border-b md:border-b-0 md:border-r border-border flex flex-col justify-between">
        <div>
          <Link href="/" className="inline-block mb-12">
            <span className="font-display text-2xl md:text-3xl font-medium tracking-widest uppercase text-foreground">
              CLAUSEA
            </span>
          </Link>
          <p className="text-muted-foreground text-sm leading-relaxed max-w-[280px]">
            Navigating the depths of legal complexity. Because clarity
            shouldn&apos;t be a luxury.
          </p>
        </div>

        <div className="flex items-center gap-6 mt-16 md:mt-0">
          {[
            { icon: FaTwitter, href: "https://x.com/clausea_ai" },
            { icon: FaGithub, href: "https://github.com/lvndry/clausea" },
          ].map(({ icon: Icon, href }, i) => (
            <a
              key={i}
              href={href}
              className="text-foreground hover:text-muted-foreground transition-colors"
            >
              <Icon className="w-5 h-5" />
            </a>
          ))}
        </div>
      </div>

      {/* Links Columns */}
      <div className="col-span-12 md:col-span-8 grid grid-cols-1 md:grid-cols-3">
        <div className="px-6 md:px-10 py-12 md:py-20 border-b md:border-b-0 md:border-r border-border">
          <h5 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground mb-8">
            Product
          </h5>
          <ul className="space-y-4">
            {["Features", "Pricing", "API", "Integrations"].map((l) => (
              <li key={l}>
                <Link
                  href="#"
                  className="text-xs uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  {l}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div className="px-6 md:px-10 py-12 md:py-20 border-b md:border-b-0 md:border-r border-border">
          <h5 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground mb-8">
            Resources
          </h5>
          <ul className="space-y-4">
            {["Security", "Support", "Blog"].map((l) => (
              <li key={l}>
                <Link
                  href="#"
                  className="text-xs uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  {l}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div className="px-6 md:px-10 py-12 md:py-20 border-b border-border md:border-b-0">
          <h5 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground mb-8">
            Legal
          </h5>
          <ul className="space-y-4">
            <li>
              <Link
                href="/privacy"
                className="text-xs uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Privacy Policy
              </Link>
            </li>
            <li>
              <Link
                href="/terms"
                className="text-xs uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Terms of Service
              </Link>
            </li>
            <li>
              <Link
                href="#"
                className="text-xs uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Cookie Policy
              </Link>
            </li>
            <li>
              <Link
                href="#"
                className="text-xs uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                GDPR
              </Link>
            </li>
          </ul>
        </div>
      </div>

      {/* Newsletter & Bottom Bar */}
      <div className="col-span-12 grid grid-cols-1 md:grid-cols-12">
        <div className="col-span-12 md:col-span-4 px-6 md:px-10 py-12 md:border-r border-border flex flex-col justify-center">
          <p className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground mb-4">
            © 2024 Clausea AI
          </p>
          <div className="flex items-center gap-6">
            <Link
              href="#"
              className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Status
            </Link>
            <Link
              href="#"
              className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Security
            </Link>
          </div>
        </div>

        <div className="col-span-12 md:col-span-8 px-6 md:px-10 py-12 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div>
            <h5 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground mb-2">
              Stay Updated
            </h5>
            <p className="text-muted-foreground text-sm">
              Get legal AI insights delivered monthly.
            </p>
          </div>

          <div className="flex w-full md:w-auto md:min-w-[400px]">
            <input
              type="email"
              placeholder="your@email.com"
              value={newsletterEmail}
              onChange={(e) => setNewsletterEmail(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleNewsletterSubmit();
              }}
              className="bg-transparent border border-r-0 border-foreground px-4 py-3 text-sm flex-1 outline-none text-foreground placeholder:text-muted-foreground rounded-none"
              aria-label="Email address"
            />
            <Button
              className="rounded-none border border-foreground bg-foreground text-background hover:bg-muted-foreground transition-colors px-6 h-auto"
              onClick={handleNewsletterSubmit}
            >
              <Mail className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>
    </footer>
  );
}
