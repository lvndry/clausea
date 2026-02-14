"use client";

import { ArrowRight, Database, Layers, Target } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface DataPurposeLink {
  data_type: string;
  purposes: string[];
}

interface DataStoryProps {
  dataCollectionDetails?: DataPurposeLink[] | null;
  dataCollected?: string[] | null;
  dataPurposes?: string[] | null;
}

export function DataStory({
  dataCollectionDetails,
  dataCollected,
  dataPurposes,
}: DataStoryProps) {
  const hasStructuredData =
    dataCollectionDetails && dataCollectionDetails.length > 0;
  const hasFallbackData =
    (dataCollected && dataCollected.length > 0) ||
    (dataPurposes && dataPurposes.length > 0);

  if (!hasStructuredData && !hasFallbackData) {
    return null;
  }

  return (
    <Card variant="default" className="border-border">
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
              <Database className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <CardTitle className="text-lg">Your Data Story</CardTitle>
              <p className="text-sm text-muted-foreground mt-0.5">
                What data is collected and why
              </p>
            </div>
          </div>
          {hasStructuredData && (
            <Badge variant="outline" className="gap-1.5">
              <Layers className="h-3 w-3" />
              {dataCollectionDetails.length}
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {hasStructuredData ? (
          <div className="space-y-2.5">
            {dataCollectionDetails.map((item, index) => (
              <div
                key={index}
                className={cn(
                  "flex flex-col sm:flex-row sm:items-start gap-3 p-3.5 rounded-lg",
                  "border border-border/50 bg-muted/30",
                )}
              >
                {/* Data type */}
                <div className="flex items-center gap-2.5 sm:min-w-[140px]">
                  <div className="w-7 h-7 rounded-md bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center shrink-0">
                    <Database className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <span className="font-medium text-sm text-foreground">
                    {item.data_type}
                  </span>
                </div>

                {/* Arrow */}
                <ArrowRight className="h-4 w-4 text-muted-foreground/50 shrink-0 hidden sm:block mt-2" />

                {/* Purposes */}
                <div className="flex flex-wrap gap-1.5 flex-1">
                  {item.purposes.map((purpose, pIndex) => (
                    <Badge
                      key={pIndex}
                      variant="secondary"
                      size="sm"
                      className="gap-1 rounded-md"
                    >
                      <Target className="h-3 w-3" />
                      {purpose}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-5">
            {dataCollected && dataCollected.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                  <Database className="h-3.5 w-3.5" />
                  Data Collected
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {dataCollected.map((item, index) => (
                    <Badge key={index} variant="outline" className="rounded-md">
                      {item}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {dataPurposes && dataPurposes.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                  <Target className="h-3.5 w-3.5" />
                  Used For
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {dataPurposes.map((purpose, index) => (
                    <Badge
                      key={index}
                      variant="secondary"
                      className="rounded-md"
                    >
                      {purpose}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="pt-3 border-t border-border/50">
          <p className="text-sm text-muted-foreground">
            {hasStructuredData
              ? `${dataCollectionDetails.length} data types collected`
              : dataCollected
                ? `${dataCollected.length} data types identified`
                : null}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
