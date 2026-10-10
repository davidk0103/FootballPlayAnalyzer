import { ChevronDown, CircleSlash, Database, Gauge } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Skeleton } from '@/components/ui/skeleton'
import { ImportJobForm } from '@/features/jobs/ImportJobForm'
import { JobAttempts } from '@/features/jobs/JobAttempts'
import { JobStatusBadge } from '@/features/jobs/JobStatusBadge'
import {
  formatRelative,
  isJobStatus,
  jobDuration,
  jobSeason,
  jobSummary,
  STATUS_FILTERS,
} from '@/features/jobs/format'
import { useCacheStats, useCancelJob, useJob, useJobs, useNow } from '@/hooks/useJobs'
import { cn } from '@/lib/utils'
import { isActiveJob, type Job } from '@/services/api'

export function JobsPage() {
  const [params, setParams] = useSearchParams()
  const rawStatus = params.get('status')
  const status = isJobStatus(rawStatus) ? rawStatus : null
  const selectedId = params.get('job')

  const jobs = useJobs(status)
  const anyActive = jobs.data?.items.some(isActiveJob) ?? false
  const now = useNow(anyActive)

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === '') next.delete(key)
      else next.set(key, value)
    }
    setParams(next, { replace: true })
  }

  const selectedOffList =
    selectedId !== null && jobs.data && !jobs.data.items.some((j) => j.id === selectedId)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Import jobs</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Season imports run in the background on Celery workers. Failed attempts retry with
          backoff, crashed workers are recovered automatically, and analytics caches refresh
          when an import finishes.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Start an import</CardTitle>
              <CardDescription>Downloads nflverse play-by-play for one season.</CardDescription>
            </CardHeader>
            <CardContent>
              <ImportJobForm onShowJob={(id) => update({ job: id, status: null })} />
            </CardContent>
          </Card>
          <CacheStatsCard />
        </div>

        <Card className="min-w-0">
          <CardHeader className="flex flex-row flex-wrap items-end justify-between gap-3">
            <div>
              <CardTitle>Recent jobs</CardTitle>
              <CardDescription aria-live="polite">
                {jobs.data
                  ? `${jobs.data.total} job${jobs.data.total === 1 ? '' : 's'}${
                      anyActive ? ' · updating live' : ''
                    }`
                  : 'Loading…'}
              </CardDescription>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="job-status-filter" className="sr-only">
                Filter by status
              </Label>
              <NativeSelect
                id="job-status-filter"
                size="sm"
                value={status ?? ''}
                onChange={(e) => update({ status: e.target.value })}
              >
                {STATUS_FILTERS.map((f) => (
                  <NativeSelectOption key={f.value} value={f.value}>
                    {f.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
          </CardHeader>
          <CardContent>
            {selectedOffList && (
              <div className="mb-4">
                <SelectedJob id={selectedId} now={now} onClose={() => update({ job: null })} />
              </div>
            )}
            {jobs.isPending ? (
              <div className="flex flex-col gap-2" aria-label="Loading jobs">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-16" />
                ))}
              </div>
            ) : jobs.isError ? (
              <ErrorState
                title="Could not load jobs"
                error={jobs.error}
                onRetry={() => void jobs.refetch()}
              />
            ) : jobs.data.items.length === 0 ? (
              <EmptyState title={status ? 'No jobs with this status' : 'No import jobs yet'}>
                {status
                  ? 'Try another status filter.'
                  : 'Queue a season on the left. It will show up here and update live while it runs.'}
              </EmptyState>
            ) : (
              <ul className="flex flex-col divide-y rounded-lg border" aria-label="Jobs">
                {jobs.data.items.map((job) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    now={now}
                    expanded={job.id === selectedId}
                    onToggle={() => update({ job: job.id === selectedId ? null : job.id })}
                  />
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function JobRow({
  job,
  now,
  expanded,
  onToggle,
}: {
  job: Job
  now: number
  expanded: boolean
  onToggle: () => void
}) {
  const season = jobSeason(job)
  const forced = job.params.force === true
  return (
    <li data-testid="job-row" data-job-id={job.id}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="grid w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-4 py-3 text-left transition-colors hover:bg-muted/50 sm:grid-cols-[10rem_7.5rem_minmax(0,1fr)_4rem_auto]"
      >
        <span className="font-medium tabular-nums">
          {season ?? '—'} season
          {forced && <span className="ml-1 text-xs font-normal text-muted-foreground">(forced)</span>}
        </span>
        <span className="justify-self-end sm:justify-self-start">
          <JobStatusBadge status={job.status} />
        </span>
        <span
          className={cn(
            'col-span-2 truncate text-sm sm:col-span-1',
            job.status === 'failed' ? 'text-destructive' : 'text-muted-foreground',
          )}
          title={jobSummary(job, now)}
        >
          {jobSummary(job, now)}
        </span>
        <span className="text-xs tabular-nums text-muted-foreground sm:text-sm">
          {jobDuration(job, now)}
        </span>
        <span className="flex items-center gap-2 justify-self-end text-xs text-muted-foreground">
          {formatRelative(job.created_at, now)}
          <ChevronDown
            aria-hidden="true"
            className={cn('size-4 transition-transform', expanded && 'rotate-180')}
          />
        </span>
      </button>
      {expanded && (
        <div className="border-t bg-muted/30 px-4 py-4">
          <JobDetail job={job} now={now} />
        </div>
      )}
    </li>
  )
}

function SelectedJob({ id, now, onClose }: { id: string; now: number; onClose: () => void }) {
  const job = useJob(id)
  if (job.isPending) return <Skeleton className="h-24" aria-label="Loading job" />
  if (job.isError) return <ErrorState title="Could not load this job" error={job.error} />
  return (
    <div className="rounded-lg border bg-muted/30 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-sm font-medium">
          {jobSeason(job.data)} season <JobStatusBadge status={job.data.status} className="ml-2" />
        </p>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
      <JobDetail job={job.data} now={now} />
    </div>
  )
}

function JobDetail({ job, now }: { job: Job; now: number }) {
  const cancel = useCancelJob()
  const active = isActiveJob(job)
  const canCancel = active && job.status !== 'cancel_requested'
  const facts: [string, string][] = [
    ['Job ID', job.id],
    ['Attempts', `${job.attempt_count} of ${job.max_attempts}`],
    ['Time limit', `${Math.round(job.timeout_seconds / 60)} min`],
    ['Queued', new Date(job.created_at).toLocaleString()],
  ]
  if (job.finished_at) facts.push(['Finished', new Date(job.finished_at).toLocaleString()])
  if (job.heartbeat_at && active) facts.push(['Last heartbeat', formatRelative(job.heartbeat_at, now)])

  return (
    <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="flex flex-col gap-4">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          {facts.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="truncate font-mono text-xs leading-5" title={value}>
                {value}
              </dd>
            </div>
          ))}
        </dl>
        {job.status === 'succeeded' && job.result && <ResultFacts result={job.result} />}
        {job.error && job.status !== 'succeeded' && (
          <Alert variant={job.status === 'failed' ? 'destructive' : 'default'}>
            <AlertDescription className="break-words">{job.error}</AlertDescription>
          </Alert>
        )}
        {canCancel && (
          <div className="flex flex-col gap-2">
            <Button
              variant="outline"
              size="sm"
              className="self-start"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate(job.id)}
            >
              <CircleSlash aria-hidden="true" />
              {cancel.isPending ? 'Cancelling…' : 'Cancel job'}
            </Button>
            <p className="text-xs text-muted-foreground">
              {job.status === 'running'
                ? 'The worker stops at its next checkpoint and rolls back, so nothing is half-imported.'
                : 'The job has not started work, so it is cancelled immediately.'}
            </p>
            {cancel.isError && (
              <p role="alert" className="text-xs text-destructive">
                {cancel.error.message}
              </p>
            )}
          </div>
        )}
      </div>
      <div>
        <h3 className="mb-3 text-sm font-medium">Attempt history</h3>
        <JobAttempts jobId={job.id} active={active} now={now} />
      </div>
    </div>
  )
}

const number = new Intl.NumberFormat('en-US')

function ResultFacts({ result }: { result: Record<string, unknown> }) {
  const rows: [string, unknown][] = [
    ['Outcome', result.status === 'skipped_duplicate' ? 'Skipped (unchanged file)' : 'Imported'],
    ['Plays stored', result.stored],
    ['Rows quarantined', result.rejected],
    ['Games', result.games],
    ['Import time', typeof result.seconds === 'number' ? `${result.seconds}s` : undefined],
    ['Source version', result.source_version],
  ]
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-lg border bg-background p-3 text-sm">
      {rows
        .filter(([, v]) => v !== undefined && v !== null)
        .map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="tabular-nums">
              {typeof value === 'number' ? number.format(value) : String(value)}
            </dd>
          </div>
        ))}
    </dl>
  )
}

function CacheStatsCard() {
  const stats = useCacheStats()
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Gauge className="size-4" aria-hidden="true" /> Analytics cache
        </CardTitle>
        <CardDescription>Shared Redis cache for team stats and comparisons.</CardDescription>
      </CardHeader>
      <CardContent>
        {stats.isPending ? (
          <Skeleton className="h-16" aria-label="Loading cache stats" />
        ) : stats.isError ? (
          <p className="text-sm text-muted-foreground">Cache stats unavailable.</p>
        ) : !stats.data.available ? (
          <p className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-300">
            <Database className="size-4" aria-hidden="true" /> Redis is unreachable. Analytics are
            served uncached.
          </p>
        ) : (
          <dl className="grid grid-cols-3 gap-2 text-center">
            {[
              [
                'Hit rate',
                stats.data.hit_rate === null ? '—' : `${Math.round(stats.data.hit_rate * 100)}%`,
              ],
              ['Hits', number.format(stats.data.hits)],
              ['Misses', number.format(stats.data.misses)],
            ].map(([label, value]) => (
              <div key={label} className="flex flex-col-reverse rounded-md bg-muted/50 py-2">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="text-lg font-semibold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  )
}
