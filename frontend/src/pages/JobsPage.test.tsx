import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import type { Job, JobAttempt } from '@/services/api'
import attemptsFixture from '@/test/fixtures/job-attempts-2024.json'
import succeededFixture from '@/test/fixtures/job-succeeded-2024.json'
import { location, renderWithProviders } from '@/test/render'
import { server, signedInAs, ADMIN } from '@/test/server'
import { JobsPage } from './JobsPage'

const done = succeededFixture as Job
const doneAttempts = attemptsFixture as JobAttempt[]
const QUEUED_ID = '7b0c6a43-0d7e-4c8f-9a43-1f2a3b4c5d6e'

function page(items: Job[]) {
  return { items, page: 1, page_size: 50, total: items.length }
}

function queuedJob(overrides: Partial<Job> = {}): Job {
  return {
    ...done,
    id: QUEUED_ID,
    status: 'queued',
    params: { season: 2023, force: false },
    attempt_count: 0,
    result: null,
    started_at: null,
    finished_at: null,
    heartbeat_at: null,
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

function useJobsApi(list: () => Job[], attempts: () => JobAttempt[] = () => []) {
  signedInAs(ADMIN)
  server.use(
    http.get('*/api/v1/jobs', () => HttpResponse.json(page(list()))),
    http.get('*/api/v1/jobs/:id/attempts', () => HttpResponse.json(attempts())),
    http.get('*/api/v1/cache/stats', () =>
      HttpResponse.json({
        enabled: true,
        available: true,
        hits: 30,
        misses: 10,
        bypass: 0,
        invalidations: 1,
        hit_rate: 0.75,
        degraded_errors_this_process: 0,
        ttl_seconds: 3600,
      }),
    ),
  )
}

describe('JobsPage', () => {
  it('shows an empty state with a call to action', async () => {
    useJobsApi(() => [])
    renderWithProviders(<JobsPage />, { route: '/jobs' })
    expect(await screen.findByText('No import jobs yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Queue import' })).toBeInTheDocument()
    expect(await screen.findByText('75%')).toBeInTheDocument()
  })

  it('lists a real finished import and expands its attempt history', async () => {
    const user = userEvent.setup()
    useJobsApi(() => [done], () => doneAttempts)
    renderWithProviders(<JobsPage />, { route: '/jobs' })

    const row = await screen.findByTestId('job-row')
    expect(within(row).getByText('Succeeded')).toBeInTheDocument()
    expect(within(row).getByText('43,110 plays stored')).toBeInTheDocument()

    await user.click(within(row).getByRole('button'))
    await waitFor(() => expect(location.current).toBe(`/jobs?job=${done.id}`))
    expect(await screen.findByText('Attempt 1: Succeeded')).toBeInTheDocument()
    expect(screen.getByText('285')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel job' })).not.toBeInTheDocument()
  })

  it('submits with an Idempotency-Key and polls the job until it finishes', async () => {
    const user = userEvent.setup()
    let job: Job | null = null
    let polls = 0
    const keys: (string | null)[] = []
    useJobsApi(() => {
      if (job && job.status !== 'succeeded' && ++polls >= 2) {
        job = { ...job, status: 'succeeded', attempt_count: 1, result: done.result }
      }
      return job ? [job] : []
    })
    server.use(
      http.post('*/api/v1/jobs/import', async ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key'))
        const body = (await request.json()) as { season: number; force: boolean }
        job = queuedJob({ params: body })
        return HttpResponse.json(job, { status: 202 })
      }),
    )
    renderWithProviders(<JobsPage />, { route: '/jobs' })

    const season = await screen.findByLabelText('Season')
    await user.clear(season)
    await user.type(season, '2023')
    await user.click(screen.getByRole('button', { name: 'Queue import' }))

    await waitFor(() => expect(keys).toHaveLength(1))
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/)
    expect(await screen.findByText('Waiting for a worker')).toBeInTheDocument()
    await waitFor(() => expect(location.current).toBe(`/jobs?job=${QUEUED_ID}`))
    // Active jobs are polled; the row flips to succeeded without any user action.
    expect(await screen.findByText('Succeeded', {}, { timeout: 5000 })).toBeInTheDocument()
  })

  it('validates the season before submitting', async () => {
    const user = userEvent.setup()
    useJobsApi(() => [])
    renderWithProviders(<JobsPage />, { route: '/jobs' })
    const season = await screen.findByLabelText('Season')
    await user.clear(season)
    await user.type(season, '1990')
    await user.click(screen.getByRole('button', { name: 'Queue import' }))
    expect(await screen.findByText('nflverse play-by-play starts in 1999')).toBeInTheDocument()
  })

  it('explains a duplicate submission and links to the running job', async () => {
    const user = userEvent.setup()
    useJobsApi(() => [])
    server.use(
      http.post('*/api/v1/jobs/import', () =>
        HttpResponse.json(
          {
            error: {
              code: 'duplicate_job',
              message: 'An import for season 2024 is already in progress',
              request_id: 'r1',
              details: { existing_job_id: QUEUED_ID },
            },
          },
          { status: 409 },
        ),
      ),
      http.get(`*/api/v1/jobs/${QUEUED_ID}`, () =>
        HttpResponse.json(queuedJob({ status: 'running', attempt_count: 1 })),
      ),
    )
    renderWithProviders(<JobsPage />, { route: '/jobs' })
    await user.click(await screen.findByRole('button', { name: 'Queue import' }))

    expect(await screen.findByText('This season is already being imported')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'View the running job' }))
    await waitFor(() => expect(location.current).toBe(`/jobs?job=${QUEUED_ID}`))
    expect(await screen.findByRole('button', { name: 'Cancel job' })).toBeInTheDocument()
  })

  it('cancels a running job', async () => {
    const user = userEvent.setup()
    let job = queuedJob({ status: 'running', attempt_count: 1, started_at: new Date().toISOString() })
    useJobsApi(() => [job])
    server.use(
      http.post(`*/api/v1/jobs/${QUEUED_ID}/cancel`, () => {
        job = { ...job, status: 'cancel_requested', cancel_requested_at: new Date().toISOString() }
        return HttpResponse.json(job, { status: 202 })
      }),
    )
    renderWithProviders(<JobsPage />, { route: `/jobs?job=${QUEUED_ID}` })

    await user.click(await screen.findByRole('button', { name: 'Cancel job' }))
    const row = await screen.findByTestId('job-row')
    expect(await within(row).findByText('Cancelling')).toBeInTheDocument()
    expect(within(row).getByText(/Stopping at the next checkpoint/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel job' })).not.toBeInTheDocument()
  })

  it('filters by status through the URL', async () => {
    const user = userEvent.setup()
    const seen: (string | null)[] = []
    useJobsApi(() => [])
    server.use(
      http.get('*/api/v1/jobs', ({ request }) => {
        seen.push(new URL(request.url).searchParams.get('status'))
        return HttpResponse.json(page([]))
      }),
    )
    renderWithProviders(<JobsPage />, { route: '/jobs' })
    await user.selectOptions(await screen.findByLabelText('Filter by status'), 'failed')
    expect(await screen.findByText('No jobs with this status')).toBeInTheDocument()
    await waitFor(() => expect(location.current).toBe('/jobs?status=failed'))
    expect(seen).toContain('failed')
  })

  it('shows an error state when the API is unreachable', async () => {
    useJobsApi(() => [])
    server.use(http.get('*/api/v1/jobs', () => HttpResponse.error()))
    renderWithProviders(<JobsPage />, { route: '/jobs' })
    expect(await screen.findByText('Could not load jobs')).toBeInTheDocument()
    expect(screen.getByText('Could not reach the PlaybookIQ API.')).toBeInTheDocument()
  })

  it('hides the import form from visitors who are not administrators', async () => {
    useJobsApi(() => [done], () => doneAttempts)
    signedInAs(null)
    renderWithProviders(<JobsPage />, { route: '/jobs' })
    expect(await screen.findByText(/only administrators can start them/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Queue import' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'sign in' })).toHaveAttribute('href', '/login?next=%2Fjobs')
  })
})
