"use client";

import { CheckCircle2, Loader2, Mail } from "lucide-react";
import { motion, useInView } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import posthog from "posthog-js";

import { useRef, useState } from "react";

import { GithubIcon } from "@/components/ui/brand-icons";
import { Button } from "@/components/ui/button";
import { useCheckout } from "@/hooks/useCheckout";
import { useGetStartedNavigation } from "@/hooks/useGetStartedNavigation";
import { useProPricing } from "@/hooks/useProPricing";
import {
  type BillingInterval,
  PRO_PRICE_ANNUAL,
  PRO_PRICE_MONTHLY,
  getProDisplayPrice,
} from "@/lib/pricing";
import { cn } from "@/lib/utils";

type PricingFeature = string | { label: string; comingSoon: boolean };

/**
 * Pricing Component - Warm Theme
 */
export function Pricing() {
  const containerRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(containerRef, { once: true, amount: 0.2 });
  const { startCheckout, isLoading, error } = useCheckout();
  const { navigate: navigateToGetStarted, isNavigationReady } =
    useGetStartedNavigation();
  const {
    getProPriceId,
    isProCheckoutAvailable,
    getCheckoutUnavailableMessage,
  } = useProPricing();
  const [billingInterval, setBillingInterval] =
    useState<BillingInterval>("monthly");

  const proDisplayPrice = getProDisplayPrice(billingInterval);
  const proPriceId = getProPriceId(billingInterval);
  const checkoutAvailable = isProCheckoutAvailable(billingInterval);
  const checkoutUnavailableMessage = checkoutAvailable
    ? null
    : getCheckoutUnavailableMessage(billingInterval);
  const annualSavings = PRO_PRICE_MONTHLY * 12 - PRO_PRICE_ANNUAL;

  const tiers: Array<{
    name: string;
    price: string;
    priceSuffix?: string;
    priceNote?: string;
    description: string;
    features: PricingFeature[];
    cta: string;
    popular: boolean;
    action: () => void;
  }> = [
    {
      name: "Free",
      price: "0",
      priceSuffix: "/mo",
      description:
        "Perfect for trying out Clausea with basic privacy analysis.",
      features: [
        "3 analyses per month",
        "Core documents only (Privacy Policy, ToS, GDPR)",
        "AI-powered analysis",
        "Risk scoring",
        "Chat with documents",
      ],
      cta: "Get Started",
      popular: false,
      action: () => navigateToGetStarted(),
    },
    {
      name: "Pro",
      price: String(proDisplayPrice.amount),
      priceSuffix: proDisplayPrice.suffix,
      priceNote:
        billingInterval === "annual" && annualSavings > 0
          ? `Save $${annualSavings} vs monthly`
          : undefined,
      description:
        "Unlimited analysis for privacy-conscious individuals and teams.",
      features: [
        "Unlimited analyses",
        "All policy documents analyzed",
        "Semantic search",
        "Priority support",
        { label: "Export reports", comingSoon: true },
      ],
      cta: "Upgrade to Pro",
      popular: true,
      action: () => {
        if (checkoutAvailable && proPriceId) {
          startCheckout(proPriceId);
        }
      },
    },
  ];

  return (
    <section
      ref={containerRef}
      id="pricing"
      className="col-span-12 grid grid-cols-1 md:grid-cols-12 border-b border-border bg-background relative z-10 overflow-visible"
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
          <div className="inline-flex border border-border mb-6">
            <button
              type="button"
              onClick={() => setBillingInterval("monthly")}
              className={cn(
                "px-4 py-2 text-[10px] uppercase tracking-widest font-medium transition-colors",
                billingInterval === "monthly"
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              Monthly
            </button>
            <button
              type="button"
              onClick={() => setBillingInterval("annual")}
              className={cn(
                "px-4 py-2 text-[10px] uppercase tracking-widest font-medium transition-colors border-l border-border",
                billingInterval === "annual"
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              Annual
            </button>
          </div>
          <p className="text-muted-foreground text-sm leading-relaxed max-w-[280px]">
            Start free, upgrade when you need more. Pro is ${PRO_PRICE_MONTHLY}
            /month or ${PRO_PRICE_ANNUAL}/year.
          </p>
          {/* Checkout configuration / error messages */}
          {checkoutUnavailableMessage && (
            <div className="mt-6 p-4 border border-border bg-muted/30 text-xs leading-relaxed text-muted-foreground">
              {checkoutUnavailableMessage}
            </div>
          )}
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

            <div className="mb-6">
              <div className="flex items-baseline gap-2">
                <span className="text-6xl font-display font-medium text-foreground tracking-tight leading-none">
                  ${tier.price}
                </span>
                <span className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
                  {tier.priceSuffix ?? "/mo"}
                </span>
              </div>
              {tier.priceNote ? (
                <p className="mt-2 text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
                  {tier.priceNote}
                </p>
              ) : null}
            </div>

            <p className="text-sm leading-relaxed text-muted-foreground mb-12 grow">
              {tier.description}
            </p>

            <ul className="space-y-4 mb-12">
              {tier.features.map((feature) => {
                const label =
                  typeof feature === "string" ? feature : feature.label;
                const comingSoon =
                  typeof feature === "object" && feature.comingSoon;
                return (
                  <li
                    key={label}
                    className="flex items-start gap-4 text-sm text-muted-foreground"
                  >
                    <CheckCircle2
                      className="w-4 h-4 shrink-0 text-foreground mt-0.5"
                      strokeWidth={1.5}
                    />
                    <span className="flex flex-wrap items-center gap-2">
                      {label}
                      {comingSoon ? (
                        <>
                          {/* TODO: Export Reports feature not yet implemented in backend */}
                          <span className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground border border-border px-2 py-0.5 rounded-none">
                            Coming soon
                          </span>
                        </>
                      ) : null}
                    </span>
                  </li>
                );
              })}
            </ul>

            {(() => {
              const showCheckoutTooltip =
                tier.popular && checkoutUnavailableMessage != null;
              const ctaButton = (
                <Button
                  variant={tier.popular ? "default" : "outline"}
                  disabled={
                    (isLoading && tier.popular) ||
                    (tier.popular && !checkoutAvailable) ||
                    (!tier.popular && !isNavigationReady)
                  }
                  className={cn(
                    "w-full h-14 rounded-none text-xs uppercase tracking-widest font-medium transition-colors border cursor-pointer",
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
              );

              if (showCheckoutTooltip) {
                return (
                  <span
                    title={checkoutUnavailableMessage}
                    className="inline-block w-full"
                  >
                    {ctaButton}
                  </span>
                );
              }

              return ctaButton;
            })()}
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
    <footer className="col-span-12 grid grid-cols-1 md:grid-cols-12 bg-background border-b border-border relative z-10 overflow-visible">
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

        <a
          href="https://github.com/lvndry/clausea"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Clausea on GitHub"
          className="mt-8 inline-flex text-foreground hover:text-muted-foreground transition-colors"
        >
          <GithubIcon className="w-5 h-5" />
        </a>
      </div>

      {/* Links Columns */}
      <div className="col-span-12 md:col-span-8 grid grid-cols-1 md:grid-cols-2">
        <div className="px-6 md:px-10 py-12 md:py-20 border-b md:border-b-0 md:border-r border-border">
          <h5 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground mb-8">
            Product
          </h5>
          <ul className="space-y-4">
            {[
              { label: "Features", href: "/features" },
              { label: "Pricing", href: "/pricing" },
            ].map((link) => (
              <li key={link.label}>
                <Link
                  href={link.href}
                  className="text-xs uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  {link.label}
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
                href="/cookie-policy"
                className="text-xs uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Cookie Policy
              </Link>
            </li>
          </ul>
        </div>
      </div>

      {/* Newsletter & Bottom Bar */}
      <div className="col-span-12 grid grid-cols-1 md:grid-cols-12">
        <div className="col-span-12 md:col-span-4 px-6 md:px-10 py-12 md:border-r border-border flex flex-col justify-center">
          <p className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
            © {new Date().getFullYear()} Clausea AI
          </p>
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
