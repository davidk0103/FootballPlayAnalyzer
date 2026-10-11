import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { api, type JobAttempt } from '@/services/api'
import { formatDuration } from './format'

const ATTEMPT_LABEL: Record<JobAttempt['status'], string> = {
  running: 'Running',
  succeeded: 'Succeeded',
  failed: 'Failed',
  cancelled: 'Cancelled',
  lost: 'Worker lost',
}

const ATTEMPT_DOT: Record<JobAttempt['status'], string> = {
  running: 'bg-sky-500 animate-pulse',
  succeeded: 'bg-emerald-500',
  failed: 'bg-destructive',
  cancelled: 'bg-muted-foreground',
  lost: 'bg-amber-500',
}

export function JobAttempts({ jobId, active, now }: { jobId: string; active: boolean; now: number }) {
  const query = useQuery({
    // Keyed on `active` so the final state is fetched once when the job finishes, even if
    // it finished between two polls.
    queryKey: ['jobs', jobId, 'attempts', active],
    queryFn: () => api.jobAttempts(jobId),
    placeholderData: keepPreviousData,
    refetchInterval: active ? 1500 : false,
  })

  if (query.isPending) return <Skeleton className="h-16" aria-label="Loading attempts" />
  if (query.isError) {
    return <ErrorState title="Could not load attempts" error={query.error} onRetry={() => void query.refetch()} />
  }
  if (query.data.length === 0) {
    return <p className="text-sm text-muted-foreground">No attempts yet. The job is waiting for a worker.</p>
  }

  return (
    <ol className="flex flex-col gap-3" aria-label="Attempts">
      {query.data.map((attempt) => {
        const end = attempt.finished_at ? Date.parse(attempt.finished_at) : now
        return (
          <li key={attempt.attempt_number} className="flex gap-3">
            <span
              className={cn('mt-1.5 size-2 shrink-0 rounded-full', ATTEMPT_DOT[attempt.status])}
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1 text-sm">
              <p className="font-medium">
                Attempt {attempt.attempt_number}: {ATTEMPT_LABEL[attempt.status]}
                <span className="ml-2 font-normal text-muted-foreground">
                  {formatDuration(end - Date.parse(attempt.started_at))}
                </span>
              </p>
              {attempt.error && (
                <p className="mt-0.5 break-words text-muted-foreground">
                  <span className="font-mono text-xs">{attempt.error_type}</span> {attempt.error}
                </p>
              )}
              {attempt.retry_delay_seconds !== null && (
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Retried after {attempt.retry_delay_seconds.toFixed(1)}s backoff
                </p>
              )}
              {attempt.worker && (
                <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground" title={attempt.worker}>
                  {attempt.worker}
                </p>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
