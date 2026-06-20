"use client";

import { ThemeProvider } from "next-themes";
import dynamic from "next/dynamic";

import { ClerkProvider } from "@clerk/nextjs";
import { ui } from "@clerk/ui";

function AuthProvider(props: { children: React.ReactNode }) {
  return (
    <ClerkProvider afterSignOutUrl="/" prefetchUI={false} ui={ui}>
      {props.children}
    </ClerkProvider>
  );
}

// Load Clerk client-only so React mounts bundled @clerk/ui before SSR-injected clerk-js.
const ClientAuthProvider = dynamic(() => Promise.resolve(AuthProvider), {
  ssr: false,
});

export function Provider(props: { children: React.ReactNode }) {
  return (
    <ClientAuthProvider>
      <ThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem={true}
        disableTransitionOnChange
      >
        {props.children}
      </ThemeProvider>
    </ClientAuthProvider>
  );
}
