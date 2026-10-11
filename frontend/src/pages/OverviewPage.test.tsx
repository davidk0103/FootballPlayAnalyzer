import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { COACH, fixtures, server, signedInAs } from '@/test/server'
import { OverviewPage } from './OverviewPage'

describe('OverviewPage', () => {
  it('asks for a team first', async () => {
    renderWithProviders(<OverviewPage />, { route: '/overview?season=2024' })
    expect(await screen.findByText('Choose a team')).toBeInTheDocument()
  })

  it('shows offense and defense against the league with ranks and a trend chart', async () => {
    renderWithProviders(<OverviewPage />, { route: '/overview?season=2024&team=DET' })
    const offense = await screen.findByLabelText('offense metrics')
    const epa = within(offense).getByLabelText('EPA / play')
    expect(epa).toHaveTextContent('+0.165')
    expect(epa).toHaveTextContent('Rank 3 of 32')
    expect(screen.getByLabelText('defense metrics')).toBeInTheDocument()
    expect(screen.getByText('1,162 plays · 18 games')).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: /DET EPA per play by game/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Scouting report/ })).toHaveAttribute(
      'href',
      '/reports?new=1&season=2024&team=DET',
    )
  })

  it('offers your processed uploads as a data source when signed in', async () => {
    signedInAs(COACH)
    renderWithProviders(<OverviewPage />, { route: '/overview?season=2024' })
    const source = await screen.findByLabelText('Data')
    expect(await within(source).findByRole('option', { name: `My upload: ${fixtures.uploadReady.name}` })).toBeInTheDocument()
  })

  it('shows an error with retry when efficiency fails', async () => {
    server.use(
      http.get('*/api/v1/analytics/efficiency', () =>
        HttpResponse.json({ error: { code: 'upload_not_ready', message: 'Upload is still processing', request_id: 'x' } }, { status: 409 }),
      ),
    )
    renderWithProviders(<OverviewPage />, { route: '/overview?season=2024&team=DET' })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Upload is still processing')
    expect(within(alert).getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })
})
