import { type VariantProps, cva } from "class-variance-authority";

import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary/15 text-secondary hover:bg-secondary/25",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "text-foreground border-border/50 bg-background/50",
        success:
          "border-transparent bg-green-500/15 text-green-600 dark:text-green-400",
        warning:
          "border-transparent bg-amber-500/15 text-amber-600 dark:text-amber-400",
        danger:
          "border-transparent bg-red-500/15 text-red-600 dark:text-red-400",
        info: "border-transparent bg-blue-500/15 text-blue-600 dark:text-blue-400",
        gradient:
          "border-transparent bg-linear-to-r from-primary/20 to-secondary/20 text-foreground",
        glass:
          "border-white/20 bg-white/10 backdrop-blur-md text-foreground dark:border-white/10 dark:bg-white/5",
        pulse: "border-transparent bg-primary/15 text-primary animate-pulse",
      },
      size: {
        default: "px-2.5 py-0.5 text-xs",
        sm: "px-2 py-0.5 text-[10px]",
        lg: "px-3 py-1 text-sm",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface BadgeProps
  extends
    React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {
  icon?: React.ReactNode;
}

function Badge({
  className,
  variant,
  size,
  icon,
  children,
  ...props
}: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant, size }), className)} {...props}>
      {icon && <span className="mr-1.5 -ml-0.5">{icon}</span>}
      {children}
    </div>
  );
}

export { Badge, badgeVariants };
