import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Report, ReportExport, ReportRequest } from '@/services/api'
import { location, renderWithProviders } from '@/test/render'
import { fixtures, server } from '@/test/server'
import { ReportDetailPage } from './ReportDetailPage'
import { ReportsPage } from './ReportsPage'

const ready = fixtures.report as Report
const pending: Report = { ...ready, status: 'pending', report: null, exports: [] }

function renderDetail() {
  return renderWithProviders(
    <Routes>
      <Route path="/reports/:id" element={<ReportDetailPage />} />
      <Route path="/reports" element={<p>Report list</p>} />
    </Routes>,
    { route: `/reports/${ready.id}` },
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ReportsPage', () => {
  it('lists saved reports', async () => {
    renderWithProviders(<ReportsPage />, { route: '/reports' })
    const table = await screen.findByRole('table', { name: 'Saved reports' })
    expect(within(table).getByRole('link', { name: 'Detroit Lions 2024 scouting report' })).toHaveAttribute(
      'href',
      `/reports/${ready.id}`,
    )
    expect(within(table).getByText('Upload')).toBeInTheDocument()
  })

  it('shows an empty state without saved reports', async () => {
    server.use(http.get('*/api/v1/reports', () => HttpResponse.json({ items: [], page: 1, page_size: 50, total: 0 })))
    renderWithProviders(<ReportsPage />, { route: '/reports' })
    expect(await screen.findByText('No saved reports yet')).toBeInTheDocument()
  })

  it('validates the form and creates a report with the chosen filters', async () => {
    const user = userEvent.setup()
    let body: ReportRequest | null = null
    server.use(
      http.post('*/api/v1/reports', async ({ request }) => {
        body = (await request.json()) as ReportRequest
        expect(request.headers.get('Idempotency-Key')).toBeTruthy()
        return HttpResponse.json(pending, { status: 202 })
      }),
    )
    renderWithProviders(<ReportsPage />, { route: '/reports?new=1&season=2024&team=DET' })
    const form = await screen.findByRole('form', { name: 'New scouting report' })
    await waitFor(() => expect(within(form).getByLabelText('Team')).toHaveValue('DET'))

    await user.type(within(form).getByLabelText('From week'), '10')
    await user.type(within(form).getByLabelText('To week'), '4')
    await user.type(within(form).getByLabelText('Only against'), 'K1')
    await user.click(within(form).getByRole('button', { name: 'Generate report' }))
    expect(await within(form).findByText('The first week must come before the last week')).toBeInTheDocument()
    expect(within(form).getByText('Use a team abbreviation such as KC')).toBeInTheDocument()
    expect(body).toBeNull()

    await user.clear(within(form).getByLabelText('To week'))
    await user.type(within(form).getByLabelText('To week'), '18')
    await user.clear(within(form).getByLabelText('Only against'))
    await user.type(within(form).getByLabelText('Only against'), 'gb')
    await user.click(within(form).getByRole('button', { name: 'Generate report' }))

    await waitFor(() => expect(location.current).toBe(`/reports/${ready.id}`))
    expect(body).toMatchObject({ team: 'DET', season: 2024, dataset_id: null, week_min: 10, week_max: 18, opponent: 'GB' })
  })

  it('needs a team before generating', async () => {
    renderWithProviders(<ReportsPage />, { route: '/reports?new=1&season=2024' })
    const form = await screen.findByRole('form', { name: 'New scouting report' })
    expect(within(form).getByRole('button', { name: 'Generate report' })).toBeDisabled()
  })
})

describe('ReportDetailPage', () => {
  it('shows progress while generating and the report once ready', async () => {
    let calls = 0
    server.use(
      http.get('*/api/v1/reports/:id', () => {
        calls += 1
        return HttpResponse.json(calls === 1 ? pending : ready)
      }),
    )
    renderDetail()
    expect(await screen.findByRole('progressbar', { name: 'Generating report' })).toBeInTheDocument()
    const findings = await screen.findByRole('list', { name: 'Key findings' }, { timeout: 4000 })
    expect(findings).toHaveTextContent('Defense 3rd-down conversion allowed: 33.0% vs league 40.4% (rank 1 of 32, n=197).')
    expect(within(findings).getAllByText('Weakness').length).toBeGreaterThan(0)
    expect(screen.getByRole('table', { name: 'offense metrics' })).toHaveTextContent('+0.165')
    expect(screen.getByRole('table', { name: 'Red zone' })).toBeInTheDocument()
    expect(screen.getByText('Limitations')).toBeInTheDocument()
    expect(screen.getByText('Jared Goff')).toBeInTheDocument()
  })

  it('exports CSV in the background and offers the download', async () => {
    const user = userEvent.setup()
    const base = { ...ready, exports: [] as ReportExport[] }
    const exportRow = (status: ReportExport['status']): ReportExport => ({
      id: '1d7e0000-0000-4000-8000-0000000000aa',
      report_id: ready.id,
      format: 'csv',
      status,
      size_bytes: status === 'ready' ? 6758 : null,
      error: null,
      job_id: null,
      created_at: '2026-10-11T04:40:12Z',
      download_url: status === 'ready' ? `/api/v1/reports/${ready.id}/exports/x/download` : null,
    })
    let state: Report = base
    let format: string | null = null
    server.use(
      http.get('*/api/v1/reports/:id', () => HttpResponse.json(state)),
      http.post('*/api/v1/reports/:id/exports', async ({ request }) => {
        format = ((await request.json()) as { format: string }).format
        state = { ...base, exports: [exportRow('pending')] }
        return HttpResponse.json(exportRow('pending'), { status: 202 })
      }),
    )
    renderDetail()
    await user.click(await screen.findByRole('button', { name: 'Export CSV' }))
    expect(await screen.findByText('Building…')).toBeInTheDocument()
    expect(format).toBe('csv')
    expect(screen.getByRole('button', { name: 'Export JSON' })).toBeDisabled()

    state = { ...base, exports: [exportRow('ready')] }
    const link = await screen.findByRole('link', { name: /Download/ }, { timeout: 4000 })
    expect(link).toHaveAttribute('href', `/api/v1/reports/${ready.id}/exports/x/download`)
    expect(link).toHaveTextContent('6.6 KB')
  })

  it('prints with the browser print dialog', async () => {
    const user = userEvent.setup()
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    renderDetail()
    await user.click(await screen.findByRole('button', { name: 'Print' }))
    expect(print).toHaveBeenCalledOnce()
  })

  it('explains a failed report and retries with the same inputs', async () => {
    const user = userEvent.setup()
    const failed: Report = { ...pending, status: 'failed', error: 'No plays for DET in 2031' }
    let retried: ReportRequest | null = null
    server.use(
      http.get('*/api/v1/reports/:id', () => HttpResponse.json(failed)),
      http.post('*/api/v1/reports', async ({ request }) => {
        retried = (await request.json()) as ReportRequest
        return HttpResponse.json(pending, { status: 202 })
      }),
    )
    renderDetail()
    expect(await screen.findByText('No plays for DET in 2031')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Try again/ }))
    await waitFor(() => expect(retried).toMatchObject({ team: 'DET', season: 2024, title: ready.title }))
  })

  it('deletes after confirmation', async () => {
    const user = userEvent.setup()
    let deleted = false
    server.use(
      http.delete('*/api/v1/reports/:id', () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderDetail()
    await user.click(await screen.findByRole('button', { name: 'Delete' }))
    await user.click(screen.getByRole('button', { name: 'Delete report' }))
    expect(await screen.findByText('Report list')).toBeInTheDocument()
    expect(deleted).toBe(true)
  })
})
