import NextLink from "next/dist/client/link";

import type { ComponentProps } from "react";

type LinkProps = ComponentProps<typeof NextLink>;

const EXPORTED_PATHS = new Set([
  "/",
  "/features",
  "/pricing",
  "/privacy",
  "/terms",
  "/cookie-policy",
]);

const APP_ORIGIN =
  process.env.NEXT_PUBLIC_PAGES_APP_ORIGIN ?? "https://clausea.co";

// Pages that need the app (sign-in, products, contact) are not part of the
// static site, so links to them open the real app instead of a missing page.
export default function Link(props: LinkProps) {
  const { href } = props;
  if (typeof href === "string" && href.startsWith("/")) {
    const path = href.split(/[?#]/)[0] ?? href;
    if (!EXPORTED_PATHS.has(path)) {
      const {
        href: _href,
        prefetch: _prefetch,
        replace: _replace,
        scroll: _scroll,
        shallow: _shallow,
        passHref: _passHref,
        legacyBehavior: _legacyBehavior,
        locale: _locale,
        as: _as,
        onNavigate: _onNavigate,
        children,
        ...anchorProps
      } = props;
      return (
        <a href={`${APP_ORIGIN}${href}`} {...anchorProps}>
          {children}
        </a>
      );
    }
  }
  return <NextLink {...props} />;
}
