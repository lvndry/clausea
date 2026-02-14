import { Loader2 } from "lucide-react";

import * as React from "react";

import { cn } from "@/lib/utils";

export interface SpinnerProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: "sm" | "md" | "lg" | "xl";
}

const sizeMap = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-8 w-8",
  xl: "h-12 w-12",
};

const Spinner = React.forwardRef<HTMLDivElement, SpinnerProps>(
  ({ className, size = "md", ...props }, ref) => {
    return (
      <div ref={ref} className={cn("inline-block", className)} {...props}>
        <Loader2 className={cn("animate-spin", sizeMap[size])} />
      </div>
    );
  },
);
Spinner.displayName = "Spinner";

export { Spinner };
