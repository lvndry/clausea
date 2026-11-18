const APP_ORIGIN =
  process.env.NEXT_PUBLIC_PAGES_APP_ORIGIN ?? "https://clausea.co";

const SIGN_UP_URL = `${APP_ORIGIN}/sign-up`;

export function useGetStartedNavigation() {
  return {
    destination: SIGN_UP_URL,
    navigate: () => {
      window.location.assign(SIGN_UP_URL);
    },
    isNavigationReady: true,
  };
}
