/**
 * SPDX-License-Identifier: Apache-2.0
 */
import { Mail, MessageCircle, Book, Github, HelpCircle } from "lucide-react";

export function Support() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <main className="container mx-auto px-4 sm:px-6 lg:px-8 py-24 max-w-4xl">
        <div className="prose prose-lg dark:prose-invert max-w-none">
          <h1 className="text-4xl sm:text-5xl font-extrabold mb-8 bg-gradient-to-r from-deepBlue to-teal bg-clip-text text-transparent">
            Support
          </h1>
          <p className="text-xl text-muted-foreground mb-12">
            Get help with SARAISE. We're here to assist you.
          </p>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-6">Get Support</h2>
            <div className="grid md:grid-cols-2 gap-6 mb-8">
              <div className="bg-card border border-border rounded-lg p-6">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-deepBlue/10 to-teal/10 flex items-center justify-center flex-shrink-0">
                    <Mail className="w-6 h-6 text-deepBlue" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold mb-2">Email Support</h3>
                    <p className="text-muted-foreground mb-2">
                      <a
                        href="mailto:info@buildworks.ai"
                        className="text-deepBlue hover:underline"
                      >
                        info@buildworks.ai
                      </a>
                    </p>
                    <p className="text-sm text-muted-foreground">
                      For general inquiries, support, and partnerships
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-card border border-border rounded-lg p-6">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-deepBlue/10 to-teal/10 flex items-center justify-center flex-shrink-0">
                    <MessageCircle className="w-6 h-6 text-deepBlue" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold mb-2">Community Support</h3>
                    <p className="text-muted-foreground mb-2">
                      <a
                        href="https://github.com/buildworksai/saraise.release/discussions"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-deepBlue hover:underline"
                      >
                        GitHub Discussions
                      </a>
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Join the community for questions and discussions
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-card border border-border rounded-lg p-6">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-deepBlue/10 to-teal/10 flex items-center justify-center flex-shrink-0">
                    <Book className="w-6 h-6 text-deepBlue" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold mb-2">Documentation</h3>
                    <p className="text-muted-foreground mb-2">
                      <a
                        href="https://github.com/buildworksai/saraise.release"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-deepBlue hover:underline"
                      >
                        Read the Documentation
                      </a>
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Comprehensive guides and API references
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-card border border-border rounded-lg p-6">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-deepBlue/10 to-teal/10 flex items-center justify-center flex-shrink-0">
                    <Github className="w-6 h-6 text-deepBlue" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold mb-2">Report Issues</h3>
                    <p className="text-muted-foreground mb-2">
                      <a
                        href="https://github.com/buildworksai/saraise.release/issues"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-deepBlue hover:underline"
                      >
                        GitHub Issues
                      </a>
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Report bugs and request features
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">Support by Purpose</h2>
            <div className="space-y-4">
              <div className="bg-card border border-border rounded-lg p-6">
                <h3 className="text-lg font-bold mb-2">General Inquiries</h3>
                <p className="text-muted-foreground mb-2">
                  <a
                    href="mailto:info@buildworks.ai"
                    className="text-deepBlue hover:underline"
                  >
                    info@buildworks.ai
                  </a>
                </p>
                <p className="text-sm text-muted-foreground">
                  Questions about SARAISE, features, licensing, or general
                  information
                </p>
              </div>

              <div className="bg-card border border-border rounded-lg p-6">
                <h3 className="text-lg font-bold mb-2">Security Issues</h3>
                <p className="text-muted-foreground mb-2">
                  <a
                    href="mailto:security@buildworks.ai"
                    className="text-deepBlue hover:underline"
                  >
                    security@buildworks.ai
                  </a>
                </p>
                <p className="text-sm text-muted-foreground">
                  Report security vulnerabilities or security-related concerns
                </p>
              </div>

              <div className="bg-card border border-border rounded-lg p-6">
                <h3 className="text-lg font-bold mb-2">Technical Support</h3>
                <p className="text-muted-foreground mb-2">
                  <a
                    href="mailto:support@buildworks.ai"
                    className="text-deepBlue hover:underline"
                  >
                    support@buildworks.ai
                  </a>
                </p>
                <p className="text-sm text-muted-foreground">
                  Technical assistance with installation, configuration, and
                  troubleshooting
                </p>
              </div>

              <div className="bg-card border border-border rounded-lg p-6">
                <h3 className="text-lg font-bold mb-2">Partnerships</h3>
                <p className="text-muted-foreground mb-2">
                  <a
                    href="mailto:partners@buildworks.ai"
                    className="text-deepBlue hover:underline"
                  >
                    partners@buildworks.ai
                  </a>
                </p>
                <p className="text-sm text-muted-foreground">
                  Partnership opportunities, integrations, and collaborations
                </p>
              </div>
            </div>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">Response Times</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              We aim to respond to all inquiries within:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>
                <strong>Security Issues:</strong> Within 48 hours
              </li>
              <li>
                <strong>General Inquiries:</strong> Within 3-5 business days
              </li>
              <li>
                <strong>Technical Support:</strong> Within 2-3 business days
              </li>
              <li>
                <strong>Partnership Inquiries:</strong> Within 5-7 business days
              </li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">Self-Hosted Support</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              For self-hosted instances, support is primarily community-driven:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>
                <strong>Community Forums:</strong> Get help from the community
                on GitHub Discussions
              </li>
              <li>
                <strong>Documentation:</strong> Comprehensive guides for
                installation, configuration, and troubleshooting
              </li>
              <li>
                <strong>Issue Tracking:</strong> Report bugs and request
                features on GitHub Issues
              </li>
              <li>
                <strong>Commercial Support:</strong> Available for enterprise
                customers (contact{" "}
                <a
                  href="mailto:info@buildworks.ai"
                  className="text-deepBlue hover:underline"
                >
                  info@buildworks.ai
                </a>
                )
              </li>
            </ul>
          </section>

          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-4">Contact Information</h2>
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
        </div>
      </main>
    </div>
  );
}
