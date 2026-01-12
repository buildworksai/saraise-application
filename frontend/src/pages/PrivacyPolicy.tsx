/**
 * SPDX-License-Identifier: Apache-2.0
 */
export function PrivacyPolicy() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <main className="container mx-auto px-4 sm:px-6 lg:px-8 py-24 max-w-4xl">
        <div className="prose prose-lg dark:prose-invert max-w-none">
          <h1 className="text-4xl sm:text-5xl font-extrabold mb-8 bg-gradient-to-r from-deepBlue to-teal bg-clip-text text-transparent">
            Privacy Policy
          </h1>
          <p className="text-muted-foreground mb-8">
            Last Updated: January 2025
          </p>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">1. Introduction</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              BuildFlow Consultancy Private Limited ("we," "our," or "us")
              operates SARAISE, an open-source ERP software platform. This
              Privacy Policy explains how we collect, use, disclose, and
              safeguard your information when you use our website and services.
            </p>
            <p className="text-muted-foreground leading-relaxed">
              SARAISE is licensed under Apache 2.0, and this privacy policy
              applies to our website, documentation, and any cloud-hosted
              services we may provide.
            </p>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              2. Information We Collect
            </h2>
            <h3 className="text-xl font-semibold mb-3">
              2.1 Information You Provide
            </h3>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>
                Contact information (name, email address) when you contact us or
                subscribe to updates
              </li>
              <li>
                GitHub account information if you contribute to the project
              </li>
              <li>Feedback, bug reports, and feature requests</li>
            </ul>

            <h3 className="text-xl font-semibold mb-3 mt-6">
              2.2 Automatically Collected Information
            </h3>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>
                Website usage data (pages visited, time spent, referring URLs)
              </li>
              <li>Browser type, device information, and IP address</li>
              <li>
                Cookies and similar tracking technologies (see Cookie Policy
                below)
              </li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              3. How We Use Your Information
            </h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              We use collected information to:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>Provide, maintain, and improve our website and services</li>
              <li>Respond to your inquiries and provide customer support</li>
              <li>Send you updates about SARAISE (with your consent)</li>
              <li>Analyze website usage to improve user experience</li>
              <li>Comply with legal obligations and protect our rights</li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              4. Data Sharing and Disclosure
            </h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              We do not sell your personal information. We may share information
              only in the following circumstances:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>
                <strong>Service Providers:</strong> With trusted third-party
                service providers who assist in website operations
              </li>
              <li>
                <strong>Legal Requirements:</strong> When required by law, court
                order, or government regulation
              </li>
              <li>
                <strong>Public Contributions:</strong> GitHub contributions are
                publicly visible per GitHub's terms
              </li>
              <li>
                <strong>Business Transfers:</strong> In connection with a
                merger, acquisition, or sale of assets
              </li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              5. Self-Hosted Instances
            </h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              When you self-host SARAISE, you are responsible for:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>
                Data collection, storage, and processing within your
                infrastructure
              </li>
              <li>
                Compliance with applicable data protection laws (GDPR, CCPA,
                etc.)
              </li>
              <li>Implementing appropriate security measures</li>
              <li>Managing user data and privacy within your organization</li>
            </ul>
            <p className="text-muted-foreground leading-relaxed mt-4">
              We do not access or process data from self-hosted instances unless
              you explicitly request support.
            </p>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              6. Cookies and Tracking Technologies
            </h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              We use cookies and similar technologies to:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>Remember your preferences (theme, language)</li>
              <li>Analyze website traffic and usage patterns</li>
              <li>Improve website functionality</li>
            </ul>
            <p className="text-muted-foreground leading-relaxed mt-4">
              You can control cookies through your browser settings. Note that
              disabling cookies may affect website functionality.
            </p>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">7. Data Security</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              We implement appropriate technical and organizational measures to
              protect your information, including:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>Encryption of data in transit (HTTPS/TLS)</li>
              <li>Secure hosting infrastructure</li>
              <li>Regular security assessments</li>
              <li>Access controls and authentication</li>
            </ul>
            <p className="text-muted-foreground leading-relaxed mt-4">
              However, no method of transmission over the Internet is 100%
              secure. While we strive to protect your data, we cannot guarantee
              absolute security.
            </p>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">8. Your Rights</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              Depending on your jurisdiction, you may have the following rights:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>
                <strong>Access:</strong> Request access to your personal
                information
              </li>
              <li>
                <strong>Correction:</strong> Request correction of inaccurate
                data
              </li>
              <li>
                <strong>Deletion:</strong> Request deletion of your personal
                information
              </li>
              <li>
                <strong>Portability:</strong> Request transfer of your data
              </li>
              <li>
                <strong>Objection:</strong> Object to processing of your
                personal information
              </li>
              <li>
                <strong>Withdrawal:</strong> Withdraw consent where processing
                is based on consent
              </li>
            </ul>
            <p className="text-muted-foreground leading-relaxed mt-4">
              To exercise these rights, contact us at{" "}
              <a
                href="mailto:info@buildworks.ai"
                className="text-deepBlue hover:underline"
              >
                info@buildworks.ai
              </a>
              .
            </p>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">9. Children's Privacy</h2>
            <p className="text-muted-foreground leading-relaxed">
              Our services are not directed to individuals under 18 years of
              age. We do not knowingly collect personal information from
              children. If you believe we have collected information from a
              child, please contact us immediately.
            </p>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              10. International Data Transfers
            </h2>
            <p className="text-muted-foreground leading-relaxed">
              Your information may be transferred to and processed in countries
              other than your country of residence. We ensure appropriate
              safeguards are in place to protect your information in accordance
              with this Privacy Policy and applicable data protection laws.
            </p>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              11. Changes to This Privacy Policy
            </h2>
            <p className="text-muted-foreground leading-relaxed">
              We may update this Privacy Policy from time to time. We will
              notify you of any material changes by posting the new Privacy
              Policy on this page and updating the "Last Updated" date. You are
              advised to review this Privacy Policy periodically.
            </p>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">12. Contact Us</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              If you have questions about this Privacy Policy, please contact
              us:
            </p>
            <div className="bg-card border border-border rounded-lg p-6">
              <p className="text-muted-foreground mb-2">
                <strong>Email:</strong>{" "}
                <a
                  href="mailto:info@buildworks.ai"
                  className="text-deepBlue hover:underline"
                >
                  info@buildworks.ai
                </a>
              </p>
              <p className="text-muted-foreground mb-2">
                <strong>Company:</strong> BuildFlow Consultancy Private Limited
              </p>
              <p className="text-muted-foreground mb-2">
                <strong>CIN:</strong> U62099TS2025PTC201319
              </p>
              <p className="text-muted-foreground">
                <strong>Address:</strong> Hafeez Pet, Miyapur, Hyderabad-
                500049, Telangana, India
              </p>
            </div>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">13. Compliance</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              This Privacy Policy is designed to comply with:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>
                General Data Protection Regulation (GDPR) - European Union
              </li>
              <li>California Consumer Privacy Act (CCPA) - United States</li>
              <li>
                Information Technology Act, 2000 and Information Technology
                (Reasonable Security Practices and Procedures and Sensitive
                Personal Data or Information) Rules, 2011 - India
              </li>
              <li>
                Other applicable data protection laws in jurisdictions where we
                operate
              </li>
            </ul>
          </section>
        </div>
      </main>
    </div>
  );
}
