"use client";

import { Header } from "@/components/clausea/Header";
import { Footer } from "@/components/clausea/PricingAndFooter";

export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-secondary/30 w-full overflow-hidden">
      <Header />

      <main className="pt-32 pb-24 px-4 md:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="mb-12">
            <h1 className="text-5xl md:text-7xl font-display font-bold text-primary mb-6">
              Privacy Policy
            </h1>
            <p className="text-muted-foreground text-lg">
              Last updated: January 2025
            </p>
          </div>

          <div className="prose prose-lg max-w-none space-y-8 text-foreground">
            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                1. Introduction
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                Clausea AI (&ldquo;we,&rdquo; &ldquo;our,&rdquo; or
                &ldquo;us&rdquo;) is committed to protecting your privacy. This
                Privacy Policy explains how we collect, use, disclose, and
                safeguard your information when you use our service, including
                our website, API, and related services (collectively, the
                &ldquo;Service&rdquo;).
              </p>
              <p className="text-muted-foreground leading-relaxed">
                By using our Service, you agree to the collection and use of
                information in accordance with this policy. If you do not agree
                with our policies and practices, please do not use our Service.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                2. Information We Collect
              </h2>
              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                2.1 Information You Provide
              </h3>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>
                  <strong className="text-foreground">
                    Account Information:
                  </strong>{" "}
                  When you create an account, we collect your name, email
                  address, and password.
                </li>
                <li>
                  <strong className="text-foreground">Documents:</strong> We
                  process legal documents you upload to our Service for
                  analysis. Documents are processed securely and are not stored
                  longer than necessary for analysis.
                </li>
                <li>
                  <strong className="text-foreground">
                    Payment Information:
                  </strong>{" "}
                  For paid subscriptions, we collect billing information through
                  our secure payment processor. We do not store full credit card
                  details on our servers.
                </li>
                <li>
                  <strong className="text-foreground">Communications:</strong>{" "}
                  When you contact us, we collect the information you provide,
                  including your name, email, and message content.
                </li>
              </ul>

              <h3 className="text-2xl font-display font-semibold text-foreground mt-8 mb-4">
                2.2 Automatically Collected Information
              </h3>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>
                  <strong className="text-foreground">Usage Data:</strong> We
                  collect information about how you interact with our Service,
                  including pages visited, features used, and time spent on the
                  Service.
                </li>
                <li>
                  <strong className="text-foreground">
                    Device Information:
                  </strong>{" "}
                  We collect information about your device, including IP
                  address, browser type, operating system, and device
                  identifiers.
                </li>
                <li>
                  <strong className="text-foreground">
                    Cookies and Tracking:
                  </strong>{" "}
                  We use cookies and similar tracking technologies to enhance
                  your experience and analyze Service usage.
                </li>
              </ul>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                3. How We Use Your Information
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                We use the information we collect to:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>Provide, maintain, and improve our Service</li>
                <li>Process and analyze legal documents you upload</li>
                <li>Authenticate your account and process payments</li>
                <li>Send you service-related communications and updates</li>
                <li>Respond to your inquiries and provide customer support</li>
                <li>
                  Monitor and analyze usage patterns to improve our Service
                </li>
                <li>
                  Detect, prevent, and address technical issues and security
                  threats
                </li>
                <li>
                  Comply with legal obligations and enforce our Terms of Service
                </li>
              </ul>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                4. Information Sharing and Disclosure
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                We do not sell your personal information. We may share your
                information only in the following circumstances:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>
                  <strong className="text-foreground">
                    Service Providers:
                  </strong>{" "}
                  We may share information with third-party service providers
                  who perform services on our behalf, such as payment
                  processing, cloud hosting, and analytics. These providers are
                  contractually obligated to protect your information.
                </li>
                <li>
                  <strong className="text-foreground">
                    Legal Requirements:
                  </strong>{" "}
                  We may disclose information if required by law, court order,
                  or government regulation, or to protect our rights and safety.
                </li>
                <li>
                  <strong className="text-foreground">
                    Business Transfers:
                  </strong>{" "}
                  In the event of a merger, acquisition, or sale of assets, your
                  information may be transferred to the acquiring entity.
                </li>
                <li>
                  <strong className="text-foreground">
                    With Your Consent:
                  </strong>{" "}
                  We may share information with your explicit consent or at your
                  direction.
                </li>
              </ul>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                5. Data Security
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                We implement industry-standard security measures to protect your
                information, including:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>Encryption of data in transit and at rest</li>
                <li>Secure authentication and access controls</li>
                <li>Regular security assessments and updates</li>
                <li>
                  Limited access to personal information on a need-to-know basis
                </li>
                <li>
                  Automatic deletion of documents after analysis completion
                </li>
              </ul>
              <p className="text-muted-foreground leading-relaxed mt-4">
                However, no method of transmission over the Internet or
                electronic storage is 100% secure. While we strive to protect
                your information, we cannot guarantee absolute security.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                6. Your Rights and Choices
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                Depending on your location, you may have certain rights
                regarding your personal information:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>
                  <strong className="text-foreground">Access:</strong> Request
                  access to your personal information we hold
                </li>
                <li>
                  <strong className="text-foreground">Correction:</strong>{" "}
                  Request correction of inaccurate or incomplete information
                </li>
                <li>
                  <strong className="text-foreground">Deletion:</strong> Request
                  deletion of your personal information
                </li>
                <li>
                  <strong className="text-foreground">Portability:</strong>{" "}
                  Request transfer of your data to another service
                </li>
                <li>
                  <strong className="text-foreground">Opt-Out:</strong> Opt out
                  of certain data processing activities, such as marketing
                  communications
                </li>
              </ul>
              <p className="text-muted-foreground leading-relaxed mt-4">
                To exercise these rights, please contact us at{" "}
                <a
                  href="mailto:privacy@clausea.co"
                  className="text-primary hover:underline"
                >
                  privacy@clausea.co
                </a>
                . We will respond to your request within 30 days.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                7. Data Retention
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                We retain your personal information only for as long as
                necessary to fulfill the purposes outlined in this Privacy
                Policy, unless a longer retention period is required by law.
                Specifically:
              </p>
              <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
                <li>
                  <strong className="text-foreground">
                    Account Information:
                  </strong>{" "}
                  Retained while your account is active and for a reasonable
                  period after account closure
                </li>
                <li>
                  <strong className="text-foreground">Documents:</strong>{" "}
                  Deleted immediately after analysis completion, unless you
                  explicitly request storage
                </li>
                <li>
                  <strong className="text-foreground">Usage Data:</strong>{" "}
                  Retained for analytics purposes for up to 2 years
                </li>
                <li>
                  <strong className="text-foreground">Legal Records:</strong>{" "}
                  May be retained longer if required by law or for legal
                  proceedings
                </li>
              </ul>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                8. Children&apos;s Privacy
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                Our Service is not intended for individuals under the age of 18.
                We do not knowingly collect personal information from children.
                If you believe we have collected information from a child,
                please contact us immediately, and we will delete such
                information.

              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                9. International Data Transfers
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                Your information may be transferred to and processed in
                countries other than your country of residence. These countries
                may have different data protection laws. We ensure appropriate
                safeguards are in place to protect your information in
                accordance with this Privacy Policy.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                10. Changes to This Privacy Policy
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                We may update this Privacy Policy from time to time. We will
                notify you of any material changes by posting the new Privacy
                Policy on this page and updating the &ldquo;Last updated&rdquo;
                date. We
                encourage you to review this Privacy Policy periodically.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-3xl font-display font-bold text-primary mt-12 mb-6">
                11. Contact Us
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                If you have questions or concerns about this Privacy Policy or
                our data practices, please contact us at:
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
