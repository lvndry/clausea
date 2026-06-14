import type { LucideIcon } from "lucide-react";
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle,
  CheckCircle2,
  Shield,
  ShieldAlert,
  TrendingDown,
} from "lucide-react";

export type VerdictType =
  | "very_user_friendly"
  | "user_friendly"
  | "moderate"
  | "pervasive"
  | "very_pervasive";

export interface VerdictConfig {
  // Common fields
  label: string;
  description: string;

  // For product cards (products page)
  variant: "success" | "warning" | "danger" | "secondary";
  cardIcon: LucideIcon;
  cardColor: string;
  cardBg: string; // With border style

  // For overview card
  overviewIcon: LucideIcon;
  overviewColor: string;
  overviewBg: string; // With opacity style
}

const VERDICT_CONFIGS: Record<VerdictType, VerdictConfig> = {
  very_user_friendly: {
    variant: "success",
    cardIcon: CheckCircle2,
    cardColor: "text-green-600",
    cardBg: "bg-green-50 border-green-200",
    overviewIcon: CheckCircle,
    overviewColor: "text-green-600",
    overviewBg: "bg-green-500/10",
    label: "Very User Friendly",
    description: "Excellent privacy practices",
  },
  user_friendly: {
    variant: "success",
    cardIcon: CheckCircle2,
    cardColor: "text-green-500",
    cardBg: "bg-green-50 border-green-200",
    overviewIcon: TrendingDown,
    overviewColor: "text-green-500",
    overviewBg: "bg-green-500/10",
    label: "User Friendly",
    description: "Good privacy practices",
  },
  moderate: {
    variant: "warning",
    cardIcon: ShieldAlert,
    cardColor: "text-amber-600",
    cardBg: "bg-amber-50 border-amber-200",
    overviewIcon: Shield,
    overviewColor: "text-yellow-500",
    overviewBg: "bg-yellow-500/10",
    label: "Moderate",
    description: "Standard privacy practices",
  },
  pervasive: {
    variant: "warning",
    cardIcon: ShieldAlert,
    cardColor: "text-orange-600",
    cardBg: "bg-orange-50 border-orange-200",
    overviewIcon: AlertTriangle,
    overviewColor: "text-orange-500",
    overviewBg: "bg-orange-500/10",
    label: "Pervasive",
    description: "Concerning privacy practices",
  },
  very_pervasive: {
    variant: "danger",
    cardIcon: ShieldAlert,
    cardColor: "text-red-600",
    cardBg: "bg-red-50 border-red-200",
    overviewIcon: AlertOctagon,
    overviewColor: "text-red-500",
    overviewBg: "bg-red-500/10",
    label: "Very Pervasive",
    description: "Very concerning privacy practices",
  },
};

const UNKNOWN_VERDICT_CONFIG: VerdictConfig = {
  variant: "secondary",
  cardIcon: Shield,
  cardColor: "text-muted-foreground",
  cardBg: "bg-muted border-border",
  overviewIcon: Shield,
  overviewColor: "text-gray-500",
  overviewBg: "bg-gray-500/10",
  label: "Unknown",
  description: "Analysis pending",
};

export function getVerdictConfig(verdict: string): VerdictConfig {
  return VERDICT_CONFIGS[verdict as VerdictType] ?? UNKNOWN_VERDICT_CONFIG;
}
