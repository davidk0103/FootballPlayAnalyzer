import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { delay, http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import type { Situational } from '@/services/api'
import { location, renderWithProviders } from '@/test/render'
import { fixtures, server } from '@/test/server'
import { SituationalPage } from './SituationalPage'

const KC = '/situational?season=2024&team=KC'

function captureRequests(path: string) {
  const urls: URL[] = []
  server.use(
    http.get(path, ({ request }) => {
      urls.push(new URL(request.url))
      return HttpResponse.json(fixtures.situational)
    }),
  )
  return urls
}

describe('SituationalPage', () => {
  it('shows each situation against the league with sample sizes and a chart', async () => {
    renderWithProviders(<SituationalPage />, { route: KC })
    const table = await screen.findByRole('table', { name: 'Situational breakdown' })
    expect(within(table).getByText('1st down')).toBeInTheDocument()
    expect(screen.getByTestId('row-1-value')).toHaveTextContent('+0.037')
    expect(within(table).getByText('4th down')).toBeInTheDocument()
    expect(within(table).getByText('(small sample)')).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: /EPA \/ play by situation for KC and the league/ })).toBeInTheDocument()
    expect(screen.getByText(/Small samples \(under 30 plays\): 4th down/)).toBeInTheDocument()
    expect(screen.getByText('How these are calculated')).toBeInTheDocument()
  })

  it('sends group-by, metric and filter choices to the API and the URL', async () => {
    const user = userEvent.setup()
    const urls = captureRequests('*/api/v1/analytics/situational')
    renderWithProviders(<SituationalPage />, { route: KC })
    await screen.findByRole('table', { name: 'Situational breakdown' })

    await user.selectOptions(screen.getByLabelText('Break down by'), 'field_zone')
    await waitFor(() => expect(urls.at(-1)?.searchParams.get('group_by')).toBe('field_zone'))

    await user.click(screen.getByRole('button', { name: '3rd down' }))
    await user.selectOptions(screen.getByLabelText('Perspective'), 'defense')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    await waitFor(() => {
      const last = urls.at(-1)
      expect(last?.searchParams.getAll('down')).toEqual(['3'])
      expect(last?.searchParams.get('side')).toBe('defense')
      expect(last?.searchParams.get('team')).toBe('KC')
    })
    expect(location.current).toContain('group_by=field_zone')
    expect(location.current).toContain('down=3')

    await user.selectOptions(screen.getByLabelText('Metric'), 'success_rate')
    expect(await screen.findByTestId('row-1-value')).toHaveTextContent('%')
  })

  it('queries the whole league when no team is chosen', async () => {
    const urls = captureRequests('*/api/v1/analytics/situational')
    renderWithProviders(<SituationalPage />, { route: '/situational?season=2024' })
    await screen.findByRole('table', { name: 'Situational breakdown' })
    expect(urls[0]?.searchParams.has('team')).toBe(false)
    expect(screen.getByLabelText('Team')).toHaveDisplayValue('Whole league')
  })

  it('shows an empty state when no plays match', async () => {
    const empty = structuredClone(fixtures.situational) as Situational
    empty.overall.plays = 0
    empty.rows = []
    server.use(http.get('*/api/v1/analytics/situational', () => HttpResponse.json(empty)))
    renderWithProviders(<SituationalPage />, { route: KC })
    expect(await screen.findByText('No plays match these filters')).toBeInTheDocument()
  })

  it('shows a skeleton while loading and an error with retry on failure', async () => {
    server.use(
      http.get('*/api/v1/analytics/situational', async () => {
        await delay('infinite')
        return HttpResponse.json({})
      }),
    )
    const { unmount } = renderWithProviders(<SituationalPage />, { route: KC })
    expect(await screen.findByLabelText('Loading situations')).toBeInTheDocument()
    unmount()

    let calls = 0
    server.use(
      http.get('*/api/v1/analytics/situational', () => {
        calls += 1
        return calls === 1
          ? HttpResponse.json({ error: { code: 'internal', message: 'Database unavailable', request_id: 'r1' } }, { status: 503 })
          : HttpResponse.json(fixtures.situational)
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<SituationalPage />, { route: KC })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Database unavailable')
    await user.click(within(alert).getByRole('button', { name: /try again/i }))
    expect(await screen.findByRole('table', { name: 'Situational breakdown' })).toBeInTheDocument()
  })

  it('renders the tendency grid and third-down split for a team', async () => {
    renderWithProviders(<SituationalPage />, { route: KC })
    const grid = await screen.findByRole('table', { name: 'Pass rate by down and distance' })
    expect(within(grid).getAllByText(/plays$/).length).toBeGreaterThan(0)
    expect(screen.getByTestId('third-down-conversion')).toHaveTextContent('%')
  })
})
