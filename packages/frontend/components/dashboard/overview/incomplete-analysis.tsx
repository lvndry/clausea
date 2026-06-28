import { FileWarning } from "lucide-react";

const MIN_DOCS_FOR_ANALYSIS = 3;

interface IncompleteAnalysisProps {
  documentCount?: number;
  minDocs?: number;
}

export function IncompleteAnalysis({
  documentCount,
  minDocs = MIN_DOCS_FOR_ANALYSIS,
}: IncompleteAnalysisProps) {
  const hasZeroDocs = documentCount === 0;

  const body = hasZeroDocs
    ? "We couldn't read any policy documents for this product. This is usually caused by bot protection or JavaScript-only pages that our crawler can't access."
    : `We only found ${documentCount ?? "a few"} policy document${documentCount !== 1 ? "s" : ""}, but need at least ${minDocs} to produce a reliable analysis. Terms of service, cookie policy, or other documents may be missing.`;

  return (
    <div className="grid grid-cols-1 md:grid-cols-12 border border-border bg-background min-h-[320px]">
      <div className="col-span-12 flex flex-col items-center justify-center text-center p-12 md:p-16">
        <div className="relative mb-8">
          <div className="flex items-center justify-center h-16 w-16 rounded-full border border-amber-200 bg-amber-50 dark:border-amber-800/50 dark:bg-amber-950/20">
            <FileWarning
              className="h-7 w-7 text-amber-600 dark:text-amber-500"
              strokeWidth={1.5}
              aria-hidden="true"
            />
          </div>
        </div>

        <h2 className="text-xl md:text-2xl font-display font-medium text-foreground mb-3">
          Not enough policy documents to analyze
        </h2>

        <p className="text-sm text-muted-foreground leading-relaxed max-w-md">
          {body}
        </p>
      </div>
    </div>
  );
}
