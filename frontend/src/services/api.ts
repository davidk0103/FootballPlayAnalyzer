import type { components } from './api-types'

export type Team = components['schemas']['TeamOut']
export type Season = components['schemas']['SeasonOut']
export type TeamComparison = components['schemas']['TeamComparisonResponse']
export type TeamStats = components['schemas']['TeamStatsOut']
export type Metric = components['schemas']['MetricOut']
export type Metrics = components['schemas']['MetricsOut']
export type MetricKey = keyof Metrics
export type Job = components['schemas']['JobOut']
export type JobStatus = Job['status']
export type JobPage = components['schemas']['JobPage']
export type JobAttempt = components['schemas']['JobAttemptOut']
export type CacheStats = components['schemas']['CacheStatsOut']
type ErrorBody = components['schemas']['ErrorBody']

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly details: unknown

  constructor(
    status: number,
    code: string,
    message: string,
    requestId: string | null,
    details: unknown = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
    this.details = details
  }
}

type QueryValue = string | number | readonly (string | number)[] | null | undefined

export function buildQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, String(item))
    } else {
      search.append(key, String(value))
    }
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  params?: Record<string, QueryValue>
  body?: unknown
  headers?: Record<string, string>
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', params = {}, body, headers = {} } = options
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}${buildQuery(params)}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'network_error', 'Could not reach the PlaybookIQ API.', null)
  }
  if (!response.ok) {
    let error: Partial<ErrorBody> = {}
    try {
      error = ((await response.json()) as { error?: ErrorBody }).error ?? {}
    } catch {
      // Non-JSON error body (e.g. proxy error page).
    }
    throw new ApiError(
      response.status,
      error.code ?? `http_${response.status}`,
      error.message ?? `Request failed with status ${response.status}`,
      error.request_id ?? response.headers.get('X-Request-ID'),
      error.details ?? null,
    )
  }
  return (await response.json()) as T
}

function getJson<T>(path: string, params: Record<string, QueryValue> = {}): Promise<T> {
  return request<T>(path, { params })
}

export const ACTIVE_JOB_STATUSES: readonly JobStatus[] = [
  'queued',
  'running',
  'retrying',
  'cancel_requested',
]

export function isActiveJob(job: Pick<Job, 'status'>): boolean {
  return ACTIVE_JOB_STATUSES.includes(job.status)
}

export interface ImportJobInput {
  season: number
  force: boolean
  idempotencyKey: string
}

export interface ComparisonQuery {
  teamA: string
  teamB: string
  season: number
  side?: 'offense' | 'defense'
  seasonType?: 'REG' | 'POST'
  down?: number[]
  distance?: 'short' | 'medium' | 'long'
  fieldZone?: 'own_deep' | 'own' | 'opp' | 'red_zone'
  qtr?: number[]
  playType?: 'pass' | 'run'
}

export const api = {
  teams: () => getJson<Team[]>('/api/v1/teams'),
  seasons: () => getJson<Season[]>('/api/v1/seasons'),
  teamComparison: (q: ComparisonQuery) =>
    getJson<TeamComparison>('/api/v1/analytics/team-comparison', {
      team_a: q.teamA,
      team_b: q.teamB,
      season: q.season,
      side: q.side,
      season_type: q.seasonType,
      down: q.down,
      distance: q.distance,
      field_zone: q.fieldZone,
      qtr: q.qtr,
      play_type: q.playType,
    }),
  jobs: (q: { status?: JobStatus; page?: number; pageSize?: number } = {}) =>
    getJson<JobPage>('/api/v1/jobs', { status: q.status, page: q.page, page_size: q.pageSize }),
  job: (id: string) => getJson<Job>(`/api/v1/jobs/${id}`),
  jobAttempts: (id: string) => getJson<JobAttempt[]>(`/api/v1/jobs/${id}/attempts`),
  submitImport: (input: ImportJobInput) =>
    request<Job>('/api/v1/jobs/import', {
      method: 'POST',
      body: { season: input.season, force: input.force },
      headers: { 'Idempotency-Key': input.idempotencyKey },
    }),
  cancelJob: (id: string) => request<Job>(`/api/v1/jobs/${id}/cancel`, { method: 'POST' }),
  cacheStats: () => getJson<CacheStats>('/api/v1/cache/stats'),
}
