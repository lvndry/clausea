import { httpJson } from "./http";

export interface TierInfo {
  tier: string;
  display_name: string;
  description: string;
  monthly_limit: number;
  limit_type: string;
}

export interface TierLimitsResponse {
  tiers: TierInfo[];
  limit_type: string;
  period: string;
}

export async function getTierLimits(): Promise<TierLimitsResponse> {
  return httpJson<TierLimitsResponse>("/api/users/tier-limits");
}
