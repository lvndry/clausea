"use client";

import { ArrowRight, Globe, Loader2 } from "lucide-react";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface IndexFormProps {
  onSubmit: (url: string) => Promise<void>;
  isSubmitting: boolean;
  className?: string;
}

export function IndexForm({
  onSubmit,
  isSubmitting,
  className,
}: IndexFormProps) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  function validateUrl(value: string): boolean {
    if (!value.trim()) {
      setError("Please enter a URL");
      return false;
    }

    // Accept domains (e.g., "netflix.com") or full URLs
    const urlPattern = /^(https?:\/\/)?([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}/;
    if (!urlPattern.test(value.trim())) {
      setError("Please enter a valid URL or domain (e.g., netflix.com)");
      return false;
    }

    setError(null);
    return true;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validateUrl(url)) return;
    await onSubmit(url.trim());
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={cn(
        "border border-border bg-background p-1.5",
        "focus-within:border-foreground/30",
        "transition-all duration-200",
        className,
      )}
    >
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
        <div className="flex items-center flex-1 gap-4 pl-4 font-serif italic text-muted-foreground/50">
          <Globe className="h-4 w-4 shrink-0" strokeWidth={1} />
          <Input
            type="text"
            placeholder="URL of new product to index (e.g. apple.com)"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              if (error) setError(null);
            }}
            disabled={isSubmitting}
            className="border-none bg-transparent focus-visible:ring-0 text-foreground text-sm h-10 px-0 uppercase tracking-widest font-sans font-medium"
          />
        </div>
        <Button
          type="submit"
          disabled={isSubmitting || !url.trim()}
          size="sm"
          className="h-12 sm:h-10 px-8 rounded-none shrink-0 bg-foreground text-background hover:bg-foreground/90 border border-foreground text-[10px] uppercase tracking-widest font-bold"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="mr-3 h-4 w-4 animate-spin" />
              Processing
            </>
          ) : (
            <>
              Index
              <ArrowRight className="ml-3 h-4 w-4 transition-transform group-hover:translate-x-1" />
            </>
          )}
        </Button>
      </div>
      {error && (
        <div className="text-[10px] text-destructive px-4 pb-2 pt-1 uppercase tracking-widest font-bold">
          {error}
        </div>
      )}
    </form>
  );
}
