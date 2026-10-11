import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { Job, MappingValidation, UploadDetail } from '@/services/api'
import { renderWithProviders } from '@/test/render'
import { fixtures, server } from '@/test/server'
import { UploadDetailPage } from './UploadDetailPage'

const uploaded = fixtures.uploadUploaded as UploadDetail
const ready = fixtures.uploadReady as UploadDetail
const route = (u: UploadDetail) => `/uploads/${u.id}`

function renderDetail(u: UploadDetail) {
  return renderWithProviders(
    <Routes>
      <Route path="/uploads/:id" element={<UploadDetailPage />} />
    </Routes>,
    { route: route(u) },
  )
}

function serve(...states: UploadDetail[]) {
  let i = 0
  server.use(
    http.get('*/api/v1/uploads/:id', () => {
      const state = states[Math.min(i, states.length - 1)]
      i += 1
      return HttpResponse.json(state)
    }),
  )
}

const job = (patch: Partial<Job>): Job => ({
  id: '9b7d3c1e-0000-4000-8000-000000000001',
  task_type: 'import_upload',
  status: 'running',
  params: { dataset_id: uploaded.id },
  user_id: 2,
  attempt_count: 1,
  max_attempts: 3,
  timeout_seconds: 300,
  result: null,
  progress: null,
  error: null,
  created_at: '2026-10-11T04:42:35Z',
  updated_at: '2026-10-11T04:42:36Z',
  started_at: '2026-10-11T04:42:36Z',
  finished_at: null,
  heartbeat_at: null,
  next_retry_at: null,
  cancel_requested_at: null,
  ...patch,
})

describe('UploadDetailPage', () => {
  it('previews the file as text and pre-fills the suggested mapping', async () => {
    serve(uploaded)
    renderDetail(uploaded)
    const preview = await screen.findByRole('table', { name: 'File preview' })
    expect(within(preview).getByText('Field Pos')).toBeInTheDocument()
    expect(screen.getByLabelText('Column for Offense')).toHaveValue('Off')
    expect(screen.getByLabelText('Column for Yards from end zone')).toHaveValue('')
    expect(screen.getByText('Needs mapping')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Process all rows' })).toBeDisabled()
  })

  it('blocks checking until every required field is mapped', async () => {
    const user = userEvent.setup()
    serve(uploaded)
    renderDetail(uploaded)
    await user.selectOptions(await screen.findByLabelText('Column for Offense'), '')
    expect(screen.getByRole('button', { name: 'Check mapping' })).toBeDisabled()
    expect(screen.getByText(/Map Offense first/)).toBeInTheDocument()
  })

  it('validates the mapping and shows accepted rows and row-level problems', async () => {
    const user = userEvent.setup()
    let body: { mapping: Record<string, string> } | null = null
    serve(uploaded)
    server.use(
      http.post('*/api/v1/uploads/:id/validate', async ({ request }) => {
        body = (await request.json()) as { mapping: Record<string, string> }
        return HttpResponse.json(fixtures.validation)
      }),
    )
    renderDetail(uploaded)
    await user.selectOptions(await screen.findByLabelText('Column for Yards from end zone'), 'Field Pos')
    await user.click(screen.getByRole('button', { name: 'Check mapping' }))

    const result = await screen.findByTestId('validation-result')
    expect(result).toHaveTextContent('1 accepted, 3 would be set aside')
    expect(within(result).getByText("Down must be a whole number from 1 to 4 (got '5')")).toBeInTheDocument()
    expect(within(result).getByText('Offense and defense are the same team')).toBeInTheDocument()
    expect((body as unknown as { mapping: Record<string, string> }).mapping.yard_line_100).toBe('Field Pos')
    expect(screen.getByRole('button', { name: 'Process all rows' })).toBeEnabled()
  })

  it('shows mapping errors when the server rejects the mapping', async () => {
    const user = userEvent.setup()
    serve(uploaded)
    const invalid: MappingValidation = {
      ...(fixtures.validation as MappingValidation),
      valid: false,
      mapping_errors: ['No rows in the sample are valid with this mapping'],
      upload: uploaded,
    }
    server.use(http.post('*/api/v1/uploads/:id/validate', () => HttpResponse.json(invalid)))
    renderDetail(uploaded)
    await user.click(await screen.findByRole('button', { name: 'Check mapping' }))
    expect(await screen.findByTestId('mapping-errors')).toHaveTextContent('No rows in the sample are valid')
  })

  it('processes with live job progress and then shows the result', async () => {
    const user = userEvent.setup()
    const validated = { ...uploaded, status: 'validated' as const, mapping: uploaded.suggested_mapping }
    const processing = {
      ...validated,
      status: 'processing' as const,
      job: job({ progress: { stage: 'storing', done: 1000, total: 2245 } }),
    }
    let processed = false
    server.use(
      http.get('*/api/v1/uploads/:id', () => HttpResponse.json(processed ? processing : validated)),
      http.post('*/api/v1/uploads/:id/process', ({ request }) => {
        expect(request.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/)
        processed = true
        return HttpResponse.json(processing.job, { status: 202 })
      }),
    )
    renderDetail(uploaded)
    await user.click(await screen.findByRole('button', { name: 'Process all rows' }))

    const bar = await screen.findByRole('progressbar', { name: 'Saving plays' })
    expect(bar).toHaveAttribute('aria-valuenow', '45')
    expect(screen.getByText(/1,000 \/ 2,245 rows/)).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Column mapping' })).not.toBeInTheDocument()

    server.use(http.get('*/api/v1/uploads/:id', () => HttpResponse.json(ready)))
    expect(await screen.findByText('Processed', {}, { timeout: 4000 })).toBeInTheDocument()
  })

  it('shows teams, rejected rows and analysis links once ready', async () => {
    serve(ready)
    renderDetail(ready)
    expect(await screen.findByText(/2,245 plays stored, 3 set aside/)).toBeInTheDocument()
    expect(await screen.findByRole('table', { name: 'Teams in this upload' })).toHaveTextContent('DET')
    const rejected = await screen.findByRole('table', { name: 'Rejected rows' })
    expect(rejected).toHaveTextContent("Down must be a whole number from 1 to 4 (got '5')")
    expect(screen.getByRole('link', { name: /Explore situations/ })).toHaveAttribute('href', `/situational?dataset=${ready.id}`)
    expect(screen.getByText('Column mapping used')).toBeInTheDocument()
  })

  it('shows why processing failed and allows another attempt', async () => {
    const failed = { ...uploaded, status: 'failed' as const, mapping: uploaded.suggested_mapping, error: 'No valid rows' }
    serve(failed)
    renderDetail(failed)
    expect(await screen.findByText('Processing failed')).toBeInTheDocument()
    expect(screen.getByText(/No valid rows/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Process all rows' })).toBeEnabled())
  })

  it('shows a not-found error for an upload you do not own', async () => {
    server.use(
      http.get('*/api/v1/uploads/:id', () =>
        HttpResponse.json({ error: { code: 'not_found', message: 'Upload not found', request_id: 'n' } }, { status: 404 }),
      ),
    )
    renderDetail(uploaded)
    expect(await screen.findByRole('alert')).toHaveTextContent('Upload not found')
  })
})
