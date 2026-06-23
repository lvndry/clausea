import type { NextFetchEvent, NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { PREVIEW_TOKEN_COOKIE } from "@/lib/preview-token";
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const CRAWLER_UA =
  /bot|crawl|spider|facebookexternalhit|Slackbot|Twitterbot|WhatsApp|TelegramBot|LinkedInBot|discordbot|Applebot|preview|embed/i;

// /products/[slug] — anything under /products/ with at least one more segment
const PRODUCT_DETAIL_RE = /^\/products\/[^/]+/;

const FREE_PRODUCT_VIEWS = 15;
const PV_COOKIE = "__pv";

function currentPreviewMonthKey(): string {
  const now = new Date();
  const month = String(now.getUTCMonth() + 1).padStart(2, "0");
  return `${now.getUTCFullYear()}-${month}`;
}

function parsePreviewViewCount(cookieValue: string | undefined): number {
  const monthKey = currentPreviewMonthKey();
  if (!cookieValue) {
    return 0;
  }

  // Legacy cookies stored only a count — start fresh with monthly tracking.
  if (!cookieValue.includes(":")) {
    return 0;
  }

  const [storedMonth, countPart] = cookieValue.split(":", 2);
  if (storedMonth !== monthKey) {
    return 0;
  }

  const count = Number.parseInt(countPart ?? "0", 10);
  return Number.isNaN(count) ? 0 : count;
}

function formatPreviewViewCookie(count: number): string {
  return `${currentPreviewMonthKey()}:${count}`;
}

const isProtectedRoute = createRouteMatcher([
  "/dashboard(.*)",
  "/onboarding(.*)",
  "/c/(.*)",
  "/checkout(.*)",
]);

const clerkProxy = clerkMiddleware(async (auth, request) => {
  const { userId } = await auth();
  const { pathname } = new URL(request.url);

  // Hard-protected routes always require a session — UA spoofing must not bypass these
  if (isProtectedRoute(request) && !userId) {
    const signInUrl = new URL("/sign-in", request.url);
    signInUrl.searchParams.set("redirect_url", request.url);
    return NextResponse.redirect(signInUrl);
  }

  // Products list requires auth — backend returns 401 without a token
  if ((pathname === "/products" || pathname === "/products/") && !userId) {
    const signInUrl = new URL("/sign-in", request.url);
    signInUrl.searchParams.set("redirect_url", request.url);
    return NextResponse.redirect(signInUrl);
  }

  // Product detail pages: crawlers pass freely (OG scraping), humans get metered access
  if (PRODUCT_DETAIL_RE.test(pathname)) {
    const ua = request.headers.get("user-agent") ?? "";
    if (CRAWLER_UA.test(ua)) {
      return NextResponse.next();
    }

    if (!userId) {
      // Next.js prefetch requests must not consume the free-view quota
      const isPrefetch =
        request.headers.get("next-router-prefetch") === "1" ||
        request.headers.get("purpose") === "prefetch";
      if (isPrefetch) return NextResponse.next();

      const count = parsePreviewViewCount(
        request.cookies.get(PV_COOKIE)?.value,
      );

      if (count >= FREE_PRODUCT_VIEWS) {
        const signInUrl = new URL("/sign-in", request.url);
        signInUrl.searchParams.set("redirect_url", request.url);
        return NextResponse.redirect(signInUrl);
      }

      const response = NextResponse.next();
      response.cookies.set(PV_COOKIE, formatPreviewViewCookie(count + 1), {
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        maxAge: 60 * 60 * 24 * 30,
      });

      const existingPreviewToken =
        request.cookies.get(PREVIEW_TOKEN_COOKIE)?.value;
      if (!existingPreviewToken) {
        response.cookies.set(PREVIEW_TOKEN_COOKIE, crypto.randomUUID(), {
          httpOnly: true,
          sameSite: "lax",
          path: "/",
          maxAge: 60 * 60 * 24 * 30,
        });
      }

      return response;
    }
  }

  if (userId) {
    const response = NextResponse.next();
    response.cookies.delete(PREVIEW_TOKEN_COOKIE);
    response.cookies.delete(PV_COOKIE);
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
