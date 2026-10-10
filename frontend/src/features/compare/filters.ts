import { z } from 'zod'
import type { ComparisonQuery } from '@/services/api'

export const SIDES = ['offense', 'defense'] as const
export const SEASON_TYPES = ['REG', 'POST'] as const
export const DISTANCES = ['short', 'medium', 'long'] as const
export const FIELD_ZONES = ['own_deep', 'own', 'opp', 'red_zone'] as const
export const PLAY_TYPES = ['pass', 'run'] as const
export const DOWNS = [1, 2, 3, 4] as const
export const QUARTERS = [1, 2, 3, 4, 5] as const

export const DISTANCE_LABELS: Record<(typeof DISTANCES)[number], string> = {
  short: 'Short (1-3 yds)',
  medium: 'Medium (4-7 yds)',
  long: 'Long (8+ yds)',
}
export const FIELD_ZONE_LABELS: Record<(typeof FIELD_ZONES)[number], string> = {
  own_deep: 'Own deep (own 1-20)',
  own: 'Own territory (own 21-50)',
  opp: 'Opponent territory (opp 49-21)',
  red_zone: 'Red zone (opp 20-1)',
}

const optional = <T extends readonly [string, ...string[]]>(values: T) =>
  z.union([z.enum(values), z.literal('')])

export const filtersSchema = z.object({
  side: z.enum(SIDES),
  seasonType: optional(SEASON_TYPES),
  down: z.array(z.number().int().min(1).max(4)),
  distance: optional(DISTANCES),
  fieldZone: optional(FIELD_ZONES),
  qtr: z.array(z.number().int().min(1).max(5)),
  playType: optional(PLAY_TYPES),
})

export type FilterValues = z.infer<typeof filtersSchema>

export const DEFAULT_FILTERS: FilterValues = {
  side: 'offense',
  seasonType: '',
  down: [],
  distance: '',
  fieldZone: '',
  qtr: [],
  playType: '',
}

export interface CompareState {
  teamA: string
  teamB: string
  season: number | null
  filters: FilterValues
}

function pick<T extends string>(values: readonly T[], raw: string | null): T | '' {
  return raw !== null && (values as readonly string[]).includes(raw) ? (raw as T) : ''
}

function numbers(raw: string[], allowed: readonly number[]): number[] {
  const out = new Set<number>()
  for (const value of raw) {
    const n = Number(value)
    if (allowed.includes(n)) out.add(n)
  }
  return [...out].sort((a, b) => a - b)
}

/** Read compare state from URL search params, dropping anything invalid. */
export function parseCompareParams(params: URLSearchParams): CompareState {
  const seasonRaw = Number(params.get('season'))
  return {
    teamA: (params.get('team_a') ?? '').toUpperCase(),
    teamB: (params.get('team_b') ?? '').toUpperCase(),
    season: Number.isInteger(seasonRaw) && seasonRaw >= 1999 ? seasonRaw : null,
    filters: {
      side: pick(SIDES, params.get('side')) || 'offense',
      seasonType: pick(SEASON_TYPES, params.get('season_type')),
      down: numbers(params.getAll('down'), DOWNS),
      distance: pick(DISTANCES, params.get('distance')),
      fieldZone: pick(FIELD_ZONES, params.get('field_zone')),
      qtr: numbers(params.getAll('qtr'), QUARTERS),
      playType: pick(PLAY_TYPES, params.get('play_type')),
    },
  }
}

export function toSearchParams(state: CompareState): URLSearchParams {
  const p = new URLSearchParams()
  if (state.teamA) p.set('team_a', state.teamA)
  if (state.teamB) p.set('team_b', state.teamB)
  if (state.season !== null) p.set('season', String(state.season))
  const f = state.filters
  if (f.side !== 'offense') p.set('side', f.side)
  if (f.seasonType) p.set('season_type', f.seasonType)
  for (const d of f.down) p.append('down', String(d))
  if (f.distance) p.set('distance', f.distance)
  if (f.fieldZone) p.set('field_zone', f.fieldZone)
  for (const q of f.qtr) p.append('qtr', String(q))
  if (f.playType) p.set('play_type', f.playType)
  return p
}

export function toComparisonQuery(state: CompareState): ComparisonQuery | null {
  if (!state.teamA || !state.teamB || state.season === null || state.teamA === state.teamB) {
    return null
  }
  const f = state.filters
  return {
    teamA: state.teamA,
    teamB: state.teamB,
    season: state.season,
    side: f.side,
    seasonType: f.seasonType || undefined,
    down: f.down.length ? f.down : undefined,
    distance: f.distance || undefined,
    fieldZone: f.fieldZone || undefined,
    qtr: f.qtr.length ? f.qtr : undefined,
    playType: f.playType || undefined,
  }
}

export function activeFilterCount(f: FilterValues): number {
  return (
    Number(f.side !== 'offense') +
    Number(Boolean(f.seasonType)) +
    Number(f.down.length > 0) +
    Number(Boolean(f.distance)) +
    Number(Boolean(f.fieldZone)) +
    Number(f.qtr.length > 0) +
    Number(Boolean(f.playType))
  )
}
