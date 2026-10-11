import { zodResolver } from '@hookform/resolvers/zod'
import { LogIn, UserPlus } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuthMutation, useCurrentUser } from '@/hooks/useAuth'
import { safeNext } from '@/lib/navigation'
import { ApiError } from '@/services/api'

const MIN_PASSWORD = 10

const loginSchema = z.object({
  email: z.email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
})
const registerSchema = z.object({
  email: z.email('Enter a valid email address'),
  password: z
    .string()
    .min(MIN_PASSWORD, `Use at least ${MIN_PASSWORD} characters`)
    .max(128, 'Use at most 128 characters'),
})
type Values = z.infer<typeof loginSchema>

function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Unexpected error'
  if (error.status === 429) return 'Too many attempts. Wait a few minutes and try again.'
  return error.message
}

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const navigate = useNavigate()
  const me = useCurrentUser()
  const mutation = useAuthMutation(mode)
  const form = useForm<Values>({
    resolver: zodResolver(mode === 'login' ? loginSchema : registerSchema),
    defaultValues: { email: '', password: '' },
  })

  if (me.data) return <Navigate to={next} replace />

  const isLogin = mode === 'login'
  const errors = form.formState.errors
  const otherLink = `${isLogin ? '/register' : '/login'}${
    params.get('next') ? `?next=${encodeURIComponent(next)}` : ''
  }`

  return (
    <div className="mx-auto w-full max-w-sm py-8">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1 className="text-xl">{isLogin ? 'Sign in' : 'Create your account'}</h1>
          </CardTitle>
          <CardDescription>
            {isLogin
              ? 'Public analytics never need an account. Sign in for uploads and saved reports.'
              : 'An account keeps your uploaded datasets and saved reports private to you.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            noValidate
            className="flex flex-col gap-4"
            aria-label={isLogin ? 'Sign in' : 'Create account'}
            onSubmit={form.handleSubmit((values) =>
              mutation.mutate(values, { onSuccess: () => navigate(next, { replace: true }) }),
            )}
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="auth-email">Email</Label>
              <Input
                id="auth-email"
                type="email"
                autoComplete="email"
                aria-invalid={errors.email ? true : undefined}
                aria-describedby={errors.email ? 'auth-email-error' : undefined}
                {...form.register('email')}
              />
              {errors.email && (
                <p id="auth-email-error" className="text-xs text-destructive">
                  {errors.email.message}
                </p>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="auth-password">Password</Label>
              <Input
                id="auth-password"
                type="password"
                autoComplete={isLogin ? 'current-password' : 'new-password'}
                aria-invalid={errors.password ? true : undefined}
                aria-describedby="auth-password-help"
                {...form.register('password')}
              />
              <p
                id="auth-password-help"
                className={errors.password ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}
              >
                {errors.password?.message ??
                  (isLogin ? '\u00a0' : `At least ${MIN_PASSWORD} characters.`)}
              </p>
            </div>
            <Button type="submit" disabled={mutation.isPending}>
              {isLogin ? <LogIn aria-hidden="true" /> : <UserPlus aria-hidden="true" />}
              {mutation.isPending ? 'Please wait…' : isLogin ? 'Sign in' : 'Create account'}
            </Button>
            {mutation.isError && (
              <Alert variant="destructive" role="alert">
                <AlertTitle>{isLogin ? 'Could not sign in' : 'Could not create the account'}</AlertTitle>
                <AlertDescription>{errorMessage(mutation.error)}</AlertDescription>
              </Alert>
            )}
          </form>
          <p className="mt-6 text-center text-sm text-muted-foreground">
            {isLogin ? 'New to PlaybookIQ? ' : 'Already have an account? '}
            <Link to={otherLink} className="font-medium text-foreground underline underline-offset-2">
              {isLogin ? 'Create an account' : 'Sign in'}
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
