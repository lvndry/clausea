import { useEffect, useState } from "react";

import { useUser } from "@clerk/nextjs";

interface UserData {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  onboarding_completed?: boolean;
  tier?: string;
  created_at?: string;
  updated_at?: string;
}

export function useUserData() {
  const { user, isLoaded } = useUser();
  const [userData, setUserData] = useState<UserData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoaded || !user) {
      setLoading(false);
      return;
    }

    async function fetchUserData() {
      try {
        setLoading(true);
        const response = await fetch("/api/users/me");

        if (!response.ok) {
          throw new Error(`Failed to fetch user data: ${response.statusText}`);
        }

        const data = await response.json();
        setUserData(data);
        setError(null);
      } catch (err) {
        console.error("Error fetching user data:", err);
        setError(
          err instanceof Error ? err.message : "Failed to fetch user data",
        );
      } finally {
        setLoading(false);
      }
    }

    void fetchUserData();
  }, [isLoaded, user]);

  return {
    userData,
    loading,
    error,
    isLoaded,
    isSignedIn: !!user,
  };
}
