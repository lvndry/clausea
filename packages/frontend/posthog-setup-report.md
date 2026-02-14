# PostHog post-wizard report

The wizard has completed a deep integration of PostHog into your Clausea Next.js project. The integration includes automatic pageview tracking, user identification via Clerk authentication, custom event capture for key business actions, and error tracking. PostHog is initialized via `instrumentation-client.ts` (the recommended approach for Next.js 15.3+) with exception capture enabled.

## Events Instrumented

| Event Name | Description | File Path |
|------------|-------------|-----------|
| `checkout_started` | User initiates checkout process for a subscription plan | `hooks/useCheckout.ts` |
| `checkout_completed` | User successfully completes subscription checkout | `app/(dashboard)/checkout/success/page.tsx` |
| `checkout_error` | Error occurred during checkout process | `hooks/useCheckout.ts` |
| `pricing_plan_clicked` | User clicks on a pricing plan CTA button | `components/clausea/PricingAndFooter.tsx` |
| `contact_form_submitted` | User submits the contact form for sales or support inquiries | `app/(site)/contact/page.tsx` |
| `newsletter_subscribed` | User subscribes to newsletter via footer email input | `components/clausea/PricingAndFooter.tsx` |
| `chat_message_sent` | User sends a message in the chat conversation about a product | `app/(dashboard)/c/[slug]/page.tsx` |
| `product_tab_changed` | User switches between Overview and Sources tabs on a product page | `app/(dashboard)/products/[slug]/page.tsx` |
| `document_source_clicked` | User clicks to view source document details | `components/dashboard/sources-list.tsx` |
| `cta_hero_clicked` | User clicks the main call-to-action button in the hero section | `components/clausea/Hero.tsx` |
| `product_sort_changed` | User changes the sort order of products (name, risk, recent) | `app/(dashboard)/products/page.tsx` |
| `billing_portal_opened` | User opens the billing portal to manage subscription | `hooks/useBillingPortal.ts` |
| `billing_portal_error` | Error occurred when opening billing portal | `hooks/useBillingPortal.ts` |

## User Identification

User identification is handled automatically via the existing `useAnalytics` hook which identifies users when they sign in via Clerk. The `identifyUser` function in `lib/analytics.ts` sends user properties including email, name, and sign-in timestamps to PostHog. On sign out, `posthog.reset()` is called to clear the user identity.

## Error Tracking

Exception capture is enabled via `capture_exceptions: true` in the PostHog initialization. Additionally, `posthog.captureException()` is called explicitly in error handlers for:
- Checkout errors
- Billing portal errors
- Chat message send failures
- Checkout success page load failures

## Next steps

We've built some insights and a dashboard for you to keep an eye on user behavior, based on the events we just instrumented:

### Dashboard
- [Analytics Basics Dashboard](https://eu.posthog.com/project/114687/dashboard/482760)

### Insights
- [Checkout Conversion Funnel](https://eu.posthog.com/project/114687/insights/ia8SuqZe) - Track conversion from checkout started to completed
- [Hero CTA Click-through](https://eu.posthog.com/project/114687/insights/hEj2M1jG) - Track clicks on hero section CTAs by type
- [User Engagement Events](https://eu.posthog.com/project/114687/insights/LfwRG9CP) - Track product interactions, chat messages, and document views
- [Pricing Plan Interest](https://eu.posthog.com/project/114687/insights/aYwcMQJt) - Track which pricing plans users are clicking on
- [Contact & Newsletter Signups](https://eu.posthog.com/project/114687/insights/EH1ktmDJ) - Track lead generation events

## Environment Variables

The following environment variables are configured in `.env.local`:

```
NEXT_PUBLIC_POSTHOG_KEY=phc_kSrJzDXUeFSOADmQAOwjOTQahuqaULMdaj2R0Ta4vSe
NEXT_PUBLIC_POSTHOG_HOST=https://eu.i.posthog.com
```

Make sure to add these to your production environment as well.
