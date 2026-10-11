import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import comparison from './fixtures/comparison-kc-phi-2024.json'
import efficiencyDefense from './fixtures/efficiency-det-2024-defense.json'
import efficiencyOffense from './fixtures/efficiency-det-2024-offense.json'
import playerStats from './fixtures/player-stats-goff-2024.json'
import playerSearch from './fixtures/players-search-goff.json'
import report from './fixtures/report-det-2024.json'
import reports from './fixtures/reports-list.json'
import seasons from './fixtures/seasons.json'
import situational from './fixtures/situational-kc-2024-down.json'
import teams from './fixtures/teams.json'
import tendencies from './fixtures/tendencies-kc-2024.json'
import trends from './fixtures/trends-det-2024.json'
import uploadReady from './fixtures/upload-ready.json'
import uploadRejected from './fixtures/upload-rejected.json'
import uploadTeams from './fixtures/upload-teams.json'
import uploadUploaded from './fixtures/upload-uploaded.json'
import validation from './fixtures/upload-validation.json'

// Fixtures are real API responses captured from the 2024 nflverse import and real uploads.
export const fixtures = {
  comparison,
  seasons,
  teams,
  situational,
  tendencies,
  efficiencyOffense,
  efficiencyDefense,
  trends,
  playerSearch,
  playerStats,
  report,
  reports,
  uploadReady,
  uploadUploaded,
  uploadTeams,
  uploadRejected,
  validation,
}

export const ADMIN = {
  id: 1,
  email: 'admin@playbookiq.test',
  is_admin: true,
  created_at: '2026-10-11T12:00:00Z',
}
export const COACH = { ...ADMIN, id: 2, email: 'coach@example.com', is_admin: false }

const unauthorized = () =>
  HttpResponse.json(
    { error: { code: 'unauthorized', message: 'Sign in required', request_id: 'test' } },
    { status: 401 },
  )

/** Make /auth/me answer as this user (or signed out with null). */
export function signedInAs(user: typeof ADMIN | null) {
  server.use(
    http.get('*/api/v1/auth/me', () => (user ? HttpResponse.json(user) : unauthorized())),
  )
}

const page = <T>(items: T[]) => ({ items, page: 1, page_size: 50, total: items.length })

export const handlers = [
  http.get('*/api/v1/teams', () => HttpResponse.json(teams)),
  http.get('*/api/v1/seasons', () => HttpResponse.json(seasons)),
  http.get('*/api/v1/analytics/team-comparison', () => HttpResponse.json(comparison)),
  http.get('*/api/v1/analytics/situational', () => HttpResponse.json(situational)),
  http.get('*/api/v1/analytics/efficiency', ({ request }) =>
    HttpResponse.json(
      new URL(request.url).searchParams.get('side') === 'defense' ? efficiencyDefense : efficiencyOffense,
    ),
  ),
  http.get('*/api/v1/analytics/trends', () => HttpResponse.json(trends)),
  http.get('*/api/v1/teams/:team/tendencies', () => HttpResponse.json(tendencies)),
  http.get('*/api/v1/players', () => HttpResponse.json(playerSearch)),
  http.get('*/api/v1/players/:id/stats', () => HttpResponse.json(playerStats)),
  http.get('*/api/v1/uploads', () => HttpResponse.json(page([uploadReady]))),
  http.get('*/api/v1/uploads/:id/teams', () => HttpResponse.json(uploadTeams)),
  http.get('*/api/v1/uploads/:id/rejected', () => HttpResponse.json(uploadRejected)),
  http.get('*/api/v1/reports', () => HttpResponse.json(reports)),
  http.get('*/api/v1/reports/:id', () => HttpResponse.json(report)),
  http.get('*/api/v1/auth/me', unauthorized),
]

export const server = setupServer(...handlers)
