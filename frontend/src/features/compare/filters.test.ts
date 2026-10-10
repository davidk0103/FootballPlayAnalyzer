import { describe, expect, it } from 'vitest'
import {
  activeFilterCount,
  DEFAULT_FILTERS,
  filtersSchema,
  parseCompareParams,
  toComparisonQuery,
  toSearchParams,
} from './filters'

describe('compare URL state', () => {
  it('round-trips through search params', () => {
    const state = {
      teamA: 'KC',
      teamB: 'PHI',
      season: 2024,
      filters: {
        ...DEFAULT_FILTERS,
        side: 'defense' as const,
        down: [3, 4],
        distance: 'long' as const,
        qtr: [4],
        playType: 'pass' as const,
      },
    }
    const params = toSearchParams(state)
    expect(params.toString()).toBe(
      'team_a=KC&team_b=PHI&season=2024&side=defense&down=3&down=4&distance=long&qtr=4&play_type=pass',
    )
    expect(parseCompareParams(params)).toEqual(state)
  })

  it('drops invalid values instead of passing them to the API', () => {
    const state = parseCompareParams(
      new URLSearchParams('team_a=kc&season=abc&down=9&down=2&distance=far&qtr=0&side=both'),
    )
    expect(state.teamA).toBe('KC')
    expect(state.season).toBeNull()
    expect(state.filters.down).toEqual([2])
    expect(state.filters.distance).toBe('')
    expect(state.filters.qtr).toEqual([])
    expect(state.filters.side).toBe('offense')
  })

  it('builds no query until two different teams and a season are chosen', () => {
    const base = { teamA: 'KC', teamB: '', season: 2024, filters: DEFAULT_FILTERS }
    expect(toComparisonQuery(base)).toBeNull()
    expect(toComparisonQuery({ ...base, teamB: 'KC' })).toBeNull()
    expect(toComparisonQuery({ ...base, teamB: 'BUF', season: null })).toBeNull()
    expect(toComparisonQuery({ ...base, teamB: 'BUF' })).toEqual({
      teamA: 'KC',
      teamB: 'BUF',
      season: 2024,
      side: 'offense',
      seasonType: undefined,
      down: undefined,
      distance: undefined,
      fieldZone: undefined,
      qtr: undefined,
      playType: undefined,
    })
  })

  it('counts active filters', () => {
    expect(activeFilterCount(DEFAULT_FILTERS)).toBe(0)
    expect(activeFilterCount({ ...DEFAULT_FILTERS, down: [1, 2], fieldZone: 'red_zone' })).toBe(2)
  })

  it('validates with zod', () => {
    expect(filtersSchema.safeParse(DEFAULT_FILTERS).success).toBe(true)
    expect(filtersSchema.safeParse({ ...DEFAULT_FILTERS, down: [5] }).success).toBe(false)
    expect(filtersSchema.safeParse({ ...DEFAULT_FILTERS, distance: 'far' }).success).toBe(false)
  })
})
