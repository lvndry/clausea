"use client";

import { Header } from "@/components/clausea/Header";
import { Footer } from "@/components/clausea/PricingAndFooter";

export default function TermsOfServicePage() {
  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-secondary/30 w-full overflow-hidden">
      <Header />

      <main className="pt-32 pb-24 px-4 md:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="mb-12">
            <h1 className="text-5xl md:text-7xl font-display font-bold text-primary mb-6">
              Terms of Service
            </h1>
            <p className="text-muted-foreground text-lg">
              Last updated: January 2025
            </p>
          </div>

          <div className="prose prose-lg max-w-none space-y-8 text-foreground">
            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                1. Acceptance of Terms
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                By accessing or using Clausea AI (&ldquo;Service&rdquo;), you
                agree to be bound by these Terms of Service
                (&ldquo;Terms&rdquo;). If you disagree with
                any part of these Terms, you may not access or use the Service.
              </p>
              <p className="text-muted-foreground leading-relaxed">
                These Terms apply to all users of the Service, including
                individuals, businesses, and organizations. By creating an
                account or using our Service, you represent that you are at
                least 18 years old and have the legal capacity to enter into
                these Terms.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                2. Description of Service
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                Clausea AI provides an AI-powered legal document analysis
                platform that helps users understand, analyze, and compare legal
                documents such as privacy policies, terms of service, and
                contracts. Our Service includes:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>Document upload and processing</li>
                <li>AI-powered summarization and analysis</li>
                <li>Semantic search and clause comparison</li>
                <li>Risk assessment and compliance checking</li>
                <li>API access for developers (on applicable plans)</li>
              </ul>
              <p className="text-muted-foreground leading-relaxed mt-4">
                We reserve the right to modify, suspend, or discontinue any
                aspect of the Service at any time, with or without notice.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                3. User Accounts and Registration
              </h2>
              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                3.1 Account Creation
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                To use certain features of the Service, you must create an
                account. You agree to:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>Provide accurate, current, and complete information</li>
                <li>Maintain and update your account information</li>
                <li>Maintain the security of your account credentials</li>
                <li>
                  Accept responsibility for all activities under your account
                </li>
                <li>Notify us immediately of any unauthorized access</li>
              </ul>

              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                3.2 Account Termination
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                You may terminate your account at any time. We reserve the right
                to suspend or terminate your account if you violate these Terms
                or engage in fraudulent, abusive, or illegal activity.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                4. Acceptable Use
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                You agree to use the Service only for lawful purposes and in
                accordance with these Terms. You agree NOT to:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>
                  Upload documents containing malicious code, viruses, or
                  harmful software
                </li>
                <li>
                  Use the Service to violate any applicable laws or regulations
                </li>
                <li>
                  Attempt to reverse engineer, decompile, or extract the source
                  code of our Service
                </li>
                <li>
                  Use automated systems (bots, scrapers) to access the Service
                  without authorization
                </li>
                <li>
                  Interfere with or disrupt the Service or servers connected to
                  the Service
                </li>
                <li>
                  Upload documents that infringe on intellectual property rights
                  or contain confidential information you do not have permission
                  to process
                </li>
                <li>
                  Use the Service to generate false or misleading legal advice
                </li>
                <li>
                  Share your account credentials with others or create multiple
                  accounts to circumvent usage limits
                </li>
              </ul>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                5. Intellectual Property Rights
              </h2>
              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                5.1 Our Intellectual Property
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                The Service, including all content, features, functionality,
                algorithms, and technology, is owned by Clausea AI and protected
                by copyright, trademark, patent, and other intellectual property
                laws. You may not copy, modify, distribute, or create derivative
                works without our express written permission.
              </p>

              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                5.2 Your Content
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                You retain ownership of documents and content you upload to the
                Service. By uploading content, you grant us a limited,
                non-exclusive license to:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>
                  Process and analyze your documents to provide the Service
                </li>
                <li>
                  Store your documents temporarily as necessary for analysis
                </li>
                <li>
                  Generate analysis results and summaries based on your content
                </li>
              </ul>
              <p className="text-muted-foreground leading-relaxed mt-4">
                You represent and warrant that you have all necessary rights to
                upload and process the content you submit to the Service.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                6. Subscription Plans and Payments
              </h2>
              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                6.1 Subscription Tiers
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                We offer various subscription plans with different features and
                usage limits. Subscription fees are billed in advance on a
                monthly or annual basis, as selected. All fees are
                non-refundable except as required by law or as explicitly stated
                in our refund policy.
              </p>

              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                6.2 Payment Terms
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                You agree to provide current, complete, and accurate payment
                information. You authorize us to charge your payment method for
                all fees due. If payment fails, we may suspend or terminate your
                access to the Service.
              </p>

              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                6.3 Price Changes
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                We reserve the right to modify subscription prices. We will
                provide at least 30 days&apos; notice of any price changes. Your
                continued use of the Service after the price change constitutes
                acceptance of the new pricing.
              </p>

              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                6.4 Cancellation
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                You may cancel your subscription at any time. Cancellation takes
                effect at the end of your current billing period. You will
                continue to have access to paid features until the end of your
                billing period.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                7. Service Availability and Disclaimers
              </h2>
              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                7.1 Availability
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                We strive to provide reliable service but do not guarantee
                uninterrupted or error-free operation. The Service may be
                unavailable due to maintenance, updates, or circumstances beyond
                our control.
              </p>

              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                7.2 AI Analysis Disclaimer
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                Our AI-powered analysis is provided for informational purposes
                only and does not constitute legal advice. The Service is not a
                substitute for professional legal counsel. You should consult
                with qualified legal professionals for legal advice specific to
                your situation.
              </p>
              <p className="text-muted-foreground leading-relaxed mt-4">
                While we strive for accuracy, AI analysis may contain errors or
                omissions. We do not guarantee the accuracy, completeness, or
                reliability of any analysis provided by the Service.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                8. Limitation of Liability
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                TO THE MAXIMUM EXTENT PERMITTED BY LAW, CLAUSEA AI SHALL NOT BE
                LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR
                PUNITIVE DAMAGES, INCLUDING BUT NOT LIMITED TO LOSS OF PROFITS,
                DATA, OR USE, ARISING OUT OF OR RELATING TO YOUR USE OF THE
                SERVICE.
              </p>
              <p className="text-muted-foreground leading-relaxed mt-4">
                Our total liability for any claims arising from or related to
                the Service shall not exceed the amount you paid us in the 12
                months preceding the claim, or $100, whichever is greater.
              </p>
              <p className="text-muted-foreground leading-relaxed mt-4">
                Some jurisdictions do not allow the exclusion or limitation of
                certain damages, so the above limitations may not apply to you.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                9. Indemnification
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                You agree to indemnify, defend, and hold harmless Clausea AI and
                its officers, directors, employees, and agents from any claims,
                damages, losses, liabilities, and expenses (including
                attorneys&apos; fees) arising out of or relating to:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>Your use of the Service</li>
                <li>Your violation of these Terms</li>
                <li>Your violation of any third-party rights</li>
                <li>Content you upload or submit to the Service</li>
              </ul>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                10. Privacy
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                Your use of the Service is also governed by our Privacy Policy.
                Please review our Privacy Policy to understand how we collect,
                use, and protect your information.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                11. Modifications to Terms
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                We reserve the right to modify these Terms at any time. We will
                notify you of material changes by posting the updated Terms on
                this page and updating the &ldquo;Last updated&rdquo; date. Your
                continued
                use of the Service after such modifications constitutes
                acceptance of the updated Terms.
              </p>
              <p className="text-muted-foreground leading-relaxed mt-4">
                If you do not agree to the modified Terms, you must stop using
                the Service and may cancel your subscription.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                12. Governing Law and Dispute Resolution
              </h2>
              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                12.1 Governing Law
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                These Terms shall be governed by and construed in accordance
                with the laws of the State of California, United States, without
                regard to its conflict of law provisions.
              </p>

              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                12.2 Dispute Resolution
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                Any disputes arising out of or relating to these Terms or the
                Service shall be resolved through binding arbitration in
                accordance with the rules of the American Arbitration
                Association, except where prohibited by law. The arbitration
                shall take place in San Francisco, California.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                13. Severability
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                If any provision of these Terms is found to be unenforceable or
                invalid, that provision shall be limited or eliminated to the
                minimum extent necessary, and the remaining provisions shall
                remain in full force and effect.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                14. Entire Agreement
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                These Terms, together with our Privacy Policy, constitute the
                entire agreement between you and Clausea AI regarding the
                Service and supersede all prior agreements and understandings.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                15. Contact Information
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                If you have questions about these Terms, please contact us at:
              </p>
              <div className="bg-muted/30 p-6 rounded-2xl border border-border mt-4">
                <p className="text-foreground font-semibold mb-2">Clausea AI</p>
                <p className="text-muted-foreground">
                  Email:{" "}
                  <a
                    href="mailto:contact@clausea.co"
                    className="text-primary hover:underline"
                  >
                    contact@clausea.co
                  </a>
                </p>
                <p className="text-muted-foreground">
                  General inquiries:{" "}
                  <a
                    href="mailto:contact@clausea.co"
                    className="text-primary hover:underline"
                  >
                    contact@clausea.co
                  </a>
                </p>
              </div>
            </section>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
