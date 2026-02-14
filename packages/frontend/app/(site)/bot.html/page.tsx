"use client";

import { Header } from "@/components/clausea/Header";
import { Footer } from "@/components/clausea/PricingAndFooter";

export default function BotPage() {
  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-secondary/30 w-full overflow-hidden">
      <Header />

      <main className="pt-32 pb-24 px-4 md:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="mb-12">
            <h1 className="text-5xl md:text-7xl font-display font-bold text-primary mb-6">
              ClauseaBot Information
            </h1>
            <p className="text-muted-foreground text-lg">
              Information for web crawlers and site administrators
            </p>
          </div>

          <div className="prose prose-lg max-w-none space-y-8 text-foreground">
            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                About ClauseaBot
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                ClauseaBot is a legal document discovery crawler operated by
                Clausea AI. Our bot crawls websites to discover and analyze
                legal documents such as privacy policies, terms of service, and
                other legal agreements to help users understand what
                they&apos;re agreeing to.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                What We Do
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                ClauseaBot is designed to:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>
                  Discover legal documents (privacy policies, terms of service,
                  etc.) on websites
                </li>
                <li>
                  Analyze and extract key information from legal documents
                </li>
                <li>
                  Help users understand complex legal agreements in plain
                  language
                </li>
                <li>
                  Provide compliance analysis and risk assessment for legal
                  documents
                </li>
              </ul>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                Bot Behavior
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                ClauseaBot:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>
                  Respects robots.txt directives and follows crawl-delay
                  instructions
                </li>
                <li>
                  Uses standard HTTP caching headers (ETag, Last-Modified) to
                  minimize bandwidth usage
                </li>
                <li>
                  Focuses on legal document pages and policy-related content
                </li>
                <li>
                  Operates with reasonable rate limits to avoid overloading
                  servers
                </li>
                <li>
                  Identifies itself with the User-Agent:{" "}
                  <code className="bg-muted px-2 py-1 rounded text-sm">
                    Mozilla/5.0 (compatible; ClauseaBot/2.0;
                    +https://www.clausea.co/bot.html; lvndry@proton.me)
                  </code>
                </li>
              </ul>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                Blocking ClauseaBot
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                If you wish to block ClauseaBot from crawling your website, you
                can add the following to your robots.txt file:
              </p>
              <div className="bg-muted/30 p-6 rounded-2xl border border-border mt-4">
                <pre className="text-foreground font-mono text-sm whitespace-pre-wrap">
                  {`User-agent: ClauseaBot
Disallow: /`}
                </pre>
              </div>
              <p className="text-muted-foreground leading-relaxed mt-4">
                Or to block only specific paths:
              </p>
              <div className="bg-muted/30 p-6 rounded-2xl border border-border mt-4">
                <pre className="text-foreground font-mono text-sm whitespace-pre-wrap">
                  {`User-agent: ClauseaBot
Disallow: /private/
Disallow: /admin/`}
                </pre>
              </div>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                Contact Information
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                If you have questions, concerns, or need assistance regarding
                ClauseaBot, please contact us:
              </p>
              <div className="bg-muted/30 p-6 rounded-2xl border border-border mt-4">
                <p className="text-foreground font-semibold mb-2">Clausea AI</p>
                <p className="text-muted-foreground">
                  Email:{" "}
                  <a
                    href="mailto:lvndry@proton.me"
                    className="text-primary hover:underline"
                  >
                    lvndry@proton.me
                  </a>
                </p>
                <p className="text-muted-foreground mt-2">
                  Website:{" "}
                  <a
                    href="https://www.clausea.co"
                    className="text-primary hover:underline"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    https://www.clausea.co
                  </a>
                </p>
              </div>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                Compliance
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                ClauseaBot is designed to be a good web citizen:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>Follows robots.txt directives</li>
                <li>Respects crawl-delay settings</li>
                <li>Uses appropriate rate limiting</li>
                <li>Implements HTTP caching to reduce server load</li>
                <li>Identifies itself clearly in User-Agent header</li>
                <li>Provides this information page for transparency</li>
              </ul>
            </section>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
