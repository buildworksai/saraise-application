/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Beautiful reset password form with video background
 * Adapted from MVP with Phase 6 backend integration
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { LogoVideo } from '@/components/ui/logo-video'
import { PasswordField } from '@/components/auth/PasswordField'
import { AuthLegalFooter } from '@/components/auth/AuthLegalFooter'
import { ShieldCheck, Loader2, ArrowLeft } from 'lucide-react'
import { authService } from '@/services/auth-service'

export function ResetPasswordForm() {
  const location = useLocation()
  const navigate = useNavigate()
  const token = useMemo(() => new URLSearchParams(location.search).get('token'), [location.search])

  const [formData, setFormData] = useState({ password: '', confirmPassword: '' })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string | null>>({
    password: null,
    confirmPassword: null,
  })
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (!token) {
      setError('Reset link is missing or invalid.')
    }
  }, [token])

  const validateField = (field: 'password' | 'confirmPassword') => {
    const value = formData[field]
    let message: string | null = null

    if (field === 'password') {
      if (!value) message = 'Password is required'
      else if (value.length < 8) message = 'Password must be at least 8 characters long'
    } else {
      if (!value) message = 'Confirm your password'
      else if (value !== formData.password) message = 'Passwords do not match'
    }

    setFieldErrors((prev) => ({ ...prev, [field]: message }))
    return message
  }

  const validateAll = () => {
    const passwordError = validateField('password')
    const confirmError = validateField('confirmPassword')
    return passwordError ?? confirmError
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError(null)

    if (!token) {
      setError('Reset link is missing or invalid.')
      return
    }

    const hasErrors = validateAll()
    if (hasErrors) return

    setIsSubmitting(true)
    try {
      // Phase 6 backend integration
      await authService.resetPassword({
        token,
        new_password: formData.password,
      })
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to reset password at this time.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({ ...prev, [event.target.name]: event.target.value }))
    if (fieldErrors[event.target.name]) {
      validateField(event.target.name as 'password' | 'confirmPassword')
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
          <div className="max-w-xl space-y-4">
            <ShieldCheck className="h-11 w-11 text-emerald-300" />
            <h2 className="text-3xl font-semibold">Reset protected by zero-trust</h2>
            <p className="text-white/80">
              Tokens expire within minutes, sessions are revoked instantly, and every change is captured in the immutable audit log.
            </p>
          </div>
          <div className="mt-auto text-white/70 text-sm">
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
                  Set a new password
                </CardTitle>
                <CardDescription className="text-base">
                  Choose a strong password you haven't used before.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {success ? (
                <div className="text-center space-y-4 py-6">
                  <div className="mx-auto w-16 h-16 bg-green-100 dark:bg-green-900/20 rounded-full flex items-center justify-center">
                    <ShieldCheck className="w-8 h-8 text-green-600 dark:text-green-400" />
                  </div>
                  <p className="text-base">Your password has been updated successfully.</p>
                  <Button onClick={() => navigate('/login')} className="w-full h-11">
                    Return to login
                  </Button>
                </div>
              ) : (
                <form
                  onSubmit={(event) => {
                    void handleSubmit(event)
                  }}
                  className="space-y-5"
                  aria-busy={isSubmitting}
                >
                  <PasswordField
                    id="reset-password"
                    name="password"
                    label="New password"
                    placeholder="••••••••"
                    value={formData.password}
                    onChange={handleChange}
                    onBlur={() => validateField('password')}
                    error={fieldErrors.password}
                    helperText="Minimum 8 characters"
                    autoComplete="new-password"
                    disabled={isSubmitting || !token}
                  />

                  <PasswordField
                    id="reset-confirmPassword"
                    name="confirmPassword"
                    label="Confirm password"
                    placeholder="••••••••"
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    onBlur={() => validateField('confirmPassword')}
                    error={fieldErrors.confirmPassword}
                    helperText="Re-enter the same password"
                    autoComplete="new-password"
                    disabled={isSubmitting || !token}
                  />

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
                    disabled={isSubmitting || !token}
                    className="w-full h-11 text-base font-semibold shadow-lg hover:shadow-xl transition-all"
                    size="lg"
                  >
                    {isSubmitting ? (
                      <>
                        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                        Updating password...
                      </>
                    ) : (
                      <>
                        <ShieldCheck className="mr-2 h-5 w-5" />
                        Update password
                      </>
                    )}
                  </Button>

                  <div className="text-center">
                    <Link
                      to="/login"
                      className="text-sm font-semibold text-primary-main hover:text-primary-dark transition-colors inline-flex items-center gap-2"
                    >
                      <ArrowLeft className="h-4 w-4" />
                      Back to login
                    </Link>
                  </div>
                </form>
              )}
              <AuthLegalFooter />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
