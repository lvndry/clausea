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
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Database className="h-5 w-5 text-foreground" strokeWidth={1.5} />
          <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
            Your Data Story
          </h3>
        </div>
        {hasStructuredData && (
          <div className="px-3 py-1 border border-border text-[10px] uppercase tracking-widest font-bold bg-muted/5">
            {dataCollectionDetails.length} Collections Identified
          </div>
        )}
      </div>

      <div className="divide-y divide-border">
        {hasStructuredData ? (
          dataCollectionDetails.map((item, index) => (
            <div key={index} className="grid grid-cols-1 md:grid-cols-12">
              {/* Data type */}
              <div className="col-span-12 md:col-span-4 p-6 border-b md:border-b-0 md:border-r border-border bg-muted/5">
                <div className="flex items-center gap-3">
                  <Database
                    className="h-4 w-4 text-foreground"
                    strokeWidth={1.5}
                  />
                  <span className="font-display font-medium text-lg text-foreground">
                    {item.data_type}
                  </span>
                </div>
              </div>

              {/* Purposes */}
              <div className="col-span-12 md:col-span-8 p-6 flex flex-wrap gap-2">
                {item.purposes.map((purpose, pIndex) => (
                  <div
                    key={pIndex}
                    className="px-3 py-1 border border-border text-[10px] uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground hover:border-foreground transition-colors cursor-default"
                  >
                    {purpose}
                  </div>
                ))}
              </div>
            </div>
          ))
        ) : (
          <div className="divide-y divide-border px-6">
            {dataCollected && dataCollected.length > 0 && (
              <div className="py-6 space-y-4">
                <h4 className="text-[10px] font-bold uppercase tracking-widest text-foreground">
                  Data Collected
                </h4>
                <div className="flex flex-wrap gap-2">
                  {dataCollected.map((item, index) => (
                    <div
                      key={index}
                      className="px-3 py-1 border border-border text-[10px] uppercase tracking-widest font-medium text-muted-foreground"
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {dataPurposes && dataPurposes.length > 0 && (
              <div className="py-6 space-y-4">
                <h4 className="text-[10px] font-bold uppercase tracking-widest text-foreground">
                  Intended Use
                </h4>
                <div className="flex flex-wrap gap-2">
                  {dataPurposes.map((purpose, index) => (
                    <div
                      key={index}
                      className="px-3 py-1 border border-border text-[10px] uppercase tracking-widest font-medium text-muted-foreground"
                    >
                      {purpose}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-6 border-t border-border bg-muted/5">
        <p className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
          {hasStructuredData
            ? `${dataCollectionDetails.length} data vectors mapped`
            : dataCollected
              ? `${dataCollected.length} data points identified`
              : "Analysis complete"}
        </p>
      </div>
    </div>
  );
}
