"use client";

import { ThemeProvider } from "next-themes";

import { ClerkProvider } from "@clerk/nextjs";
import { ui } from "@clerk/ui";

export function Provider(props: {
  children: React.ReactNode;
  publishableKey?: string;
}) {
  return (
    <ClerkProvider
      publishableKey={props.publishableKey}
      afterSignOutUrl="/"
      prefetchUI={false}
      ui={ui}
    >
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
