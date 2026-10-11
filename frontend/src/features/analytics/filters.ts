import { parseCompareParams, toSearchParams, type FilterValues } from '@/features/compare/filters'
import type { AnalyticsQuery } from '@/services/api'
import { scopeQuery, type Scope } from './scope'

const FILTER_KEYS = ['side', 'season_type', 'down', 'distance', 'field_zone', 'qtr', 'play_type']

export function readFilters(params: URLSearchParams): FilterValues {
  return parseCompareParams(params).filters
}

/** Replace the filter params, keeping everything else (scope, page-specific params). */
export function writeFilters(params: URLSearchParams, filters: FilterValues): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const key of FILTER_KEYS) next.delete(key)
  const written = toSearchParams({ teamA: '', teamB: '', season: null, filters })
  for (const [key, value] of written) next.append(key, value)
  return next
}

export function toAnalyticsQuery(scope: Scope, f: FilterValues): AnalyticsQuery {
  return {
    ...scopeQuery(scope),
    side: f.side,
    seasonType: f.seasonType || undefined,
    down: f.down.length ? f.down : undefined,
    distance: f.distance || undefined,
    fieldZone: f.fieldZone || undefined,
    qtr: f.qtr.length ? f.qtr : undefined,
    playType: f.playType || undefined,
  }
}
