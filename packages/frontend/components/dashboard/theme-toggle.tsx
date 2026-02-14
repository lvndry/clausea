"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();

  // Use suppressHydrationWarning in the consuming component to avoid hydration mismatch
  // The theme value from next-themes handles this gracefully
  const isDark = resolvedTheme === "dark";

  return (
    <Button
      variant="outline"
      size="sm"
      className="w-full justify-start"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      suppressHydrationWarning
    >
      {isDark ? (
        <>
          <Moon className="h-4 w-4 mr-2" />
          <span suppressHydrationWarning>Dark Mode</span>
        </>
      ) : (
        <>
          <Sun className="h-4 w-4 mr-2" />
          <span suppressHydrationWarning>Light Mode</span>
        </>
      )}
    </Button>
  );
}
