import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import comparison from './fixtures/comparison-kc-phi-2024.json'
import seasons from './fixtures/seasons.json'
import teams from './fixtures/teams.json'

// Fixtures are real API responses captured from the 2024 nflverse import.
export const fixtures = { comparison, seasons, teams }

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

export const handlers = [
  http.get('*/api/v1/teams', () => HttpResponse.json(teams)),
  http.get('*/api/v1/seasons', () => HttpResponse.json(seasons)),
  http.get('*/api/v1/analytics/team-comparison', () => HttpResponse.json(comparison)),
  http.get('*/api/v1/auth/me', unauthorized),
]

export const server = setupServer(...handlers)
