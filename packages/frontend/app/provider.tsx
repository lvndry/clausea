"use client";

import { ThemeProvider } from "next-themes";

import { ClerkProvider } from "@clerk/nextjs";

export function Provider(props: { children: React.ReactNode }) {
  return (
    <ClerkProvider afterSignOutUrl="/" prefetchUI={false}>
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
