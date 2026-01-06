/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Beautiful split-screen login form with video background
 * Adapted from MVP with Phase 6 backend integration
 */
import { AuthLegalFooter } from '@/components/auth/AuthLegalFooter'
import { PasswordField } from '@/components/auth/PasswordField'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { LogoVideo } from '@/components/ui/logo-video'
import { authService } from '@/services/auth-service'
import { useAuthStore } from '@/stores/auth-store'
import { Loader2, LogIn, Shield, Sparkles, Users } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

export function LoginForm() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [emailError, setEmailError] = useState<string | null>(null)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [emailTouched, setEmailTouched] = useState(false)
  const [passwordTouched, setPasswordTouched] = useState(false)
  
  const loginHighlights = [
    { icon: Sparkles, text: 'AI-native orchestration across ERP workflows' },
    { icon: Shield, text: 'SOC 2-ready controls and tenant isolation' },
    { icon: Users, text: 'Trusted by global operators & disruptive MSMEs' },
  ]

  const computeEmailError = (emailValue?: string) => {
    const value = emailValue ?? email
    if (!value.trim()) return 'Email is required'
    const isValidEmail = /\S+@\S+\.\S+/.test(value.trim())
    if (!isValidEmail) return 'Please enter a valid email address'
    return null
  }

  const computePasswordError = (passwordValue?: string) => {
    const value = passwordValue ?? password
    if (!value) return 'Password is required'
    return null
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    e.stopPropagation()

    // Mark fields as touched
    setEmailTouched(true)
    setPasswordTouched(true)

    const currentEmailError = computeEmailError()
    const currentPasswordError = computePasswordError()
    setEmailError(currentEmailError)
    setPasswordError(currentPasswordError)

    if (currentEmailError || currentPasswordError) {
      // Focus first field with error
      if (currentEmailError) {
        document.getElementById('email')?.focus()
      } else if (currentPasswordError) {
        document.getElementById('password')?.focus()
      }
      return
    }

    setError(null)
    setIsLoading(true)

    try {
      // Phase 6 backend integration
      const response = await authService.login({ email: email.trim(), password })
      
      // Update auth store
      const { setUser, setAuthenticated } = useAuthStore.getState()
      setUser(response.user)
      setAuthenticated(true)

      // Navigate based on roles
      if (response.user.platform_role === 'platform_owner') {
        navigate('/platform/dashboard', { replace: true })
      } else if (response.user.tenant_role) {
        navigate('/ai-agents', { replace: true })
      } else {
        navigate('/', { replace: true })
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Invalid email or password'
      setError(errorMessage)
      console.error('Login error:', err)
      // Focus password field on error for better UX
      document.getElementById('password')?.focus()
    } finally {
      setIsLoading(false)
    }
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
              backgroundSize: '60px 60px',
            }}
          />
        </div>

        {/* Minimal caption only – avoid overlapping the hero logo */}
        <div className="relative z-10 flex flex-col h-full px-8 lg:px-12 py-8 text-white">
          <div className="mt-auto text-xs text-white/60 uppercase tracking-[0.3em]">
            Trusted by MSMEs &amp; Global Enterprises
          </div>
        </div>
      </div>

      {/* Right Panel - Login Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-4 sm:p-8 bg-background h-full overflow-y-auto">
        <div className="w-full max-w-md animate-fade-in my-auto">
          {/* Value props panel (moved from left hero to avoid overlap) */}
          <div className="mb-6 space-y-2">
            <p className="text-[11px] uppercase tracking-[0.4em] text-muted-foreground">
              AI Symphony Control Tower
            </p>
            <h2 className="text-lg font-semibold text-foreground">
              Transform operations with AI-driven precision.
            </h2>
            <ul className="space-y-1 text-xs text-muted-foreground">
              {loginHighlights.map((item) => (
                <li key={item.text} className="flex items-center gap-2">
                  <item.icon className="h-3.5 w-3.5 text-primary-main" aria-hidden="true" />
                  {item.text}
                </li>
              ))}
            </ul>
          </div>

          <Card className="shadow-xl border-0">
            <CardHeader className="space-y-4 pb-6">
              {/* Mobile Logo */}
              <div className="lg:hidden flex justify-center mb-4">
                <LogoVideo width={180} showText={true} className="text-white" autoplay loop />
              </div>

              <div className="space-y-2 text-center lg:text-left">
                <CardTitle className="text-3xl font-bold bg-gradient-to-r from-primary-main to-primary-dark bg-clip-text text-transparent">
                  Welcome Back
                </CardTitle>
                <CardDescription className="text-base">
                  Sign in to your SARAISE account
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <form
                onSubmit={(event) => {
                  void handleSubmit(event)
                }}
                className="space-y-5"
                aria-busy={isLoading}
                noValidate
              >
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-sm font-semibold">
                    Email Address
                  </Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => {
                      const newValue = e.target.value
                      setEmail(newValue)
                      if (emailTouched) {
                        setEmailError(computeEmailError(newValue))
                      }
                    }}
                    autoComplete="email"
                    className="h-11"
                    disabled={isLoading}
                    aria-invalid={emailError ? 'true' : 'false'}
                    aria-describedby={emailError ? 'login-email-error' : 'login-email-helper'}
                    onBlur={() => {
                      setEmailTouched(true)
                      setEmailError(computeEmailError())
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !emailError && email.trim()) {
                        document.getElementById('password')?.focus()
                      }
                    }}
                    autoFocus
                  />
                  {!emailError && (
                    <p id="login-email-helper" className="text-xs text-muted-foreground">
                      Use your work email to sign in.
                    </p>
                  )}
                  {emailError && emailTouched && (
                    <p
                      id="login-email-error"
                      className="text-xs text-red-600 dark:text-red-400 font-medium"
                      role="alert"
                      aria-live="polite"
                    >
                      {emailError}
                    </p>
                  )}
                </div>
                <PasswordField
                  id="password"
                  label="Password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => {
                    const newValue = e.target.value
                    setPassword(newValue)
                    if (passwordTouched) {
                      setPasswordError(computePasswordError(newValue))
                    }
                  }}
                  onBlur={() => {
                    setPasswordTouched(true)
                    setPasswordError(computePasswordError())
                  }}
                  error={passwordTouched ? passwordError : null}
                  helperText={!passwordError ? "Enter your password" : undefined}
                  autoComplete="current-password"
                  disabled={isLoading}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !passwordError && password && !isLoading) {
                      void handleSubmit(e as unknown as React.FormEvent)
                    }
                  }}
                />
                <div className="text-right text-sm">
                  <Link
                    to="/forgot-password"
                    className="font-semibold text-primary-main hover:text-primary-dark transition-colors"
                  >
                    Forgot password?
                  </Link>
                </div>
                {error && (
                  <div
                    className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 px-4 py-3 rounded-md text-sm animate-fade-in"
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
                      Signing in...
                    </>
                  ) : (
                    <>
                      <LogIn className="mr-2 h-5 w-5" />
                      Sign In
                    </>
                  )}
                </Button>
              </form>

              {/* Register link */}
              <div className="mt-6 text-center">
                <p className="text-sm text-muted-foreground">
                  Don't have an account?{' '}
                  <Link
                    to="/register"
                    className="font-semibold text-primary-main hover:text-primary-dark transition-colors"
                  >
                    Create an account
                  </Link>
                </p>
              </div>

              <AuthLegalFooter />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
