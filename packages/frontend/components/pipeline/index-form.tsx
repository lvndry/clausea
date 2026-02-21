"use client";

import { Globe, ArrowRight, Loader2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface IndexFormProps {
  onSubmit: (url: string) => Promise<void>;
  isSubmitting: boolean;
  className?: string;
}

export function IndexForm({ onSubmit, isSubmitting, className }: IndexFormProps) {
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
        "rounded-xl border border-border bg-card p-1.5",
        "focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20",
        "transition-all duration-200",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <div className="flex items-center flex-1 gap-2 pl-3">
          <Globe className="h-4 w-4 text-muted-foreground/50 shrink-0" />
          <Input
            type="text"
            placeholder="Enter a website URL to analyze (e.g., netflix.com)"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              if (error) setError(null);
            }}
            disabled={isSubmitting}
            className="border-none bg-transparent focus-visible:ring-0 text-sm h-10 px-0"
          />
        </div>
        <Button
          type="submit"
          disabled={isSubmitting || !url.trim()}
          size="sm"
          className="h-9 px-4 rounded-lg shrink-0"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
              Analyzing...
            </>
          ) : (
            <>
              Analyze
              <ArrowRight className="ml-2 h-3.5 w-3.5" />
            </>
          )}
        </Button>
      </div>
      {error && (
        <p className="text-xs text-destructive px-3 pb-2 pt-1">{error}</p>
      )}
    </form>
  );
}
