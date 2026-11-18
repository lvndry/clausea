# Static landing page for GitHub Pages

`build.mjs` builds the landing page and its public pages (features, pricing, privacy, terms, cookie policy) as a static site for [lvndry.github.io/clausea](https://lvndry.github.io/clausea/). The app at clausea.co is unchanged.

```sh
node pages-build/build.mjs   # writes ../../.pages-build/out
```

## How it works

The script copies the frontend to `.pages-build/` at the repo root and builds the copy with `output: "export"` and the base path `/clausea` (`next.config.mjs` here replaces the app's config in the copy).

- **Left out of the copy:** everything that needs a server or an account: the sign-in and dashboard routes, the API routes, server actions, the proxy, analytics setup, the contact page (it posts to the backend) and the bot page.
- **`stubs/`:** stand-ins for Clerk (always signed out), PostHog (does nothing) and `next/link` (links to pages that are not in the static site open the real app at clausea.co).
- **`overrides/`:** static versions of `useCheckout`, `useProPricing` and `useGetStartedNavigation`, laid over the copy at the same paths. Every button that needs the app sends the visitor to clausea.co.

The pages' canonical URL and social image still point at clausea.co.

## When it breaks

A change that makes an exported page depend on something that is left out, such as a new Clerk hook, fails the `Pages` workflow on the pull request. Add a stub or an override here, or leave that page out in `build.mjs`.
