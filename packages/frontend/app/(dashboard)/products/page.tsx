"use client";

import {
  ArrowLeft,
  ArrowRight,
  ArrowUpDown,
  CheckCircle2,
  ChevronDown,
  Search,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import posthog from "posthog-js";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { IndexForm } from "@/components/pipeline/index-form";
import { PipelineProgress } from "@/components/pipeline/pipeline-progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Product } from "@/types";
import { useUser } from "@clerk/nextjs";
import { useAnalytics } from "@hooks/useAnalytics";
import { usePipelineJob } from "@hooks/usePipelineJob";

function ProductCard({
  product,
  index,
  onClick,
}: {
  product: Product;
  index: number;
  onClick: () => void;
}) {
  const [logo, setLogo] = useState<string | null>(product.logo || null);
  const [isLoadingLogo, setIsLoadingLogo] = useState(false);
  const [hasTriedLoading, setHasTriedLoading] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

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

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.03 }}
      className="group"
      onClick={onClick}
    >
      <div
        ref={cardRef}
        className="border border-border bg-background p-6 sm:p-8 relative overflow-hidden transition-colors hover:border-foreground/30 cursor-pointer h-full flex flex-col gap-6"
      >
        <div className="flex items-start justify-between">
          <div className="w-12 h-12 flex items-center justify-center border border-border bg-muted/5 shrink-0">
            {isLoadingLogo ? (
              <div className="w-6 h-6 border-b-2 border-foreground rounded-full animate-spin" />
            ) : logo ? (
              <img
                src={logo}
                alt={`${product.name} logo`}
                className="w-full h-full object-contain p-2"
                loading="lazy"
              />
            ) : (
              <span className="text-[10px] font-bold text-muted-foreground">
                {product.name.substring(0, 2).toUpperCase()}
              </span>
            )}
          </div>
          <div className="text-[8px] font-bold uppercase tracking-[0.2em] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer">
            View Analysis
          </div>
        </div>

        <div className="space-y-4 grow">
          <h3 className="font-display font-medium text-2xl text-foreground">
            {product.name}
          </h3>
          {product.description && (
            <p className="text-sm text-muted-foreground line-clamp-2 leading-relaxed font-serif italic">
              &ldquo;{product.description}&rdquo;
            </p>
          )}
        </div>

        <div className="pt-6 border-t border-border mt-auto flex items-center justify-between gap-4">
          <div className="flex flex-wrap gap-2">
            {product.categories?.slice(0, 3).map((cat) => (
              <span
                key={cat}
                className="text-[8px] font-bold uppercase tracking-widest text-muted-foreground px-2 py-0.5 border border-border bg-muted/5 whitespace-nowrap"
              >
                {cat}
              </span>
            ))}
            {(!product.categories || product.categories.length === 0) && (
              <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                General Service
              </span>
            )}
          </div>
          <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-foreground group-hover:translate-x-1 transition-all shrink-0" />
        </div>
      </div>
    </motion.div>
  );
}

function ProductsPageContent() {
  const { user } = useUser();
  const router = useRouter();
  const searchParams = useSearchParams();

  const { trackUserJourney, trackPageView } = useAnalytics();

  const [products, setProducts] = useState<Product[]>([]);
  const [sortBy, setSortBy] = useState<"name" | "risk" | "recent">("name");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");

  // Pagination
  const ITEMS_PER_PAGE = 20;
  const pageParam = searchParams.get("page");
  const currentPage = pageParam ? parseInt(pageParam) : 1;

  // Pipeline state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const {
    jobId: activeJobId,
    setJobId: setActiveJobId,
    clearJobId: clearActiveJobId,
  } = usePipelineJob();
  const [alreadyIndexed, setAlreadyIndexed] = useState<{
    slug: string;
    name: string;
  } | null>(null);

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
          product.categories?.some((cat) =>
            cat.toLowerCase().includes(searchTerm.toLowerCase()),
          ),
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

  const filteredProducts = products.filter(
    (product) =>
      product.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      product.description?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      product.categories?.some((cat) =>
        cat.toLowerCase().includes(searchTerm.toLowerCase()),
      ),
  );

  const sortedProducts = [...filteredProducts].sort((a, b) => {
    if (sortBy === "name") return a.name.localeCompare(b.name);
    return a.name.localeCompare(b.name);
  });

  const totalPages = Math.ceil(sortedProducts.length / ITEMS_PER_PAGE);
  const paginatedProducts = sortedProducts.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE,
  );

  const setPage = (page: number) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", page.toString());
    router.push(`/products?${params.toString()}`);
  };

  async function handlePipelineSubmit(url: string) {
    setIsSubmitting(true);
    setAlreadyIndexed(null);
    try {
      const res = await fetch("/api/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || "Failed to start analysis");
      }
      const data = await res.json();

      if (data.already_indexed) {
        setAlreadyIndexed({ slug: data.product_slug, name: data.product_name });
        return;
      }

      setActiveJobId(data.job_id);
      posthog.capture("pipeline_started", {
        url,
        product_slug: data.product_slug,
        job_id: data.job_id,
      });
    } catch (err) {
      console.error("Pipeline submit error:", err);
      setError(err instanceof Error ? err.message : "Failed to start analysis");
    } finally {
      setIsSubmitting(false);
    }
  }

  function handlePipelineComplete(productSlug: string) {
    posthog.capture("pipeline_completed", { product_slug: productSlug });
    clearActiveJobId();
    // Optionally auto-navigate after a brief delay
    setTimeout(() => {
      router.push(`/products/${productSlug}`);
    }, 1500);
  }

  function handlePipelineDismiss() {
    clearActiveJobId();
  }

  function handleProductClick(product: Product) {
    trackUserJourney.productViewed(product.slug, product.name);
    router.push(`/products/${product.slug}`);
  }

  if (loading) {
    return (
      <div className="space-y-12">
        <div className="space-y-4">
          <Skeleton className="h-10 w-64 rounded-none" />
          <Skeleton className="h-4 w-full max-w-2xl rounded-none" />
        </div>
        <Skeleton className="h-16 w-full rounded-none" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-64 rounded-none" />
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
    <div className="flex flex-col space-y-12">
      {/* Header */}
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 border border-border flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-foreground" strokeWidth={1.5} />
          </div>
          <div>
            <h1 className="text-4xl md:text-5xl font-display font-medium text-foreground tracking-tight">
              Service Intelligence
            </h1>
          </div>
        </div>
        <p className="text-muted-foreground text-sm uppercase tracking-widest font-medium max-w-2xl leading-relaxed">
          The privacy archive. AI-powered structural analysis of the digital
          service layer.
        </p>
      </div>

      {/* URL Submission - DeepWiki style */}
      <IndexForm onSubmit={handlePipelineSubmit} isSubmitting={isSubmitting} />

      {/* Already-indexed banner */}
      {alreadyIndexed && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="border border-[#2B7A5C]/20 bg-[#2B7A5C]/5 p-4 flex items-center justify-between gap-6">
            <div className="flex items-center gap-3">
              <CheckCircle2
                className="h-4 w-4 text-[#2B7A5C]"
                strokeWidth={2}
              />
              <p className="text-[10px] uppercase tracking-widest font-bold text-[#2B7A5C]">
                Analysis available: {alreadyIndexed.name}
              </p>
            </div>
            <div className="flex gap-4 items-center">
              <Link href={`/products/${alreadyIndexed.slug}`}>
                <Button
                  size="sm"
                  variant="ghost"
                  className="rounded-none h-8 px-0 text-[10px] uppercase tracking-widest font-bold text-[#2B7A5C] hover:bg-transparent hover:text-[#2B7A5C]/70"
                >
                  View Archive
                </Button>
              </Link>
              <Button
                size="sm"
                variant="ghost"
                className="rounded-none h-8 px-0 text-[10px] uppercase tracking-widest font-bold text-muted-foreground hover:bg-transparent hover:text-foreground"
                onClick={() => setAlreadyIndexed(null)}
              >
                Dismiss
              </Button>
            </div>
          </div>
        </motion.div>
      )}

      {/* Pipeline Progress */}
      {activeJobId && (
        <PipelineProgress
          jobId={activeJobId}
          onComplete={handlePipelineComplete}
          onDismiss={handlePipelineDismiss}
        />
      )}

      {/* Search & Filter */}
      <div className="border border-border bg-background flex flex-col md:flex-row divide-y md:divide-y-0 md:divide-x divide-border">
        <div className="relative flex-1 p-4">
          <Search
            className="absolute left-8 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40"
            strokeWidth={1.5}
          />
          <Input
            placeholder="Search the archive..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-12 h-10 border-none bg-transparent focus-visible:ring-0 text-sm uppercase tracking-widest font-medium placeholder:text-muted-foreground/30 rounded-none shadow-none"
          />
        </div>

        <div className="flex items-center p-2 bg-muted/5">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-10 rounded-none px-6 text-[10px] uppercase tracking-widest font-bold hover:bg-transparent"
              >
                <ArrowUpDown
                  className="mr-3 h-4 w-4 text-foreground/40"
                  strokeWidth={1.5}
                />
                <span className="text-muted-foreground mr-2">Sort:</span>
                <span className="text-foreground">{sortBy}</span>
                <ChevronDown className="ml-3 h-3 w-3 opacity-30" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="w-56 p-2 rounded-none border-border shadow-none"
            >
              <DropdownMenuItem
                onClick={() => setSortBy("name")}
                className="rounded-none cursor-pointer text-[10px] uppercase tracking-widest font-bold focus:bg-muted/10 p-3"
              >
                Name (A-Z)
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setSortBy("risk")}
                className="rounded-none cursor-pointer text-[10px] uppercase tracking-widest font-bold focus:bg-muted/10 p-3"
              >
                Risk Level
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setSortBy("recent")}
                className="rounded-none cursor-pointer text-[10px] uppercase tracking-widest font-bold focus:bg-muted/10 p-3"
              >
                Recently Updated
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <div className="h-6 w-px bg-border mx-2" />

          <div className="px-6 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            {filteredProducts.length} Entries
          </div>
        </div>
      </div>

      {/* Grid - Varied spacing */}
      <AnimatePresence mode="popLayout">
        {filteredProducts.length === 0 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center py-32 text-center"
          >
            <div className="w-16 h-16 border border-border flex items-center justify-center mb-6">
              <Search className="h-6 w-6 text-muted-foreground/20" />
            </div>
            <div className="space-y-2">
              <h3 className="text-sm font-bold uppercase tracking-[0.2em] text-foreground">
                Archive result: null
              </h3>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground max-w-sm mx-auto">
                The specified identifier does not exist within our current
                mapping.
              </p>
            </div>
          </motion.div>
        ) : (
          <div className="space-y-12">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {paginatedProducts.map((product, index) => (
                <ProductCard
                  key={product.id}
                  product={product}
                  index={index}
                  onClick={() => handleProductClick(product)}
                />
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="pt-12 border-t border-border flex items-center justify-between">
                <Button
                  variant="ghost"
                  disabled={currentPage === 1}
                  onClick={() => setPage(currentPage - 1)}
                  className="rounded-none text-[10px] uppercase tracking-widest font-bold gap-3 px-0 hover:bg-transparent hover:text-foreground/70"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Previous
                </Button>

                <div className="flex gap-4">
                  {[...Array(totalPages)].map((_, i) => (
                    <button
                      key={i + 1}
                      onClick={() => setPage(i + 1)}
                      className={cn(
                        "text-[10px] font-bold uppercase tracking-widest transition-colors",
                        currentPage === i + 1
                          ? "text-foreground underline underline-offset-8"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {i + 1}
                    </button>
                  ))}
                </div>

                <Button
                  variant="ghost"
                  disabled={currentPage === totalPages}
                  onClick={() => setPage(currentPage + 1)}
                  className="rounded-none text-[10px] uppercase tracking-widest font-bold gap-3 px-0 hover:bg-transparent hover:text-foreground/70"
                >
                  Next
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ProductsPageFallback() {
  return (
    <div className="space-y-12">
      <div className="space-y-4">
        <Skeleton className="h-10 w-64 rounded-none" />
        <Skeleton className="h-4 w-full max-w-2xl rounded-none" />
      </div>
      <Skeleton className="h-16 w-full rounded-none" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-64 rounded-none" />
        ))}
      </div>
    </div>
  );
}

export default function ProductsPage() {
  return (
    <Suspense fallback={<ProductsPageFallback />}>
      <ProductsPageContent />
    </Suspense>
  );
}
