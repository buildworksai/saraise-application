/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Beautiful split-screen registration form with video background
 * Adapted from MVP with Phase 6 backend integration
 */
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/Card";
import {
  UserPlus,
  Loader2,
  CheckCircle2,
  Sparkles,
  Shield,
  Zap,
} from "lucide-react";
import { LogoVideo } from "@/components/ui/logo-video";
import { PasswordField } from "@/components/auth/PasswordField";
import { AuthLegalFooter } from "@/components/auth/AuthLegalFooter";
import { authService } from "@/services/auth-service";
import { useAuthStore } from "@/stores/auth-store";

export function RegisterForm() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
    confirmPassword: "",
    organizationName: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const highlights = [
    {
      icon: Sparkles,
      title: "AI-powered workflows",
      description:
        "Design, deploy, and monitor automations without writing code.",
    },
    {
      icon: Shield,
      title: "Enterprise-grade security",
      description:
        "Multi-tenant isolation, zero-trust policies, and immutable audit trails.",
    },
    {
      icon: Zap,
      title: "Instant tenant readiness",
      description:
        "Provision environments, billing, and governance in minutes.",
    },
  ];
  const [fieldErrors, setFieldErrors] = useState<Record<string, string | null>>(
    {
      name: null,
      email: null,
      password: null,
      confirmPassword: null,
      organizationName: null,
    }
  );

  const validators = {
    name: () => (!formData.name.trim() ? "Name is required" : null),
    email: () => {
      if (!formData.email.trim()) return "Email is required";
      const isValidEmail = /\S+@\S+\.\S+/.test(formData.email.trim());
      if (!isValidEmail) return "Please enter a valid email address";
      return null;
    },
    organizationName: () =>
      !formData.organizationName.trim()
        ? "Organization Name is required"
        : null,
    password: () => {
      if (!formData.password) return "Password is required";
      if (formData.password.length < 8)
        return "Password must be at least 8 characters long";
      return null;
    },
    confirmPassword: () => {
      if (!formData.confirmPassword) return "Confirm your password";
      if (formData.password !== formData.confirmPassword)
        return "Passwords do not match";
      return null;
    },
  } as const;

  const validateField = (field: keyof typeof fieldErrors) => {
    const validator = validators[field as keyof typeof validators];
    if (!validator) return null;
    const message = validator();
    setFieldErrors((prev) => ({ ...prev, [field]: message }));
    return message;
  };

  const validateAllFields = () => {
    const results: Record<string, string | null> = {};
    const validatorKeys: (keyof typeof validators)[] = [
      "name",
      "email",
      "organizationName",
      "password",
      "confirmPassword",
    ];
    validatorKeys.forEach((field) => {
      const validator = validators[field];
      if (validator) {
        results[field] = validator();
      }
    });
    setFieldErrors(results);
    return Object.values(results).some(Boolean);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    setError(null);

    if ((validators as Record<string, () => string | null>)[e.target.name]) {
      validateField(e.target.name as keyof typeof validators);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setError(null);

    const hasErrors = validateAllFields();
    if (hasErrors) return;

    setIsLoading(true);

    try {
      // Phase 6 backend integration
      const response = await authService.register({
        name: formData.name.trim(),
        email: formData.email.trim(),
        password: formData.password,
        company_name: formData.organizationName.trim(),
      });

      // Update auth store (auto-login after registration)
      const { setUser, setAuthenticated } = useAuthStore.getState();
      setUser(response.user);
      setAuthenticated(true);

      setSuccess(true);
      // Redirect after 2 seconds
      // ⚠️ ARCHITECTURAL ENFORCEMENT: Application repo is tenant-only
      setTimeout(() => {
        if (response.user.tenant_role) {
          navigate("/tenant/dashboard", { replace: true });
        } else {
          navigate("/ai-agents", { replace: true });
        }
      }, 2000);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Registration failed";
      setError(errorMessage);
      // Error already handled via setError
    } finally {
      setIsLoading(false);
    }
  };

  if (success) {
    return (
      <div className="h-screen flex overflow-hidden">
        {/* Left Panel - Logo and Branding */}
        <div className="hidden lg:flex lg:w-1/2 bg-[#040818] flex-col justify-center relative overflow-hidden h-full">
          <LogoVideo
            background
            autoplay
            loop
            className="opacity-100 brightness-[1.15] contrast-[1.15] saturate-[1.2]"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[#040818]/15 to-[#040818]/70 pointer-events-none" />
          <div className="absolute inset-0 opacity-5 z-[1]">
            <div
              className="absolute inset-0"
              style={{
                backgroundImage: `radial-gradient(circle at 2px 2px, rgba(255,255,255,0.3) 1px, transparent 0)`,
                backgroundSize: "60px 60px",
              }}
            />
          </div>
          <div className="relative z-10 text-center px-8 lg:px-12">
            <div className="text-white/80 text-[11px] uppercase tracking-[0.4em] mb-6">
              SARAISE
            </div>
            <div className="mx-auto w-16 h-16 lg:w-20 lg:h-20 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center mb-4 lg:mb-6">
              <CheckCircle2 className="w-8 h-8 lg:w-10 lg:h-10 text-white" />
            </div>
            <h2 className="text-2xl lg:text-3xl font-bold text-white mb-3 lg:mb-4">
              Welcome to SARAISE!
            </h2>
            <p className="text-white/90 text-base lg:text-lg">
              Your organization has been created successfully
            </p>
          </div>
        </div>

        {/* Right Panel - Success Message */}
        <div className="w-full lg:w-1/2 flex items-center justify-center p-4 sm:p-8 bg-background h-full overflow-y-auto">
          <div className="w-full max-w-md animate-fade-in my-auto">
            <Card className="shadow-xl border-0">
              <CardHeader className="space-y-4 text-center pb-6">
                <div className="mx-auto w-16 h-16 bg-green-500/10 dark:bg-green-400/10 rounded-full flex items-center justify-center">
                  <CheckCircle2 className="w-8 h-8 text-green-600 dark:text-green-400" />
                </div>
                <CardTitle className="text-2xl font-bold">
                  Organization Created!
                </CardTitle>
                <CardDescription className="text-base">
                  Your account is ready. Redirecting...
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex overflow-hidden">
      {/* Left Panel - Logo and Branding */}
      <div className="hidden lg:flex lg:w-1/2 bg-[#040818] flex-col relative overflow-hidden h-full">
        <LogoVideo
          background
          autoplay
          loop
          className="opacity-100 brightness-[1.15] contrast-[1.15] saturate-[1.2]"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[#040818]/15 to-[#040818]/70 pointer-events-none" />
        {/* Background Pattern */}
        <div className="absolute inset-0 opacity-5 z-[1]">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `radial-gradient(circle at 2px 2px, rgba(255,255,255,0.3) 1px, transparent 0)`,
              backgroundSize: "60px 60px",
            }}
          />
        </div>

        <div className="relative z-10 flex flex-col h-full overflow-y-auto px-8 lg:px-12 py-12">
          <div className="absolute -top-10 -right-10 w-72 h-72 bg-primary-main/25 blur-3xl rounded-full animate-pulse pointer-events-none" />
          <div className="space-y-8 text-white max-w-xl">
            <p className="text-[11px] uppercase tracking-[0.4em] text-white/70">
              AI Symphony ERP
            </p>
            <div className="space-y-3">
              <h2 className="text-3xl font-semibold">
                Transform operations with AI-driven precision.
              </h2>
              <p className="text-white/80">
                Activate no-code workflows, multi-tenant governance, and
                enterprise automation from a single control plane.
              </p>
            </div>
            <ul className="space-y-4">
              {highlights.map((feature) => (
                <li key={feature.title} className="flex gap-4">
                  <feature.icon
                    className="h-5 w-5 text-primary-main"
                    aria-hidden="true"
                  />
                  <div>
                    <p className="font-semibold">{feature.title}</p>
                    <p className="text-sm text-white/75">
                      {feature.description}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <div className="mt-auto text-sm text-white/70">
            Trusted by global operators, startups, and regulated enterprises.
          </div>
        </div>
      </div>

      {/* Right Panel - Registration Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-4 sm:p-8 bg-background h-full overflow-y-auto">
        <div className="w-full max-w-md animate-fade-in my-auto">
          <Card className="shadow-xl border-0">
            <CardHeader className="space-y-4 pb-6">
              {/* Mobile Logo */}
              <div className="lg:hidden flex justify-center mb-4">
                <LogoVideo width={180} showText={true} autoplay loop />
              </div>

              <div className="space-y-2 text-center lg:text-left">
                <CardTitle className="text-3xl font-bold bg-gradient-to-r from-primary-main to-primary-dark bg-clip-text text-transparent">
                  Create Organization
                </CardTitle>
                <CardDescription className="text-base">
                  Set up your organization and admin account
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <form
                onSubmit={(event) => {
                  void handleSubmit(event);
                }}
                className="space-y-5"
                aria-busy={isLoading}
              >
                <div className="space-y-2">
                  <Label htmlFor="name" className="text-sm font-semibold">
                    Full Name
                  </Label>
                  <Input
                    id="name"
                    name="name"
                    type="text"
                    placeholder="John Doe"
                    value={formData.name}
                    onChange={handleChange}
                    required
                    autoComplete="name"
                    className="h-11"
                    disabled={isLoading}
                    aria-invalid={fieldErrors.name ? "true" : "false"}
                    aria-describedby="register-name-helper register-name-error"
                    onBlur={() => validateField("name")}
                  />
                  <p
                    id="register-name-helper"
                    className="text-xs text-muted-foreground"
                  >
                    This appears on approvals and audit logs.
                  </p>
                  {fieldErrors.name && (
                    <p
                      id="register-name-error"
                      className="text-xs text-destructive"
                      role="alert"
                    >
                      {fieldErrors.name}
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="email" className="text-sm font-semibold">
                    Email Address
                  </Label>
                  <Input
                    id="email"
                    name="email"
                    type="email"
                    placeholder="you@example.com"
                    value={formData.email}
                    onChange={handleChange}
                    required
                    autoComplete="email"
                    className="h-11"
                    disabled={isLoading}
                    aria-invalid={fieldErrors.email ? "true" : "false"}
                    aria-describedby="register-email-helper register-email-error"
                    onBlur={() => validateField("email")}
                  />
                  <p
                    id="register-email-helper"
                    className="text-xs text-muted-foreground"
                  >
                    Use the email you want associated with your workspace.
                  </p>
                  {fieldErrors.email && (
                    <p
                      id="register-email-error"
                      className="text-xs text-destructive"
                      role="alert"
                    >
                      {fieldErrors.email}
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label
                    htmlFor="organizationName"
                    className="text-sm font-semibold"
                  >
                    Organization Name
                  </Label>
                  <Input
                    id="organizationName"
                    name="organizationName"
                    type="text"
                    placeholder="Acme Corp"
                    value={formData.organizationName}
                    onChange={handleChange}
                    required
                    autoComplete="organization"
                    className="h-11"
                    disabled={isLoading}
                    aria-invalid={
                      fieldErrors.organizationName ? "true" : "false"
                    }
                    onBlur={() => validateField("organizationName")}
                  />
                  {fieldErrors.organizationName && (
                    <p
                      id="register-org-error"
                      className="text-xs text-destructive"
                      role="alert"
                    >
                      {fieldErrors.organizationName}
                    </p>
                  )}
                </div>

                <PasswordField
                  id="password"
                  name="password"
                  label="Password"
                  placeholder="••••••••"
                  value={formData.password}
                  onChange={handleChange}
                  onBlur={() => validateField("password")}
                  error={fieldErrors.password}
                  helperText="Must be at least 8 characters long"
                  autoComplete="new-password"
                  disabled={isLoading}
                />

                <PasswordField
                  id="confirmPassword"
                  name="confirmPassword"
                  label="Confirm Password"
                  placeholder="••••••••"
                  value={formData.confirmPassword}
                  onChange={handleChange}
                  onBlur={() => validateField("confirmPassword")}
                  error={fieldErrors.confirmPassword}
                  helperText="Re-enter your password to confirm"
                  autoComplete="new-password"
                  disabled={isLoading}
                />

                {error && (
                  <div
                    className="bg-destructive/10 border border-destructive/20 text-destructive px-4 py-3 rounded-md text-sm animate-fade-in"
                    role="alert"
                    aria-live="assertive"
                  >
                    {error}
                  </div>
                )}

                <Button
                  type="submit"
                  disabled={isLoading}
                  className="w-full h-11 text-base font-semibold shadow-lg hover:shadow-xl transition-all"
                  size="lg"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                      Creating organization...
                    </>
                  ) : (
                    <>
                      <UserPlus className="mr-2 h-5 w-5" />
                      Create Organization
                    </>
                  )}
                </Button>
              </form>

              {/* Login link */}
              <div className="mt-6 text-center">
                <p className="text-sm text-muted-foreground">
                  Already have access?{" "}
                  <Link
                    to="/login"
                    className="font-semibold text-primary-main hover:text-primary-dark transition-colors"
                  >
                    Sign in
                  </Link>
                </p>
              </div>

              <AuthLegalFooter />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
