const APP_ORIGIN =
  process.env.NEXT_PUBLIC_PAGES_APP_ORIGIN ?? "https://clausea.co";

// The static site cannot start a checkout, so it hands over to the app.
export function useCheckout() {
  return {
    startCheckout: (_priceId: string) => {
      window.location.assign(`${APP_ORIGIN}/pricing`);
    },
    isLoading: false,
    error: null as string | null,
  };
}
