import { LogOut } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { useCurrentUser, useLogout } from '@/hooks/useAuth'

export function UserMenu() {
  const me = useCurrentUser()
  const logout = useLogout()
  const navigate = useNavigate()

  if (me.isPending) return <span className="h-8 w-20" aria-hidden="true" />
  if (!me.data) {
    return (
      <Link to="/login" className={buttonVariants({ variant: 'outline', size: 'sm' })}>
        Sign in
      </Link>
    )
  }
  return (
    <div className="flex items-center gap-2">
      <span className="hidden max-w-48 truncate text-sm text-muted-foreground md:inline" title={me.data.email}>
        {me.data.email}
      </span>
      {me.data.is_admin && <Badge variant="secondary">Admin</Badge>}
      <Button
        variant="ghost"
        size="sm"
        disabled={logout.isPending}
        onClick={() => logout.mutate(false, { onSettled: () => navigate('/') })}
      >
        <LogOut aria-hidden="true" /> Sign out
      </Button>
    </div>
  )
}
