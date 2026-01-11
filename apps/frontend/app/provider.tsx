"use client";

import { ThemeProvider } from "next-themes";

import { LenisProvider } from "@/components/providers/lenis-provider";
import { ClerkProvider } from "@clerk/nextjs";

export function Provider(props: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <ThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem={true}
        disableTransitionOnChange
      >
        <LenisProvider>{props.children}</LenisProvider>
      </ThemeProvider>
    </ClerkProvider>
  );
}
