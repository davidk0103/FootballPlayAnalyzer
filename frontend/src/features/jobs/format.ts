import type { Job, JobStatus } from '@/services/api'

export const STATUS_LABEL: Record<JobStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  retrying: 'Retrying',
  cancel_requested: 'Cancelling',
  succeeded: 'Succeeded',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

export const STATUS_FILTERS: readonly { value: JobStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'queued', label: 'Queued' },
  { value: 'running', label: 'Running' },
  { value: 'retrying', label: 'Retrying' },
  { value: 'cancel_requested', label: 'Cancelling' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
]

export function isJobStatus(value: string | null): value is JobStatus {
  return value !== null && value in STATUS_LABEL
}

const number = new Intl.NumberFormat('en-US')

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '—'
  const seconds = ms / 1000
  if (seconds < 1) return '<1s'
  if (seconds < 60) return `${Math.round(seconds)}s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  if (minutes < 60) return rest ? `${minutes}m ${rest}s` : `${minutes}m`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

export function jobDuration(job: Pick<Job, 'started_at' | 'finished_at'>, now: number): string {
  if (!job.started_at) return '—'
  const end = job.finished_at ? Date.parse(job.finished_at) : now
  return formatDuration(end - Date.parse(job.started_at))
}

export function formatRelative(iso: string, now: number): string {
  const diff = Math.round((now - Date.parse(iso)) / 1000)
  if (diff < 5) return 'just now'
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function jobSeason(job: Pick<Job, 'params'>): number | null {
  const season = job.params.season
  return typeof season === 'number' ? season : null
}

/** One-line, human description of where a job is and what it produced. */
export function jobSummary(job: Job, now: number): string {
  const attempt = `attempt ${Math.max(job.attempt_count, 1)} of ${job.max_attempts}`
  switch (job.status) {
    case 'queued':
      return 'Waiting for a worker'
    case 'running':
      return `Importing, ${attempt}`
    case 'retrying': {
      const due = job.next_retry_at ? Date.parse(job.next_retry_at) - now : 0
      const when = due > 1000 ? `in ${formatDuration(due)}` : 'shortly'
      return `Retrying ${when} after a temporary error (${attempt})`
    }
    case 'cancel_requested':
      return 'Stopping at the next checkpoint; changes will be rolled back'
    case 'cancelled':
      return 'Cancelled. No data was changed'
    case 'failed':
      return job.error ?? 'Failed'
    case 'succeeded': {
      const result = job.result ?? {}
      if (result.status === 'skipped_duplicate') {
        return 'Already up to date (same file checksum), nothing to import'
      }
      const stored = typeof result.stored === 'number' ? number.format(result.stored) : '?'
      const rejected = typeof result.rejected === 'number' ? result.rejected : 0
      return rejected
        ? `${stored} plays stored, ${number.format(rejected)} rows quarantined`
        : `${stored} plays stored`
    }
  }
}
