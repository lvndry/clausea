// API client for subscription management
import { getBackendUrl } from "@/lib/config";

const API_BASE = getBackendUrl("");

export interface CheckoutRequest {
  price_id: string;
  success_url?: string;
  cancel_url?: string;
}

export interface CheckoutResponse {
  checkout_url: string;
  session_id: string;
}

export interface SubscriptionResponse {
  tier: string;
  status: string;
  paddle_customer_id: string | null;
  paddle_subscription_id: string | null;
  started_at?: string;
  current_period_end?: string;
  canceled_at?: string;
}

export interface BillingPortalResponse {
  portal_url: string;
}

class SubscriptionAPI {
  private async fetchWithAuth(endpoint: string, options: RequestInit = {}) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      credentials: "include",
    });

    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async createCheckout(request: CheckoutRequest): Promise<CheckoutResponse> {
    return this.fetchWithAuth("/subscriptions/checkout", {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  async getSubscription(): Promise<SubscriptionResponse> {
    return this.fetchWithAuth("/subscriptions/me");
  }

  async cancelSubscription(): Promise<{ success: boolean; message: string }> {
    return this.fetchWithAuth("/subscriptions/cancel", {
      method: "POST",
    });
  }

  async pauseSubscription(): Promise<{ success: boolean; message: string }> {
    return this.fetchWithAuth("/subscriptions/pause", {
      method: "POST",
    });
  }

  async resumeSubscription(): Promise<{ success: boolean; message: string }> {
    return this.fetchWithAuth("/subscriptions/resume", {
      method: "POST",
    });
  }

  async getBillingPortal(): Promise<BillingPortalResponse> {
    return this.fetchWithAuth("/subscriptions/portal");
  }
}

export const subscriptionApi = new SubscriptionAPI();
