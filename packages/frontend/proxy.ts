import type { NextFetchEvent, NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Define public routes that don't require authentication
const isPublicRoute = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/features",
  "/about",
  "/pricing",
  "/api/webhooks(.*)",
]);

// Define protected routes that require authentication
const isProtectedRoute = createRouteMatcher([
  "/products(.*)",
  "/dashboard(.*)",
  "/onboarding(.*)",
  "/c/(.*)",
  "/checkout(.*)",
]);

const clerkProxy = clerkMiddleware(async (auth, request) => {
  const { userId } = await auth();

  // If accessing a protected route without authentication, redirect to sign-in
  if (isProtectedRoute(request) && !userId) {
    const signInUrl = new URL("/sign-in", request.url);
    // Preserve the original URL so we can redirect back after sign-in
    signInUrl.searchParams.set("redirect_url", request.url);
    return NextResponse.redirect(signInUrl);
  }

  // Allow the request to proceed
  return NextResponse.next();
});

export function proxy(request: NextRequest, event: NextFetchEvent) {
  return clerkProxy(request, event);
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes - handled separately below)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico, sitemap.xml, robots.txt (metadata files)
     * - Static file extensions (images, fonts, documents, etc.)
     *
     * Note: Even when _next/data is excluded, proxy will still run for
     * _next/data routes for security (to protect data routes).
     */
    {
      source:
        "/((?!api|_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    },
    // Always run for API routes (Clerk handles authentication per route)
    {
      source: "/(api|trpc)(.*)",
    },
  ],
};
