export async function register() {
  if (typeof window !== "undefined") {
    // Client-side initialization
    const { default: posthog } = await import("posthog-js");

    if (!process.env.NEXT_PUBLIC_POSTHOG_KEY) {
      console.warn("NEXT_PUBLIC_POSTHOG_KEY is not set");
      return;
    }

    posthog.init(process.env.NEXT_PUBLIC_POSTHOG_KEY, {
      api_host:
        process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://eu.i.posthog.com",
      ui_host:
        process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://eu.i.posthog.com",
      defaults: "2025-11-30",
      capture_exceptions: true,
      debug: process.env.NODE_ENV === "development",
      loaded: (posthog) => {
        if (process.env.NODE_ENV === "development") {
          console.log("PostHog initialized", posthog);
        }
      },
    });
  }
}
