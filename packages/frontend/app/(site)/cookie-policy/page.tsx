import type { Metadata } from "next";

import { Header } from "@/components/clausea/Header";
import { Footer } from "@/components/clausea/PricingAndFooter";

export const metadata: Metadata = {
  title: "Cookie Policy | Clausea AI",
  description:
    "How Clausea AI uses cookies and similar technologies, and how you can control them.",
};

export default function CookiePolicyPage() {
  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-secondary/30 w-full overflow-hidden">
      <Header />

      <main className="pt-32 pb-24 px-4 md:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="mb-12">
            <h1 className="text-5xl md:text-7xl font-display font-bold text-primary mb-6">
              Cookie Policy
            </h1>
            <p className="text-muted-foreground text-lg">
              Last updated: June 2026
            </p>
          </div>

          <div className="prose prose-lg max-w-none space-y-8 text-foreground">
            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                1. What are cookies?
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                Cookies are small text files placed on your device when you
                visit a website. They are widely used to make websites work, to
                remember your preferences, and to provide information to the
                site owners. We also use similar technologies such as local
                storage and pixels; in this policy we refer to all of them as
                &ldquo;cookies.&rdquo;
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                2. How we use cookies
              </h2>
              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                2.1 Strictly necessary
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                These cookies are required for the Service to function and
                cannot be switched off. They include cookies set during
                authentication and session management by our identity provider,
                Clerk, so that you can sign in and stay signed in securely.
              </p>
              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                2.2 Analytics
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                We use PostHog to understand how the Service is used so we can
                improve it. These cookies help us measure page views, feature
                usage, and aggregate trends. The information is used in
                aggregate and helps us prioritize improvements.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                3. Third-party cookies
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                Some cookies are set by third parties that provide services on
                our behalf, including Clerk (authentication) and PostHog
                (product analytics). These providers process data according to
                their own privacy and cookie policies.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                4. Managing cookies
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                Most browsers let you refuse or delete cookies through their
                settings. Blocking strictly necessary cookies may prevent parts
                of the Service, such as signing in, from working correctly. You
                can also opt out of analytics tracking via your browser&rsquo;s
                Do Not Track setting where supported.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                5. Changes to this policy
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                We may update this Cookie Policy from time to time. When we do,
                we will revise the &ldquo;Last updated&rdquo; date above.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                6. Contact
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                Questions about our use of cookies can be sent to{" "}
                <a
                  href="mailto:privacy@clausea.co"
                  className="text-foreground underline underline-offset-4"
                >
                  privacy@clausea.co
                </a>
                .
              </p>
            </section>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
