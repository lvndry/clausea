"use server";

import { getBackendUrl } from "@lib/config";
import { httpJson } from "@lib/http";

export interface TriggerPipelineResult {
  job_id: string;
  product_slug: string;
  product_name: string;
  status: string;
  message: string;
  already_indexed?: boolean;
}

export async function triggerPipeline(
  url: string,
): Promise<TriggerPipelineResult> {
  try {
    return await httpJson<TriggerPipelineResult>(
      getBackendUrl("/pipeline/crawl"),
      { method: "POST", body: { url } },
    );
  } catch (error) {
    console.error("Error starting pipeline:", error);
    throw new Error("Failed to start analysis");
  }
}
