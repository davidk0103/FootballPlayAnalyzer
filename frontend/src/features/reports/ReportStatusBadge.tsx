import { CheckCircle2, Loader2, XCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { ReportSummary } from '@/services/api'

const STYLE = {
  pending: { icon: Loader2, label: 'Generating', className: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 [&>svg]:animate-spin' },
  ready: { icon: CheckCircle2, label: 'Ready', className: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300' },
  failed: { icon: XCircle, label: 'Failed', className: 'bg-destructive/10 text-destructive' },
} as const

export function ReportStatusBadge({ status }: { status: ReportSummary['status'] }) {
  const { icon: Icon, label, className } = STYLE[status]
  return (
    <Badge className={className} data-status={status}>
      <Icon aria-hidden="true" />
      {label}
    </Badge>
  )
}
