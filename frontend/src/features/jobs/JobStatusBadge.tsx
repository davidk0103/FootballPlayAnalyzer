import { Ban, CheckCircle2, Clock, Loader2, RotateCw, XCircle } from 'lucide-react'
import type { ComponentType } from 'react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { JobStatus } from '@/services/api'
import { STATUS_LABEL } from './format'

const STYLE: Record<JobStatus, { icon: ComponentType<{ className?: string }>; className: string }> =
  {
    queued: { icon: Clock, className: 'bg-muted text-muted-foreground' },
    running: {
      icon: Loader2,
      className: 'bg-sky-500/15 text-sky-700 dark:text-sky-300 [&>svg]:animate-spin',
    },
    retrying: { icon: RotateCw, className: 'bg-amber-500/15 text-amber-700 dark:text-amber-300' },
    cancel_requested: {
      icon: Loader2,
      className: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 [&>svg]:animate-spin',
    },
    succeeded: {
      icon: CheckCircle2,
      className: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
    },
    failed: { icon: XCircle, className: 'bg-destructive/10 text-destructive' },
    cancelled: { icon: Ban, className: 'border-border bg-transparent text-muted-foreground' },
  }

export function JobStatusBadge({ status, className }: { status: JobStatus; className?: string }) {
  const { icon: Icon, className: tone } = STYLE[status]
  return (
    <Badge className={cn(tone, className)} data-status={status}>
      <Icon aria-hidden="true" />
      {STATUS_LABEL[status]}
    </Badge>
  )
}
