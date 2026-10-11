import { CheckCircle2, CircleDot, FileCheck2, Loader2, XCircle } from 'lucide-react'
import type { ComponentType } from 'react'
import { Badge } from '@/components/ui/badge'
import type { UploadStatus } from '@/services/api'

const UPLOAD_STATUS_LABEL: Record<UploadStatus, string> = {
  uploaded: 'Needs mapping',
  validated: 'Ready to process',
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
}

const STYLE: Record<UploadStatus, { icon: ComponentType<{ className?: string }>; className: string }> = {
  uploaded: { icon: CircleDot, className: 'bg-muted text-muted-foreground' },
  validated: { icon: FileCheck2, className: 'bg-sky-500/15 text-sky-700 dark:text-sky-300' },
  processing: { icon: Loader2, className: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 [&>svg]:animate-spin' },
  ready: { icon: CheckCircle2, className: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300' },
  failed: { icon: XCircle, className: 'bg-destructive/10 text-destructive' },
}

export function UploadStatusBadge({ status }: { status: UploadStatus }) {
  const { icon: Icon, className } = STYLE[status]
  return (
    <Badge className={className} data-status={status}>
      <Icon aria-hidden="true" />
      {UPLOAD_STATUS_LABEL[status]}
    </Badge>
  )
}
