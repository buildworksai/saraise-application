/**
 * SPDX-License-Identifier: Apache-2.0
 */
import { Shield, Lock, Key, AlertTriangle } from "lucide-react";

const securityFeatures = [
  {
    icon: Shield,
    title: "Security Architecture",
    description: "Multi-layered security with defense in depth principles",
  },
  {
    icon: Lock,
    title: "Encryption",
    description: "Data encrypted in transit (TLS 1.3) and at rest (AES-256)",
  },
  {
    icon: Key,
    title: "Access Control",
    description: "Role-based access control (RBAC) with granular permissions",
  },
  {
    icon: AlertTriangle,
    title: "Vulnerability Management",
    description: "Regular security assessments and prompt patch deployment",
  },
];

export function Security() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <main className="container mx-auto px-4 sm:px-6 lg:px-8 py-24 max-w-4xl">
        <div className="prose prose-lg dark:prose-invert max-w-none">
          <h1 className="text-4xl sm:text-5xl font-extrabold mb-8 bg-gradient-to-r from-deepBlue to-teal bg-clip-text text-transparent">
            Security Policy
          </h1>
          <p className="text-muted-foreground mb-8">
            Last Updated: January 2025
          </p>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">1. Security Commitment</h2>
            <p className="text-muted-foreground leading-relaxed">
              BuildFlow Consultancy Private Limited is committed to maintaining
              the security and integrity of SARAISE. We implement
              industry-standard security practices and continuously improve our
              security posture to protect our users and their data.
            </p>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-6">2. Security Features</h2>
            <div className="grid md:grid-cols-2 gap-6 mb-8">
              {securityFeatures.map((feature) => {
                const Icon = feature.icon;
                return (
                  <div
                    key={feature.title}
                    className="bg-card border border-border rounded-lg p-6"
                  >
                    <div className="flex items-start gap-4">
                      <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-deepBlue/10 to-teal/10 flex items-center justify-center flex-shrink-0">
                        <Icon className="w-6 h-6 text-deepBlue" />
                      </div>
                      <div>
                        <h3 className="text-lg font-bold mb-2">
                          {feature.title}
                        </h3>
                        <p className="text-sm text-muted-foreground">
                          {feature.description}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">3. Security Practices</h2>
            <h3 className="text-xl font-semibold mb-3">3.1 Code Security</h3>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground mb-4">
              <li>Regular code reviews and security audits</li>
              <li>Static code analysis and vulnerability scanning</li>
              <li>Dependency management and security updates</li>
              <li>Secure coding practices and training</li>
            </ul>

            <h3 className="text-xl font-semibold mb-3 mt-6">
              3.2 Infrastructure Security
            </h3>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground mb-4">
              <li>Secure hosting infrastructure with regular updates</li>
              <li>Network segmentation and firewall protection</li>
              <li>Intrusion detection and monitoring systems</li>
              <li>Regular security assessments and penetration testing</li>
            </ul>

            <h3 className="text-xl font-semibold mb-3 mt-6">
              3.3 Data Protection
            </h3>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>Encryption of data in transit (TLS 1.3)</li>
              <li>Encryption of data at rest (AES-256)</li>
              <li>Regular backups with encryption</li>
              <li>Data retention and deletion policies</li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              4. Authentication and Access Control
            </h2>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>
                <strong>Session-Based Authentication:</strong> Secure HTTP-only
                cookies with Redis session storage
              </li>
              <li>
                <strong>Role-Based Access Control (RBAC):</strong> Granular
                permissions for platform and tenant roles
              </li>
              <li>
                <strong>Multi-Factor Authentication (MFA):</strong> TOTP-based
                step-up authentication for sensitive operations
              </li>
              <li>
                <strong>Single Sign-On (SSO):</strong> SAML/OIDC integration
                with Azure AD, Google Workspace, Okta
              </li>
              <li>
                <strong>Audit Logging:</strong> Immutable audit trails for all
                sensitive operations
              </li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              5. Vulnerability Disclosure
            </h2>
            <h3 className="text-xl font-semibold mb-3">
              5.1 Responsible Disclosure
            </h3>
            <p className="text-muted-foreground leading-relaxed mb-4">
              We encourage responsible disclosure of security vulnerabilities.
              If you discover a security vulnerability, please follow these
              guidelines:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground mb-4">
              <li>
                Email security details to{" "}
                <a
                  href="mailto:security@buildworks.ai"
                  className="text-deepBlue hover:underline"
                >
                  security@buildworks.ai
                </a>
              </li>
              <li>
                Do not publicly disclose the vulnerability until we have
                addressed it
              </li>
              <li>
                Provide detailed information about the vulnerability and
                potential impact
              </li>
              <li>
                Allow us reasonable time to fix the issue before disclosure
              </li>
            </ul>

            <h3 className="text-xl font-semibold mb-3 mt-6">
              5.2 Response Timeline
            </h3>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>
                <strong>Initial Response:</strong> Within 48 hours of report
                receipt
              </li>
              <li>
                <strong>Assessment:</strong> Within 7 days to confirm and assess
                severity
              </li>
              <li>
                <strong>Fix Timeline:</strong> Based on severity (Critical: 7
                days, High: 30 days, Medium: 90 days)
              </li>
              <li>
                <strong>Disclosure:</strong> After fix is deployed and tested
              </li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">6. Security Updates</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              We regularly release security updates to address vulnerabilities
              and improve security. We recommend:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>Subscribing to security advisories on GitHub</li>
              <li>Keeping your SARAISE installation up to date</li>
              <li>Applying security patches promptly</li>
              <li>Monitoring security announcements</li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              7. Compliance and Certifications
            </h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              SARAISE is designed with compliance in mind:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>
                <strong>SOC 2 Aligned:</strong> Security controls aligned with
                SOC 2 Type II framework
              </li>
              <li>
                <strong>GDPR Compliant:</strong> Data protection measures
                aligned with GDPR requirements
              </li>
              <li>
                <strong>ISO 27001 Principles:</strong> Information security
                management best practices
              </li>
              <li>
                <strong>OWASP Top 10:</strong> Protection against common web
                application vulnerabilities
              </li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">8. Self-Hosted Security</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              When self-hosting SARAISE, you are responsible for:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>Implementing and maintaining security controls</li>
              <li>Regular security updates and patch management</li>
              <li>Network security and firewall configuration</li>
              <li>Access control and user management</li>
              <li>Backup and disaster recovery procedures</li>
              <li>Security monitoring and incident response</li>
            </ul>
            <p className="text-muted-foreground leading-relaxed mt-4">
              We provide security best practices documentation, but ultimate
              responsibility for security in self-hosted instances lies with
              you.
            </p>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">9. Incident Response</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              In the event of a security incident, we will:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>Immediately investigate and contain the incident</li>
              <li>Assess the impact and scope of the incident</li>
              <li>Notify affected users as required by law</li>
              <li>Remediate vulnerabilities and prevent recurrence</li>
              <li>Provide post-incident analysis and improvements</li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              10. Security Best Practices for Users
            </h2>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>Use strong, unique passwords</li>
              <li>Enable multi-factor authentication (MFA) when available</li>
              <li>Keep your installation and dependencies up to date</li>
              <li>Regularly review and audit user access permissions</li>
              <li>Monitor audit logs for suspicious activity</li>
              <li>Implement network security controls (firewalls, VPNs)</li>
              <li>Regularly backup your data</li>
              <li>Follow principle of least privilege for user access</li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">
              11. Contact Security Team
            </h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              For security-related inquiries or to report vulnerabilities:
            </p>
            <div className="bg-card border border-border rounded-lg p-6">
              <p className="text-muted-foreground mb-2">
                <strong>Security Email:</strong>{" "}
                <a
                  href="mailto:security@buildworks.ai"
                  className="text-deepBlue hover:underline"
                >
                  security@buildworks.ai
                </a>
              </p>
              <p className="text-muted-foreground mb-2">
                <strong>General Contact:</strong>{" "}
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
        </div>
      </main>
    </div>
  );
}
