// User and subscription types for Clausea

export type UserTier = "free" | "individual" | "business" | "enterprise";

export type SubscriptionStatus =
  | "active"
  | "past_due"
  | "canceled"
  | "paused"
  | "inactive";

export interface Subscription {
  tier: UserTier;
  status: SubscriptionStatus;
  paddle_customer_id: string | null;
  paddle_subscription_id: string | null;
  started_at?: string;
  current_period_end?: string;
  canceled_at?: string;
}

export interface User {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  tier: UserTier;
  onboarding_completed: boolean;
  subscription?: Subscription;
}

export interface UsageSummary {
  user_id: string;
  tier: UserTier;
  current_month: string;
  usage: {
    used: number;
    limit: number;
    remaining: number;
    percentage: number;
  };
  monthly_history: Record<string, number>;
}

export interface TierInfo {
  tier: UserTier;
  display_name: string;
  description: string;
  monthly_limit: number;
  limit_type: string;
  price: number;
}
