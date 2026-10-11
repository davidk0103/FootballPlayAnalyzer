import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress'
import type { Job } from '@/services/api'
import { JobStatusBadge } from './JobStatusBadge'

const STAGE_LABEL: Record<string, string> = {
  reading: 'Reading the file',
  validating: 'Checking rows',
  storing: 'Saving plays',
}

interface JobProgressData {
  stage?: string
  done?: number
  total?: number
}

/** Status plus a determinate bar when the worker has reported progress, indeterminate otherwise. */
export function JobProgress({ job, label = 'Processing' }: { job: Job; label?: string }) {
  const p = (job.progress ?? {}) as JobProgressData
  const pct = p.total && p.total > 0 && p.done !== undefined ? Math.min(100, Math.round((p.done / p.total) * 100)) : null
  return (
    <div className="flex flex-col gap-2" aria-live="polite">
      <div className="flex items-center gap-2 text-sm">
        <JobStatusBadge status={job.status} />
        {job.attempt_count > 1 && (
          <span className="text-muted-foreground">
            Attempt {job.attempt_count} of {job.max_attempts}
          </span>
        )}
      </div>
      <Progress value={job.status === 'queued' ? null : pct}>
        <ProgressLabel>{p.stage ? (STAGE_LABEL[p.stage] ?? p.stage) : job.status === 'queued' ? 'Waiting for a worker' : label}</ProgressLabel>
        <ProgressValue>
          {() =>
            pct === null
              ? ''
              : `${pct}%${p.total ? ` · ${(p.done ?? 0).toLocaleString()} / ${p.total.toLocaleString()} rows` : ''}`
          }
        </ProgressValue>
      </Progress>
      {job.error && <p className="text-sm text-destructive">{job.error}</p>}
    </div>
  )
}
