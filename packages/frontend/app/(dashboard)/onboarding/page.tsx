"use client";

import { ArrowRight, Shield, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Logo } from "@/data/logo";
import { cn } from "@/lib/utils";
import { useUser } from "@clerk/nextjs";

import { useAnalytics } from "../../../hooks/useAnalytics";
import { useUserData } from "../../../hooks/useUserData";
import { posthog } from "../../../lib/analytics";

export default function OnboardingPage() {
  const { user } = useUser();
  const router = useRouter();
  const { trackUserJourney } = useAnalytics();
  const { userData, loading: userDataLoading } = useUserData();
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Form state
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [useCase, setUseCase] = useState("");
  const [goal, setGoal] = useState("");

  useEffect(() => {
    trackUserJourney.onboardingStarted();

    if (user) {
      setFirstName(user.firstName || "");
      setLastName(user.lastName || "");
      setEmail(user.primaryEmailAddress?.emailAddress || "");

      posthog.identify(user.id, {
        email: user.primaryEmailAddress?.emailAddress,
        first_name: user.firstName,
        last_name: user.lastName,
      });

      void fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.primaryEmailAddress?.emailAddress,
          first_name: user.firstName,
          last_name: user.lastName,
        }),
      }).catch(() => {});
    }
  }, [user, trackUserJourney]);

  useEffect(() => {
    if (!userDataLoading && userData?.onboarding_completed) {
      router.push("/products");
    }
  }, [userData, userDataLoading, router]);

  function validateForm() {
    const newErrors: Record<string, string> = {};

    if (!email.trim()) {
      newErrors.email = "Email is required";
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      newErrors.email = "Please enter a valid email address";
    }

    if (!role) {
      newErrors.role = "Please select your role";
    }

    if (!useCase) {
      newErrors.useCase = "Please select how you want to use Clausea";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Enter" && !loading) {
      event.preventDefault();
      void handleSubmit(event as any);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    if (!user) return;

    if (!validateForm()) {
      return;
    }

    setLoading(true);

    try {
      posthog.capture("onboarding_submitted", {
        role,
        use_case: useCase,
        goal,
      });

      await fetch("/api/users/complete-onboarding", { method: "POST" });

      trackUserJourney.onboardingCompleted({
        user_id: user.id,
        email: user.primaryEmailAddress?.emailAddress,
        role,
        use_case: useCase,
        goal,
      });

      router.push("/products");
    } catch (error) {
      console.error("Submission failed:", error);
    } finally {
      setLoading(false);
    }
  }

  if (userDataLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center dashboard-bg">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-4"
        >
          <div className="w-14 h-14 bg-linear-to-br from-primary/20 to-secondary/20 border border-primary/20 rounded-2xl flex items-center justify-center">
            <Logo className="w-7 h-7 text-primary animate-pulse" />
          </div>
          <p className="text-sm font-bold uppercase tracking-widest text-muted-foreground">
            Loading...
          </p>
        </motion.div>
      </div>
    );
  }

  if (userData?.onboarding_completed) {
    return null;
  }

  return (
    <div className="min-h-screen dashboard-bg flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-2xl">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="text-center mb-10"
        >
          <div className="flex items-center justify-center gap-3 mb-6">
            <div className="w-12 h-12 bg-linear-to-br from-primary/20 to-secondary/20 border border-primary/20 rounded-xl flex items-center justify-center">
              <Logo className="w-6 h-6 text-primary" />
            </div>
            <span className="font-display font-bold text-3xl tracking-tight text-foreground">
              Clausea{" "}
              <span className="text-secondary font-serif italic font-normal">
                AI
              </span>
            </span>
          </div>
          <h1 className="font-display font-bold text-4xl md:text-5xl tracking-tight text-foreground mb-4">
            Tell us about{" "}
            <span className="text-primary font-serif italic">you</span>
          </h1>
          <p className="text-lg text-muted-foreground max-w-md mx-auto">
            This helps us tailor legal analysis to your needs and deliver
            insights that matter.
          </p>
        </motion.div>

        {/* Form Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
        >
          <Card
            variant="glass"
            className="p-8 md:p-10 rounded-3xl border-border/50"
          >
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Name Fields */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                    First Name
                  </label>
                  <Input
                    placeholder="John"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    onKeyDown={handleKeyDown}
                    className="h-12 rounded-xl bg-muted/30 border-border/50 focus:border-primary/50 focus:bg-background transition-all"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                    Last Name
                  </label>
                  <Input
                    placeholder="Doe"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    onKeyDown={handleKeyDown}
                    className="h-12 rounded-xl bg-muted/30 border-border/50 focus:border-primary/50 focus:bg-background transition-all"
                  />
                </div>
              </div>

              {/* Email */}
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                  Email
                </label>
                <Input
                  placeholder="john@example.com"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className={cn(
                    "h-12 rounded-xl bg-muted/30 border-border/50 focus:border-primary/50 focus:bg-background transition-all",
                    errors.email && "border-red-500/50 focus:border-red-500",
                  )}
                />
                {errors.email && (
                  <p className="text-red-500 text-sm">{errors.email}</p>
                )}
              </div>

              {/* Role */}
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                  I am a...
                </label>
                <Select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className={cn(
                    "h-12 rounded-xl bg-muted/30 border-border/50 focus:border-primary/50 focus:bg-background transition-all",
                    errors.role && "border-red-500/50 focus:border-red-500",
                  )}
                >
                  <option value="">Select your role</option>
                  <option value="individual">
                    Privacy-conscious individual
                  </option>
                  <option value="founder">Founder</option>
                  <option value="compliance_officer">Compliance officer</option>
                  <option value="legal_team">Legal team</option>
                  <option value="other">Other</option>
                </Select>
                {errors.role && (
                  <p className="text-red-500 text-sm">{errors.role}</p>
                )}
              </div>

              {/* Use Case */}
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                  I want to use Clausea to...
                </label>
                <Select
                  value={useCase}
                  onChange={(e) => setUseCase(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className={cn(
                    "h-12 rounded-xl bg-muted/30 border-border/50 focus:border-primary/50 focus:bg-background transition-all",
                    errors.useCase && "border-red-500/50 focus:border-red-500",
                  )}
                >
                  <option value="">Select your use case</option>
                  <option value="analyze_privacy_policies">
                    Understand privacy policies
                  </option>
                  <option value="vendor_risk">
                    Assess vendor and contract risk
                  </option>
                  <option value="monitor_changes">
                    Monitor policy changes
                  </option>
                  <option value="bulk_review">
                    Bulk review for legal team
                  </option>
                </Select>
                {errors.useCase && (
                  <p className="text-red-500 text-sm">{errors.useCase}</p>
                )}
              </div>

              {/* Goals */}
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                  Tell us about your goals
                </label>
                <Textarea
                  placeholder="What are your priorities? How could Clausea help you?"
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className="min-h-[120px] rounded-xl bg-muted/30 border-border/50 focus:border-primary/50 focus:bg-background transition-all resize-none"
                />
              </div>

              {/* Submit */}
              <Button
                type="submit"
                disabled={loading}
                className="w-full rounded-xl h-14 text-base font-semibold bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg shadow-primary/20 disabled:opacity-50 disabled:cursor-not-allowed mt-4 gap-2"
              >
                {loading ? (
                  "Saving..."
                ) : (
                  <>
                    Continue to Dashboard
                    <ArrowRight className="h-5 w-5" />
                  </>
                )}
              </Button>
            </form>

            {/* Trust indicators */}
            <div className="flex items-center justify-center gap-6 mt-8 pt-6 border-t border-border/50">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Shield className="h-4 w-4 text-secondary" />
                <span>Secure & Private</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Sparkles className="h-4 w-4 text-primary" />
                <span>AI-Powered</span>
              </div>
            </div>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
