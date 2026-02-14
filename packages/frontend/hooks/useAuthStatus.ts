import { useAuth } from "@clerk/nextjs";

export function useAuthStatus() {
  const { isLoaded, isSignedIn } = useAuth();

  return {
    isLoaded,
    isSignedIn,
    isLoading: !isLoaded,
  };
}
