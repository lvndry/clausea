import { AlertCircle, AlertTriangle, FileQuestion, Home } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ErrorDisplayProps {
  title?: string;
  message?: string;
  variant?: "not-found" | "error" | "warning";
  className?: string;
  icon?: React.ReactElement;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
}

const variantConfig = {
  "not-found": {
    icon: FileQuestion,
    defaultTitle: "Not Found",
    defaultMessage: "The requested resource could not be found.",
    iconColor: "text-muted-foreground",
    iconBg: "bg-muted",
    borderColor: "border-muted",
  },
  error: {
    icon: AlertCircle,
    defaultTitle: "Error",
    defaultMessage: "Something went wrong. Please try again later.",
    iconColor: "text-destructive",
    iconBg: "bg-destructive/10",
    borderColor: "border-destructive/20",
  },
  warning: {
    icon: AlertTriangle,
    defaultTitle: "Warning",
    defaultMessage: "An issue occurred while processing your request.",
    iconColor: "text-amber-600 dark:text-amber-500",
    iconBg: "bg-amber-50 dark:bg-amber-950/20",
    borderColor: "border-amber-200 dark:border-amber-800",
  },
};

export function ErrorDisplay({
  title,
  message,
  variant = "error",
  className,
  icon,
  actionLabel,
  actionHref,
  onAction,
}: ErrorDisplayProps) {
  const config = variantConfig[variant];
  const IconComponent = config.icon;

  const actionButton = actionHref ? (
    <Button asChild variant="outline" className="mt-4">
      <Link href={actionHref}>
        {actionLabel || "Go Home"}
        <Home className="ml-2 h-4 w-4" />
      </Link>
    </Button>
  ) : onAction ? (
    <Button onClick={onAction} variant="outline" className="mt-4">
      {actionLabel || "Try Again"}
    </Button>
  ) : null;

  return (
    <div
      className={cn(
        "flex min-h-[400px] items-center justify-center p-6",
        className,
      )}
    >
      <Card
        className={cn("w-full max-w-md border-2 shadow-lg", config.borderColor)}
      >
        <CardContent className="flex flex-col items-center justify-center p-12 text-center">
          <div
            className={cn(
              "mb-6 flex h-20 w-20 items-center justify-center rounded-full",
              config.iconBg,
            )}
          >
            {icon ? (
              <div className={cn("h-10 w-10", config.iconColor)}>{icon}</div>
            ) : (
              <IconComponent className={cn("h-10 w-10", config.iconColor)} />
            )}
          </div>

          <h2 className="mb-3 text-2xl font-semibold tracking-tight">
            {title || config.defaultTitle}
          </h2>

          <p className="mb-6 text-sm text-muted-foreground leading-relaxed max-w-sm">
            {message || config.defaultMessage}
          </p>

          {actionButton}
        </CardContent>
      </Card>
    </div>
  );
}
