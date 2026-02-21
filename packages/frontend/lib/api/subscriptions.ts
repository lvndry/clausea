// API client for subscription management
import { getBackendUrl } from "@/lib/config";

export interface CheckoutRequest {
  price_id: string;
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
  private async fetchWithAuth(
    endpoint: string,
    token: string | null,
    options: RequestInit = {}
  ) {
    const url = getBackendUrl(endpoint);
    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    if (token) {
      (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
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

  async createCheckout(
    request: CheckoutRequest,
    token: string | null
  ): Promise<CheckoutResponse> {
    return this.fetchWithAuth("/subscriptions/checkout", token, {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  async getSubscription(token: string | null): Promise<SubscriptionResponse> {
    return this.fetchWithAuth("/subscriptions/me", token);
  }

  async cancelSubscription(
    token: string | null
  ): Promise<{ success: boolean; message: string }> {
    return this.fetchWithAuth("/subscriptions/cancel", token, {
      method: "POST",
    });
  }

  async pauseSubscription(
    token: string | null
  ): Promise<{ success: boolean; message: string }> {
    return this.fetchWithAuth("/subscriptions/pause", token, {
      method: "POST",
    });
  }

  async resumeSubscription(
    token: string | null
  ): Promise<{ success: boolean; message: string }> {
    return this.fetchWithAuth("/subscriptions/resume", token, {
      method: "POST",
    });
  }

  async getBillingPortal(token: string | null): Promise<BillingPortalResponse> {
    return this.fetchWithAuth("/subscriptions/portal", token);
  }
}

export const subscriptionApi = new SubscriptionAPI();
