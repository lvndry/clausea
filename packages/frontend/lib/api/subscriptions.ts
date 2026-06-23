// API client for subscription management (browser → Next.js /api proxy → backend)

export interface CheckoutRequest {
  price_id: string;
}
interface CheckoutResponse {
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

interface BillingPortalResponse {
  portal_url: string;
}

class SubscriptionAPI {
  private async fetchApi<T>(
    endpoint: string,
    options: RequestInit = {},
  ): Promise<T> {
    const url = `/api/subscriptions${endpoint}`;
    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: "include",
    });

    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ detail: "Unknown error" }));
      throw new Error(
        (error as { detail?: string; error?: string }).detail ||
          (error as { detail?: string; error?: string }).error ||
          `HTTP ${response.status}`,
      );
    }

    return response.json() as Promise<T>;
  }

  async createCheckout(request: CheckoutRequest): Promise<CheckoutResponse> {
    return this.fetchApi("/checkout", {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  async getSubscription(): Promise<SubscriptionResponse> {
    return this.fetchApi("/me");
  }

  async syncSubscription(): Promise<{
    tier: string;
    status: string;
    synced: boolean;
  }> {
    return this.fetchApi("/sync", { method: "POST" });
  }

  async cancelSubscription(): Promise<{ success: boolean; message: string }> {
    return this.fetchApi("/cancel", { method: "POST" });
  }

  async pauseSubscription(): Promise<{ success: boolean; message: string }> {
    return this.fetchApi("/pause", { method: "POST" });
  }

  async resumeSubscription(): Promise<{ success: boolean; message: string }> {
    return this.fetchApi("/resume", { method: "POST" });
  }

  async getBillingPortal(): Promise<BillingPortalResponse> {
    return this.fetchApi("/portal");
  }
}

export const subscriptionApi = new SubscriptionAPI();
