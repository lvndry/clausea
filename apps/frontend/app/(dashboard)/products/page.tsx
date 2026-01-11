"use client";

import {
  ArrowUpDown,
  ChevronDown,
  Search,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import posthog from "posthog-js";

import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { getVerdictConfig } from "@/lib/verdict";
import type { Product } from "@/types";
import { useUser } from "@clerk/nextjs";
import { useAnalytics } from "@hooks/useAnalytics";

function ProductCard({
  product,
  index,
  verdict,
  riskScore,
  isLoadingSummary,
  fetchMetaSummary,
  onClick,
}: {
  product: Product;
  index: number;
  verdict?: string;
  riskScore?: number;
  isLoadingSummary?: boolean;
  fetchMetaSummary?: (slug: string) => void;
  onClick: () => void;
}) {
  const [logo, setLogo] = useState<string | null>(product.logo || null);
  const [isLoadingLogo, setIsLoadingLogo] = useState(false);
  const [hasTriedLoading, setHasTriedLoading] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  const verdictConfig = verdict ? getVerdictConfig(verdict) : null;

  // Lazy load logo
  useEffect(() => {
    if (hasTriedLoading || logo || !cardRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !hasTriedLoading && !logo) {
            setHasTriedLoading(true);
            setIsLoadingLogo(true);

            const params = new URLSearchParams();
            params.append("slug", product.slug);

            fetch(`/api/products/logos?${params.toString()}`)
              .then((res) => {
                if (res.ok) return res.json();
                return null;
              })
              .then((data) => {
                if (data?.logo) setLogo(data.logo);
              })
              .catch((err) => {
                console.warn(`Failed to fetch logo for ${product.name}:`, err);
              })
              .finally(() => {
                setIsLoadingLogo(false);
              });
            observer.disconnect();
          }
        });
      },
      { rootMargin: "50px" },
    );

    observer.observe(cardRef.current);
    return () => observer.disconnect();
  }, [product.slug, product.name, logo, hasTriedLoading]);

  // Lazy load summary
  useEffect(() => {
    if (verdict !== undefined || isLoadingSummary) return;

    const summaryObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && fetchMetaSummary) {
            fetchMetaSummary(product.slug);
            summaryObserver.disconnect();
          }
        });
      },
      { rootMargin: "100px" },
    );

    if (cardRef.current) summaryObserver.observe(cardRef.current);
    return () => summaryObserver.disconnect();
  }, [product.slug, verdict, isLoadingSummary, fetchMetaSummary]);

  // Vary card styles - some with borders, some minimal
  const cardVariants = [
    "border border-border bg-card",
    "border-2 border-border/60 bg-card",
    "border border-border/40 bg-muted/30",
  ];
  const cardStyle = cardVariants[index % cardVariants.length];

  // Risk color - solid, not gradient
  const getRiskColor = (score?: number) => {
    if (!score) return "bg-muted";
    if (score >= 7) return "bg-red-500";
    if (score >= 4) return "bg-amber-500";
    return "bg-green-500";
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.03 }}
    >
      <Card
        ref={cardRef}
        variant="default"
        className={cn(
          "group cursor-pointer transition-all duration-200",
          cardStyle,
          "hover:border-primary/50 hover:shadow-md",
        )}
        onClick={onClick}
      >
        <CardContent className="p-5">
          <div className="flex flex-col gap-4">
            {/* Header: Logo + Verdict */}
            <div className="flex items-start justify-between gap-3">
              <div className="relative">
                {isLoadingLogo ? (
                  <div className="w-12 h-12 rounded-lg bg-muted animate-pulse" />
                ) : logo ? (
                  <div className="w-12 h-12 rounded-lg overflow-hidden bg-background border border-border flex items-center justify-center p-2">
                    <img
                      src={logo}
                      alt={`${product.name} logo`}
                      className="w-full h-full object-contain"
                      loading="lazy"
                    />
                  </div>
                ) : (
                  <div className="w-12 h-12 rounded-lg bg-primary/10 border border-primary/20 text-primary flex items-center justify-center font-display font-bold text-lg">
                    {product.name.charAt(0).toUpperCase()}
                  </div>
                )}
              </div>

              {verdictConfig && (
                <Badge
                  variant="outline"
                  size="sm"
                  className="gap-1 font-medium uppercase tracking-wide rounded-md"
                >
                  <verdictConfig.cardIcon className="h-3 w-3" />
                  {verdictConfig.label}
                </Badge>
              )}
            </div>

            {/* Product Info */}
            <div className="space-y-1">
              <h3 className="font-display font-bold text-lg text-foreground group-hover:text-primary transition-colors">
                {product.name}
              </h3>
              {product.description && (
                <p className="text-sm text-muted-foreground line-clamp-2 leading-snug">
                  {product.description}
                </p>
              )}
            </div>

            {/* Risk Score - Simple bar */}
            <div className="pt-3 border-t border-border/50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Risk
                </span>
                <span className="text-sm font-bold text-foreground">
                  {isLoadingSummary ? (
                    <Skeleton className="w-8 h-4" />
                  ) : riskScore !== undefined ? (
                    <span
                      className={cn(
                        riskScore >= 7
                          ? "text-red-600"
                          : riskScore >= 4
                            ? "text-amber-600"
                            : "text-green-600",
                      )}
                    >
                      {Math.round(riskScore)}/10
                    </span>
                  ) : (
                    <span className="text-muted-foreground">--</span>
                  )}
                </span>
              </div>

              {/* Simple progress bar */}
              <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                {isLoadingSummary ? (
                  <div className="h-full w-1/3 bg-muted-foreground/20 animate-pulse" />
                ) : riskScore !== undefined ? (
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${(riskScore / 10) * 100}%` }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className={cn(
                      "h-full rounded-full",
                      getRiskColor(riskScore),
                    )}
                  />
                ) : null}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export default function ProductsPage() {
  const { user } = useUser();
  const router = useRouter();

  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const { trackUserJourney, trackPageView } = useAnalytics();

  const [products, setProducts] = useState<Product[]>([]);
  const [productSummaries, setProductSummaries] = useState<Record<string, any>>(
    {},
  );
  const [summaryLoading, setSummaryLoading] = useState<Record<string, boolean>>(
    {},
  );
  const [sortBy, setSortBy] = useState<"name" | "risk" | "recent">("name");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    trackPageView("products");
  }, [trackPageView]);

  useEffect(() => {
    if (searchTerm.trim()) {
      const filteredCount = products.filter(
        (product) =>
          product.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          product.description
            ?.toLowerCase()
            .includes(searchTerm.toLowerCase()) ||
          product.industry?.toLowerCase().includes(searchTerm.toLowerCase()),
      ).length;
      trackUserJourney.productSearched(searchTerm, filteredCount);
    }
  }, [searchTerm, products, trackUserJourney]);

  useEffect(() => {
    async function fetchProducts() {
      try {
        setLoading(true);
        const response = await fetch("/api/products");
        if (!response.ok) throw new Error("Failed to fetch products");
        const data = await response.json();
        setProducts(data);
      } catch (err) {
        console.error("Error fetching products:", err);
        setError(
          err instanceof Error ? err.message : "Failed to fetch products",
        );
      } finally {
        setLoading(false);
      }
    }
    fetchProducts();
  }, []);

  const fetchMetaSummary = useCallback(
    (slug: string) => {
      if (!slug || productSummaries[slug] || summaryLoading[slug]) return;
      setSummaryLoading((s) => ({ ...s, [slug]: true }));
      fetch(`/api/products/${slug}/overview`)
        .then((res) => {
          if (res.ok) return res.json();
          return null;
        })
        .then((data) => {
          if (data) setProductSummaries((s) => ({ ...s, [slug]: data }));
        })
        .catch(() => {})
        .finally(() => {
          setSummaryLoading((s) => ({ ...s, [slug]: false }));
        });
    },
    [productSummaries, summaryLoading],
  );

  const filteredProducts = products.filter(
    (product) =>
      product.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      product.description?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      product.industry?.toLowerCase().includes(searchTerm.toLowerCase()),
  );

  const sortedProducts = [...filteredProducts].sort((a, b) => {
    if (sortBy === "name") return a.name.localeCompare(b.name);
    if (sortBy === "risk") {
      const ra = productSummaries[a.slug]?.verdict || "";
      const rb = productSummaries[b.slug]?.verdict || "";
      const rank = (v: string) =>
        v === "very_pervasive"
          ? 5
          : v === "pervasive"
            ? 4
            : v === "moderate"
              ? 3
              : v === "user_friendly"
                ? 2
                : v === "very_user_friendly"
                  ? 1
                  : 0;
      return rank(rb) - rank(ra);
    }
    if (sortBy === "recent") {
      const ta = new Date(
        productSummaries[a.slug]?.last_updated || 0,
      ).getTime();
      const tb = new Date(
        productSummaries[b.slug]?.last_updated || 0,
      ).getTime();
      return tb - ta;
    }
    return 0;
  });

  function handleProductClick(product: Product) {
    trackUserJourney.productViewed(product.slug, product.name);
    router.push(`/products/${product.slug}`);
  }

  if (loading) {
    return (
      <div className="space-y-8">
        <div className="space-y-3">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-5 w-96" />
        </div>
        <Skeleton className="h-12 w-full rounded-xl" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-[200px] rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center space-y-4 max-w-md mx-auto p-6"
        >
          <div className="w-16 h-16 rounded-xl bg-destructive/10 flex items-center justify-center mx-auto">
            <ShieldAlert className="h-8 w-8 text-destructive" />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-bold font-display text-foreground">
              Error Loading Products
            </h2>
            <p className="text-muted-foreground">{error}</p>
          </div>
          <Button
            onClick={() => window.location.reload()}
            className="rounded-lg"
          >
            Try Again
          </Button>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="flex flex-col space-y-8">
      {/* Header - More personality */}
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-3xl md:text-4xl font-display font-bold text-foreground tracking-tight">
              Service Intelligence
            </h1>
          </div>
        </div>
        <p className="text-muted-foreground text-base max-w-2xl">
          Understand what you're agreeing to. AI-powered privacy analysis for
          the services you use daily.
        </p>
      </div>

      {/* Search - Simple, solid */}
      <div className="rounded-xl border border-border bg-card p-2 flex flex-col md:flex-row gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/50" />
          <Input
            placeholder="Search products..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10 h-10 border-none bg-transparent focus-visible:ring-0 text-sm"
          />
        </div>

        <div className="flex items-center gap-2 px-2">
          <div className="hidden md:block w-px h-6 bg-border" />

          <Badge variant="secondary" size="sm" className="gap-1.5 rounded-md">
            {filteredProducts.length}
          </Badge>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-9 rounded-lg px-3 text-sm"
              >
                <ArrowUpDown className="mr-2 h-3.5 w-3.5" />
                <span className="hidden sm:inline">Sort:</span>
                <span className="ml-1 capitalize text-primary font-medium">
                  {sortBy}
                </span>
                <ChevronDown className="ml-2 h-3 w-3 opacity-50" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48 p-1 rounded-lg">
              <DropdownMenuItem
                onClick={() => {
                  setSortBy("name");
                  posthog.capture("product_sort_changed", {
                    sort_by: "name",
                    products_count: filteredProducts.length,
                  });
                }}
                className="rounded-md cursor-pointer"
              >
                Name (A-Z)
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => {
                  setSortBy("risk");
                  posthog.capture("product_sort_changed", {
                    sort_by: "risk",
                    products_count: filteredProducts.length,
                  });
                }}
                className="rounded-md cursor-pointer"
              >
                Risk Level
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => {
                  setSortBy("recent");
                  posthog.capture("product_sort_changed", {
                    sort_by: "recent",
                    products_count: filteredProducts.length,
                  });
                }}
                className="rounded-md cursor-pointer"
              >
                Recently Updated
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Grid - Varied spacing */}
      <AnimatePresence mode="popLayout">
        {filteredProducts.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex flex-col items-center justify-center py-20 text-center space-y-4"
          >
            <div className="w-20 h-20 rounded-xl bg-muted/50 flex items-center justify-center">
              <Search className="h-10 w-10 text-muted-foreground/30" />
            </div>
            <div className="space-y-1">
              <h3 className="text-xl font-bold font-display">
                No products found
              </h3>
              <p className="text-muted-foreground max-w-sm mx-auto text-sm">
                Try searching for a different product or check back later.
              </p>
            </div>
          </motion.div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {sortedProducts.map((product, index) => {
              const verdict = productSummaries[product.slug]?.verdict;
              const riskScore = productSummaries[product.slug]?.risk_score;
              const isLoadingSummary = summaryLoading[product.slug];

              return (
                <ProductCard
                  key={product.id}
                  product={product}
                  index={index}
                  verdict={verdict}
                  riskScore={riskScore}
                  isLoadingSummary={isLoadingSummary}
                  fetchMetaSummary={fetchMetaSummary}
                  onClick={() => handleProductClick(product)}
                />
              );
            })}
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
