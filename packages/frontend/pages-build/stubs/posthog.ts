// The static site does no tracking, so analytics calls do nothing.
const posthog = {
  capture(..._args: unknown[]): void {},
};

export default posthog;
