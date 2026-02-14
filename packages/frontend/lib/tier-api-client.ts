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
  const response = await fetch("/api/users/tier-limits", {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch tier limits: ${response.status}`);
  }

  return response.json();
}
