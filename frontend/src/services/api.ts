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
export type User = components['schemas']['UserOut']
export type Dataset = components['schemas']['DatasetOut']
export type TeamKey = components['schemas']['TeamKey']
export type Situational = components['schemas']['SituationalResponse']
export type SituationRow = components['schemas']['SituationRowOut']
export type Efficiency = components['schemas']['EfficiencyResponse']
export type Trends = components['schemas']['TrendsResponse']
export type Tendencies = components['schemas']['TendenciesResponse']
export type ThirdDown = components['schemas']['ThirdDownOut']
export type TendencyCell = components['schemas']['TendencyCellOut']
export type Player = components['schemas']['PlayerOut']
export type PlayerListItem = components['schemas']['PlayerListItem']
export type PlayerPage = components['schemas']['PlayerPage']
export type PlayerStats = components['schemas']['PlayerStatsResponse']
export type Upload = components['schemas']['UploadOut']
export type UploadDetail = components['schemas']['UploadDetailOut']
export type UploadPage = components['schemas']['UploadPage']
export type UploadStatus = Upload['status']
export type SchemaField = components['schemas']['SchemaFieldOut']
export type MappingValidation = components['schemas']['ValidationOut']
export type RowIssue = components['schemas']['RowIssueOut']
export type RejectedPage = components['schemas']['QuarantinePage']
export type UploadTeam = components['schemas']['TeamCountOut']
export type Report = components['schemas']['ReportOut']
export type ReportSummary = components['schemas']['ReportSummaryOut']
export type ReportPage = components['schemas']['ReportPage']
export type ReportRequest = components['schemas']['ReportRequest']
export type ScoutingReport = components['schemas']['ScoutingReportOut']
export type SideReport = components['schemas']['SideReportOut']
export type ReportMetric = components['schemas']['ReportMetricOut']
export type ReportExport = components['schemas']['ExportOut']
export type ExportFormat = ReportExport['format']
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

// Unsafe requests must carry this header (the API rejects them otherwise). Browsers
// cannot add custom headers to cross-site form posts, which is what blocks CSRF.
export const CSRF_HEADER = 'X-PlaybookIQ-CSRF'

interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE'
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
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        ...(method === 'GET' ? {} : { [CSRF_HEADER]: '1' }),
        ...(body === undefined || body instanceof FormData
          ? {}
          : { 'Content-Type': 'application/json' }),
        ...headers,
      },
      body:
        body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
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
  if (response.status === 204) return undefined as T
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

export type Side = 'offense' | 'defense'
export type GroupBy = 'down' | 'distance' | 'field_zone' | 'qtr' | 'score_state' | 'play_type'

/** Shared analytics filters; ``datasetId`` switches from public data to one of your uploads. */
export interface AnalyticsQuery {
  season?: number | null
  datasetId?: string | null
  side?: Side
  seasonType?: 'REG' | 'POST'
  weekMin?: number
  weekMax?: number
  opponent?: string
  down?: number[]
  distance?: 'short' | 'medium' | 'long'
  fieldZone?: 'own_deep' | 'own' | 'opp' | 'red_zone'
  qtr?: number[]
  scoreState?: 'trailing_9plus' | 'trailing_1_8' | 'tied' | 'leading_1_8' | 'leading_9plus'
  playType?: 'pass' | 'run'
}

function analyticsParams(q: AnalyticsQuery): Record<string, QueryValue> {
  return {
    season: q.season,
    dataset_id: q.datasetId,
    side: q.side,
    season_type: q.seasonType,
    week_min: q.weekMin,
    week_max: q.weekMax,
    opponent: q.opponent,
    down: q.down,
    distance: q.distance,
    field_zone: q.fieldZone,
    qtr: q.qtr,
    score_state: q.scoreState,
    play_type: q.playType,
  }
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
  jobs: (q: { status?: JobStatus; taskType?: string; page?: number; pageSize?: number } = {}) =>
    getJson<JobPage>('/api/v1/jobs', {
      status: q.status,
      task_type: q.taskType,
      page: q.page,
      page_size: q.pageSize,
    }),
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

  situational: (q: AnalyticsQuery & { team?: string | null; groupBy: GroupBy }) =>
    getJson<Situational>('/api/v1/analytics/situational', {
      ...analyticsParams(q),
      team: q.team,
      group_by: q.groupBy,
    }),
  efficiency: (q: AnalyticsQuery & { team: string }) =>
    getJson<Efficiency>('/api/v1/analytics/efficiency', { ...analyticsParams(q), team: q.team }),
  trends: (q: AnalyticsQuery & { team: string }) =>
    getJson<Trends>('/api/v1/analytics/trends', { ...analyticsParams(q), team: q.team }),
  tendencies: (q: AnalyticsQuery & { team: string }) =>
    getJson<Tendencies>(`/api/v1/teams/${encodeURIComponent(q.team)}/tendencies`, analyticsParams(q)),

  players: (q: { search?: string; season?: number | null; position?: string; page?: number }) =>
    getJson<PlayerPage>('/api/v1/players', {
      search: q.search,
      season: q.season,
      position: q.position,
      page: q.page,
      page_size: 20,
    }),
  player: (id: string) => getJson<Player>(`/api/v1/players/${encodeURIComponent(id)}`),
  playerStats: (id: string, q: AnalyticsQuery) =>
    getJson<PlayerStats>(`/api/v1/players/${encodeURIComponent(id)}/stats`, analyticsParams(q)),

  uploads: (page = 1) => getJson<UploadPage>('/api/v1/uploads', { page, page_size: 50 }),
  upload: (id: string) => getJson<UploadDetail>(`/api/v1/uploads/${id}`),
  createUpload: (file: File, name?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (name) form.append('name', name)
    return request<UploadDetail>('/api/v1/uploads', { method: 'POST', body: form })
  },
  validateUpload: (id: string, mapping: Record<string, string>) =>
    request<MappingValidation>(`/api/v1/uploads/${id}/validate`, {
      method: 'POST',
      body: { mapping },
    }),
  processUpload: (id: string, idempotencyKey: string) =>
    request<Job>(`/api/v1/uploads/${id}/process`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
    }),
  deleteUpload: (id: string) => request<void>(`/api/v1/uploads/${id}`, { method: 'DELETE' }),
  uploadTeams: (id: string) => getJson<UploadTeam[]>(`/api/v1/uploads/${id}/teams`),
  uploadRejected: (id: string, page = 1) =>
    getJson<RejectedPage>(`/api/v1/uploads/${id}/rejected`, { page, page_size: 50 }),

  reports: (page = 1) => getJson<ReportPage>('/api/v1/reports', { page, page_size: 50 }),
  report: (id: string) => getJson<Report>(`/api/v1/reports/${id}`),
  createReport: (body: ReportRequest, idempotencyKey: string) =>
    request<Report>('/api/v1/reports', {
      method: 'POST',
      body,
      headers: { 'Idempotency-Key': idempotencyKey },
    }),
  deleteReport: (id: string) => request<void>(`/api/v1/reports/${id}`, { method: 'DELETE' }),
  createExport: (id: string, format: ExportFormat, idempotencyKey: string) =>
    request<ReportExport>(`/api/v1/reports/${id}/exports`, {
      method: 'POST',
      body: { format },
      headers: { 'Idempotency-Key': idempotencyKey },
    }),

  me: () => getJson<User>('/api/v1/auth/me'),
  login: (body: Credentials) => request<User>('/api/v1/auth/login', { method: 'POST', body }),
  register: (body: Credentials) =>
    request<User>('/api/v1/auth/register', { method: 'POST', body }),
  logout: () => request<void>('/api/v1/auth/logout', { method: 'POST' }),
  logoutAll: () => request<void>('/api/v1/auth/logout-all', { method: 'POST' }),
}

export interface Credentials {
  email: string
  password: string
}
