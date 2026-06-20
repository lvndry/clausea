"use client";

import { ThemeProvider } from "next-themes";

import { ClerkProvider } from "@clerk/nextjs";
import { ui } from "@clerk/ui";

export function Provider(props: { children: React.ReactNode }) {
  return (
    <ClerkProvider afterSignOutUrl="/" prefetchUI={false} ui={ui}>
      <ThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem={true}
        disableTransitionOnChange
      >
        {props.children}
      </ThemeProvider>
    </ClerkProvider>
  );
}
