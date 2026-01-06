/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Beautiful forgot password form with video background
 * Adapted from MVP with Phase 6 backend integration
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Button } from '@/components/ui/Button'
import { LogoVideo } from '@/components/ui/logo-video'
import { AuthLegalFooter } from '@/components/auth/AuthLegalFooter'
import { Send, CheckCircle2, Loader2 } from 'lucide-react'
import { authService } from '@/services/auth-service'

export function ForgotPasswordForm() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError(null)

    if (!email.trim()) {
      setError('Email is required')
      return
    }

    setIsSubmitting(true)
    try {
      // Phase 6 backend integration
      await authService.forgotPassword({ email: email.trim() })
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to process your request right now.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="h-screen flex overflow-hidden">
      <div className="hidden lg:flex lg:w-1/2 bg-[#040818] flex-col relative overflow-hidden h-full">
        <LogoVideo background autoplay loop className="opacity-100 brightness-[1.15] contrast-[1.15] saturate-[1.2]" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[#040818]/15 to-[#040818]/70 pointer-events-none" />
        <div className="absolute inset-0 opacity-5 z-[1]">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `radial-gradient(circle at 2px 2px, rgba(255,255,255,0.3) 1px, transparent 0)`,
              backgroundSize: '60px 60px',
            }}
          />
        </div>
        <div className="relative z-10 flex flex-col h-full px-8 lg:px-12 py-12 text-white">
          <div className="max-w-xl">
            <h2 className="text-3xl font-semibold mb-4">Enterprise-grade security</h2>
            <p className="text-white/80">
              Password resets are protected with short-lived tokens, session revocation, and audit logging to keep your tenant secure.
            </p>
          </div>
          <div className="mt-auto space-y-3 text-white/70 text-sm">
            <p>SARAISE – Secure and Reliable AI Symphony ERP</p>
          </div>
        </div>
      </div>

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
                  Forgot password?
                </CardTitle>
                <CardDescription className="text-base">
                  Enter your email address and we'll send you a secure reset link.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {success ? (
                <div className="text-center space-y-4 py-6">
                  <div className="mx-auto w-16 h-16 bg-green-100 dark:bg-green-900/20 rounded-full flex items-center justify-center">
                    <CheckCircle2 className="w-8 h-8 text-green-600 dark:text-green-400" />
                  </div>
                  <p className="text-base">
                    {`If an account exists for ${email}, a reset link is on its way. Check your inbox (and spam folder).`}
                  </p>
                  <Link
                    to="/login"
                    className="font-semibold text-primary-main hover:text-primary-dark transition-colors"
                  >
                    Back to login
                  </Link>
                </div>
              ) : (
                <form
                  onSubmit={(event) => {
                    void handleSubmit(event)
                  }}
                  className="space-y-5"
                  aria-busy={isSubmitting}
                >
                  <div className="space-y-2">
                    <Label htmlFor="reset-email" className="text-sm font-semibold">
                      Email Address
                    </Label>
                    <Input
                      id="reset-email"
                      type="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      required
                      autoComplete="email"
                      className="h-11"
                      disabled={isSubmitting}
                      aria-invalid={error ? 'true' : 'false'}
                    />
                    <p className="text-xs text-muted-foreground">
                      We'll never share your email. Reset links expire after 15 minutes.
                    </p>
                  </div>

                  {error && (
                    <div
                      className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 px-4 py-3 rounded-md text-sm"
                      role="alert"
                      aria-live="assertive"
                    >
                      {error}
                    </div>
                  )}

                  <Button
                    type="submit"
                    disabled={isSubmitting}
                    className="w-full h-11 text-base font-semibold shadow-lg hover:shadow-xl transition-all"
                    size="lg"
                  >
                    {isSubmitting ? (
                      <>
                        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                        Sending link...
                      </>
                    ) : (
                      <>
                        <Send className="mr-2 h-5 w-5" />
                        Email me a reset link
                      </>
                    )}
                  </Button>
                </form>
              )}

              <div className="mt-6 text-center">
                <p className="text-sm text-muted-foreground">
                  Remembered your password?{' '}
                  <Link to="/login" className="font-semibold text-primary-main hover:text-primary-dark transition-colors">
                    Return to sign in
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
