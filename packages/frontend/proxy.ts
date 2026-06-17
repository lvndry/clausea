import type { NextFetchEvent, NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const CRAWLER_UA =
  /bot|crawl|spider|facebookexternalhit|Slackbot|Twitterbot|WhatsApp|TelegramBot|LinkedInBot|discordbot|Applebot|preview|embed/i;

// /products/[slug] — anything under /products/ with at least one more segment
const PRODUCT_DETAIL_RE = /^\/products\/[^/]+/;

const FREE_PRODUCT_VIEWS = 5;
const PV_COOKIE = "__pv";

const isPublicRoute = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/features",
  "/about",
  "/pricing",
  "/products",
  "/api/webhooks(.*)",
]);

const isProtectedRoute = createRouteMatcher([
  "/dashboard(.*)",
  "/onboarding(.*)",
  "/c/(.*)",
  "/checkout(.*)",
]);

const clerkProxy = clerkMiddleware(async (auth, request) => {
  const { userId } = await auth();
  const { pathname } = new URL(request.url);

  // Always let crawlers through so OG metadata is scrapeable
  const ua = request.headers.get("user-agent") ?? "";
  if (CRAWLER_UA.test(ua)) {
    return NextResponse.next();
  }

  // Hard-protected routes require a session
  if (isProtectedRoute(request) && !userId) {
    const signInUrl = new URL("/sign-in", request.url);
    signInUrl.searchParams.set("redirect_url", request.url);
    return NextResponse.redirect(signInUrl);
  }

  // Metered product detail pages for unauthenticated users
  if (!userId && PRODUCT_DETAIL_RE.test(pathname)) {
    const count = parseInt(request.cookies.get(PV_COOKIE)?.value ?? "0", 10);

    if (count >= FREE_PRODUCT_VIEWS) {
      const signInUrl = new URL("/sign-in", request.url);
      signInUrl.searchParams.set("redirect_url", request.url);
      return NextResponse.redirect(signInUrl);
    }

    const response = NextResponse.next();
    response.cookies.set(PV_COOKIE, String(count + 1), {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24 * 30,
    });
    return response;
  }

  return NextResponse.next();
});

export function proxy(request: NextRequest, event: NextFetchEvent) {
  return clerkProxy(request, event);
}

export const config = {
  matcher: [
    {
      source:
        "/((?!api|_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    },
    {
      source: "/(api|trpc)(.*)",
    },
  ],
};
