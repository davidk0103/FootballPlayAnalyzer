import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { delay, http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import type { TeamComparison } from '@/services/api'
import { fixtures, server } from '@/test/server'
import { location, renderWithProviders } from '@/test/render'
import { ComparePage } from './ComparePage'

const KC_PHI = '/compare?team_a=KC&team_b=PHI&season=2024'

describe('ComparePage', () => {
  it('prompts for teams and defaults to the latest season', async () => {
    renderWithProviders(<ComparePage />, { route: '/compare' })
    expect(await screen.findByText('Pick two teams to compare')).toBeInTheDocument()
    await waitFor(() => expect(location.current).toBe('/compare?season=2024'))
    expect(screen.getByLabelText('Season')).toHaveValue('2024')
  })

  it('compares two picked teams and shows real metrics with sample sizes', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ComparePage />, { route: '/compare?season=2024' })

    await user.selectOptions(await screen.findByLabelText('Team A'), 'KC')
    await user.selectOptions(screen.getByLabelText('Team B'), 'PHI')

    expect(await screen.findByTestId('metric-epa_per_play-a')).toHaveTextContent('+0.063')
    expect(screen.getByTestId('metric-epa_per_play-b')).toHaveTextContent('+0.120')
    expect(screen.getByText('1,223 plays · 20 games')).toBeInTheDocument()
    expect(screen.getByText('How these are calculated')).toBeInTheDocument()
    expect(location.current).toBe(KC_PHI)
  })

  it('disables picking the same team on both sides', async () => {
    renderWithProviders(<ComparePage />, { route: KC_PHI })
    const teamB = await screen.findByLabelText('Team B')
    expect(within(teamB).getByRole('option', { name: /Kansas City Chiefs/ })).toBeDisabled()
  })

  it('shows a loading skeleton while the comparison loads', async () => {
    server.use(
      http.get('*/api/v1/analytics/team-comparison', async () => {
        await delay('infinite')
        return HttpResponse.json({})
      }),
    )
    renderWithProviders(<ComparePage />, { route: KC_PHI })
    expect(await screen.findByLabelText('Loading comparison')).toBeInTheDocument()
  })

  it('shows the API error message and request id with a retry button', async () => {
    server.use(
      http.get('*/api/v1/analytics/team-comparison', () =>
        HttpResponse.json(
          { error: { code: 'not_found', message: 'No imported data for season 2024', request_id: 'abc' } },
          { status: 404 },
        ),
      ),
    )
    renderWithProviders(<ComparePage />, { route: KC_PHI })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('No imported data for season 2024')
    expect(alert).toHaveTextContent('Request ID: abc')
    expect(within(alert).getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('shows an empty state when no seasons are imported', async () => {
    server.use(http.get('*/api/v1/seasons', () => HttpResponse.json([])))
    renderWithProviders(<ComparePage />, { route: '/compare' })
    expect(await screen.findByText('No seasons imported yet')).toBeInTheDocument()
  })

  it('renders null metrics as n/a with warnings for an empty filter', async () => {
    const empty = structuredClone(fixtures.comparison) as TeamComparison
    for (const side of [empty.team_a, empty.team_b]) {
      side.sample = { plays: 0, games: 0 }
      for (const metric of Object.values(side.metrics)) {
        Object.assign(metric, { value: null, numerator: 0, denominator: 0 })
      }
    }
    empty.warnings = ['KC: No plays match these filters', 'PHI: No plays match these filters']
    server.use(http.get('*/api/v1/analytics/team-comparison', () => HttpResponse.json(empty)))

    renderWithProviders(<ComparePage />, { route: `${KC_PHI}&qtr=5&down=4` })
    expect(await screen.findByTestId('metric-success_rate-a')).toHaveTextContent('n/a')
    expect(screen.getByText('KC: No plays match these filters')).toBeInTheDocument()
  })

  it('applies filters to the URL and the API request', async () => {
    const user = userEvent.setup()
    const seen: string[] = []
    server.use(
      http.get('*/api/v1/analytics/team-comparison', ({ request }) => {
        seen.push(new URL(request.url).search)
        return HttpResponse.json(fixtures.comparison)
      }),
    )
    renderWithProviders(<ComparePage />, { route: KC_PHI })
    await screen.findByTestId('metric-epa_per_play-a')

    await user.click(screen.getByRole('button', { name: '3rd down' }))
    await user.selectOptions(screen.getByLabelText('Distance to go'), 'long')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))

    await waitFor(() => expect(location.current).toBe(`${KC_PHI}&down=3&distance=long`))
    await waitFor(() => expect(seen.at(-1)).toContain('down=3'))
    expect(seen.at(-1)).toContain('distance=long')

    await user.click(screen.getByRole('button', { name: 'Reset' }))
    await waitFor(() => expect(location.current).toBe(KC_PHI))
  })

  it('swaps teams', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ComparePage />, { route: KC_PHI })
    await user.click(await screen.findByRole('button', { name: 'Swap teams' }))
    await waitFor(() => expect(location.current).toBe('/compare?team_a=PHI&team_b=KC&season=2024'))
  })
})
