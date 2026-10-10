import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import comparison from './fixtures/comparison-kc-phi-2024.json'
import seasons from './fixtures/seasons.json'
import teams from './fixtures/teams.json'

// Fixtures are real API responses captured from the 2024 nflverse import.
export const fixtures = { comparison, seasons, teams }

export const handlers = [
  http.get('*/api/v1/teams', () => HttpResponse.json(teams)),
  http.get('*/api/v1/seasons', () => HttpResponse.json(seasons)),
  http.get('*/api/v1/analytics/team-comparison', () => HttpResponse.json(comparison)),
]

export const server = setupServer(...handlers)
