export const AUTH_ROUTES = {
  signUp: "/sign-up",
  signIn: "/sign-in",
  onboarding: "/onboarding",
  products: "/products",
} as const;

export function getSignedInDestination(
  onboardingCompleted: boolean | undefined,
): string {
  return onboardingCompleted ? AUTH_ROUTES.products : AUTH_ROUTES.onboarding;
}
