import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { location, renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { PlayersPage } from './PlayersPage'

describe('PlayersPage', () => {
  it('searches by name, adds a player and shows stats with limitations', async () => {
    const user = userEvent.setup()
    const searches: string[] = []
    server.use(
      http.get('*/api/v1/players', ({ request }) => {
        searches.push(new URL(request.url).searchParams.get('search') ?? '')
        return HttpResponse.json({
          items: [{ id: '00-0033106', name: 'Jared Goff', position: 'QB', season_plays: 650 }],
          page: 1,
          page_size: 20,
          total: 1,
        })
      }),
    )
    renderWithProviders(<PlayersPage />, { route: '/players?season=2024' })
    expect(await screen.findByText('Pick a player')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Name'), 'Goff')
    const results = await screen.findByRole('list', { name: 'Player results' })
    await waitFor(() => expect(searches).toContain('Goff'))
    await user.click(within(results).getByRole('button', { name: 'Compare Jared Goff' }))

    expect(location.current).toBe('/players?season=2024&player=00-0033106')
    expect(await screen.findByTestId('00-0033106-pass_attempts')).toHaveTextContent('579')
    expect(screen.getByTestId('00-0033106-completion_rate')).toHaveTextContent('71.3%')
    expect(screen.getByText('649 plays · 18 games')).toBeInTheDocument()
    expect(screen.getByText('Limitations')).toBeInTheDocument()
    expect(screen.getByText('EPA / dropback', { selector: 'dt' })).toBeInTheDocument()
  })

  it('removes a player from the comparison', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PlayersPage />, { route: '/players?season=2024&player=00-0033106' })
    await user.click(await screen.findByRole('button', { name: 'Remove Jared Goff' }))
    expect(await screen.findByText('Pick a player')).toBeInTheDocument()
  })

  it('shows an error with retry when stats fail', async () => {
    server.use(
      http.get('*/api/v1/players/:id/stats', () =>
        HttpResponse.json({ error: { code: 'not_found', message: 'Player not found', request_id: 'p' } }, { status: 404 }),
      ),
    )
    renderWithProviders(<PlayersPage />, { route: '/players?season=2024&player=00-0000000' })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Player not found')
  })
})
