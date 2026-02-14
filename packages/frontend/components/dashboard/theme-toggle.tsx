"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // Wait until mounted on client to avoid hydration mismatch
  useEffect(() => {
    // This is intentional to avoid hydration mismatch
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  // Render a placeholder during SSR and initial client render
  if (!mounted) {
    return (
      <Button
        variant="outline"
        size="sm"
        className="w-full justify-start"
        disabled
      >
        <Sun className="h-4 w-4 mr-2" />
        <span>Theme</span>
      </Button>
    );
  }

  const isDark = resolvedTheme === "dark";

  return (
    <Button
      variant="outline"
      size="sm"
      className="w-full justify-start"
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {isDark ? (
        <>
          <Moon className="h-4 w-4 mr-2" />
          <span>Dark Mode</span>
        </>
      ) : (
        <>
          <Sun className="h-4 w-4 mr-2" />
          <span>Light Mode</span>
        </>
      )}
    </Button>
  );
}
