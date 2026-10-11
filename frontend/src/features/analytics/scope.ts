/** Which data an analytics page looks at: a public season or one of your uploads, plus a team. */
export interface Scope {
  season: number | null
  datasetId: string | null
  team: string
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function parseScope(params: URLSearchParams): Scope {
  const season = Number(params.get('season'))
  const dataset = params.get('dataset')
  return {
    season: Number.isInteger(season) && season >= 1999 && season <= 2100 ? season : null,
    datasetId: dataset && UUID_RE.test(dataset) ? dataset.toLowerCase() : null,
    team: (params.get('team') ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 5),
  }
}

/** Merge scope into existing params (other page params are kept). */
export function writeScope(params: URLSearchParams, scope: Scope): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const [key, value] of [
    ['season', scope.season === null || scope.datasetId ? '' : String(scope.season)],
    ['dataset', scope.datasetId ?? ''],
    ['team', scope.team],
  ] as const) {
    if (value) next.set(key, value)
    else next.delete(key)
  }
  return next
}

export function scopeQuery(scope: Scope): { season: number | null; datasetId: string | null } {
  return scope.datasetId
    ? { season: null, datasetId: scope.datasetId }
    : { season: scope.season, datasetId: null }
}

export function scopeLink(path: string, scope: Scope, extra: Record<string, string> = {}): string {
  const params = writeScope(new URLSearchParams(extra), scope)
  const text = params.toString()
  return text ? `${path}?${text}` : path
}
