import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { useCurrentUser } from '@/hooks/useAuth'

export function RequireAuth({ children }: { children: ReactNode }) {
  const me = useCurrentUser()
  const location = useLocation()
  if (me.isPending) return <Skeleton className="h-96" aria-label="Checking your session" />
  if (me.isError) return <ErrorState error={me.error} onRetry={() => void me.refetch()} />
  if (!me.data) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return children
}
