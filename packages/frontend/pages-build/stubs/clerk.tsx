import type { ReactNode } from "react";

// The static site has no accounts, so Clerk is replaced by a signed-out stub.
export function ClerkProvider(props: { children: ReactNode }) {
  return <>{props.children}</>;
}

export function useAuth() {
  return { isLoaded: true, isSignedIn: false } as const;
}
