"use client";

import {
  CreditCard,
  ExternalLink,
  Loader2,
  Settings,
  Shield,
  Sparkles,
} from "lucide-react";

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCheckout } from "@/hooks/useCheckout";
import {
  type SubscriptionResponse,
  subscriptionApi,
} from "@/lib/api/subscriptions";
import { useAuth, useUser } from "@clerk/nextjs";

const PRO_PRICE_ID =
  process.env.NEXT_PUBLIC_PADDLE_PRICE_PRO_MONTHLY ||
  process.env.NEXT_PUBLIC_PADDLE_PRICE_INDIVIDUAL_MONTHLY ||
  "";

export default function SettingsPage() {
  const { user } = useUser();
  const { getToken } = useAuth();
  const { startCheckout, isLoading: checkoutLoading } = useCheckout();
  const [subscription, setSubscription] = useState<SubscriptionResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchSubscription = useCallback(async () => {
    try {
      setLoading(true);
      // Get Clerk token - try template first, then default
      let token = await getToken({ template: "default" });
      if (!token) {
        token = await getToken();
      }
      const data = await subscriptionApi.getSubscription(token);
      setSubscription(data);
    } catch {
      // User might not have a subscription yet
      setSubscription(null);
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    fetchSubscription();
  }, [fetchSubscription]);

  const handleCancel = async () => {
    if (
      !confirm(
        "Are you sure you want to cancel? You will retain access until the end of your billing period.",
      )
    ) {
      return;
    }
    setActionLoading("cancel");
    setError(null);
    try {
      let token = await getToken({ template: "default" });
      if (!token) {
        token = await getToken();
      }
      await subscriptionApi.cancelSubscription(token);
      await fetchSubscription();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to cancel subscription",
      );
    } finally {
      setActionLoading(null);
    }
  };

  const handleResume = async () => {
    setActionLoading("resume");
    setError(null);
    try {
      let token = await getToken({ template: "default" });
      if (!token) {
        token = await getToken();
      }
      await subscriptionApi.resumeSubscription(token);
      await fetchSubscription();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to resume subscription",
      );
    } finally {
      setActionLoading(null);
    }
  };

  const handleBillingPortal = async () => {
    setActionLoading("portal");
    setError(null);
    try {
      let token = await getToken({ template: "default" });
      if (!token) {
        token = await getToken();
      }
      const data = await subscriptionApi.getBillingPortal(token);
      window.open(data.portal_url, "_blank");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to open billing portal",
      );
    } finally {
      setActionLoading(null);
    }
  };

  const isPro =
    subscription &&
    subscription.tier === "pro" &&
    subscription.status === "active";
  const isCanceled = subscription?.status === "canceled";
  const isPaused = subscription?.status === "paused";
  const isPastDue = subscription?.status === "past_due";

  return (
    <div className="flex flex-col space-y-8">
      {/* Header */}
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
            <Settings className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-3xl md:text-4xl font-display font-bold text-foreground tracking-tight">
              Settings
            </h1>
          </div>
        </div>
        <p className="text-muted-foreground text-base max-w-2xl">
          Manage your account and subscription.
        </p>
      </div>

      {error && (
        <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-xl text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Account Section */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <Shield className="w-5 h-5 text-primary" />
            <h2 className="font-display font-bold text-lg">Account</h2>
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between items-center py-2 border-b border-border/50">
              <span className="text-muted-foreground">Email</span>
              <span className="font-medium">
                {user?.primaryEmailAddress?.emailAddress || "..."}
              </span>
            </div>
            <div className="flex justify-between items-center py-2">
              <span className="text-muted-foreground">Plan</span>
              {loading ? (
                <Skeleton className="w-16 h-6" />
              ) : (
                <Badge
                  variant={isPro ? "default" : "secondary"}
                  className="gap-1"
                >
                  {isPro ? (
                    <>
                      <Sparkles className="w-3 h-3" />
                      Pro
                    </>
                  ) : (
                    "Free"
                  )}
                </Badge>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Subscription Section */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <CreditCard className="w-5 h-5 text-primary" />
            <h2 className="font-display font-bold text-lg">Subscription</h2>
          </div>

          {loading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-10 w-40" />
            </div>
          ) : isPro ? (
            <div className="space-y-4">
              <div className="space-y-3 text-sm">
                <div className="flex justify-between items-center py-2 border-b border-border/50">
                  <span className="text-muted-foreground">Status</span>
                  <Badge
                    variant={
                      isPastDue
                        ? "destructive"
                        : isCanceled
                          ? "secondary"
                          : "default"
                    }
                  >
                    {isPastDue
                      ? "Past Due"
                      : isCanceled
                        ? "Canceled"
                        : isPaused
                          ? "Paused"
                          : "Active"}
                  </Badge>
                </div>
                {subscription?.current_period_end && (
                  <div className="flex justify-between items-center py-2 border-b border-border/50">
                    <span className="text-muted-foreground">
                      {isCanceled ? "Access until" : "Next billing date"}
                    </span>
                    <span className="font-medium">
                      {new Date(
                        subscription.current_period_end,
                      ).toLocaleDateString()}
                    </span>
                  </div>
                )}
              </div>

              <div className="flex flex-wrap gap-3 pt-2">
                {subscription?.paddle_customer_id && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleBillingPortal}
                    disabled={actionLoading === "portal"}
                  >
                    {actionLoading === "portal" ? (
                      <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    ) : (
                      <ExternalLink className="w-4 h-4 mr-2" />
                    )}
                    Manage Billing
                  </Button>
                )}
                {isPaused ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleResume}
                    disabled={actionLoading === "resume"}
                  >
                    {actionLoading === "resume" && (
                      <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    )}
                    Resume Subscription
                  </Button>
                ) : !isCanceled ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground hover:text-destructive"
                    onClick={handleCancel}
                    disabled={actionLoading === "cancel"}
                  >
                    {actionLoading === "cancel" && (
                      <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    )}
                    Cancel Subscription
                  </Button>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                You are on the Free plan with 3 analyses per month. Upgrade to
                Pro for unlimited analyses.
              </p>
              <Button
                onClick={() => {
                  if (PRO_PRICE_ID) {
                    startCheckout(PRO_PRICE_ID);
                  }
                }}
                disabled={checkoutLoading || !PRO_PRICE_ID}
                className="gap-2"
              >
                {checkoutLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4" />
                )}
                Upgrade to Pro - $9/month
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
