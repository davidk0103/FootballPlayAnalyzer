import { describe, expect, it } from 'vitest'
import { DEFAULT_FILTERS } from '@/features/compare/filters'
import { formatDifference, formatValue, labelFor } from '@/lib/format'
import { readFilters, toAnalyticsQuery, writeFilters } from './filters'
import { parseScope, scopeLink, writeScope } from './scope'

const DATASET = '5a2d674e-3fd5-4926-9f5e-5923ff553e8f'

describe('scope', () => {
  it('parses and sanitizes season, dataset and team', () => {
    expect(parseScope(new URLSearchParams('season=2024&team=det'))).toEqual({ season: 2024, datasetId: null, team: 'DET' })
    expect(parseScope(new URLSearchParams('season=abc&dataset=../../etc&team=<b>KC</b>'))).toEqual({
      season: null,
      datasetId: null,
      team: 'BKCB',
    })
    expect(parseScope(new URLSearchParams(`dataset=${DATASET.toUpperCase()}`)).datasetId).toBe(DATASET)
  })

  it('drops the season when an upload is the source and keeps other params', () => {
    const params = writeScope(new URLSearchParams('group_by=qtr&season=2024'), { season: 2024, datasetId: DATASET, team: 'DET' })
    expect(params.get('season')).toBeNull()
    expect(params.get('dataset')).toBe(DATASET)
    expect(params.get('group_by')).toBe('qtr')
    expect(scopeLink('/reports', { season: 2024, datasetId: null, team: 'KC' }, { new: '1' })).toBe(
      '/reports?new=1&season=2024&team=KC',
    )
  })

  it('round-trips filters through the URL without touching scope', () => {
    const filters = { ...DEFAULT_FILTERS, side: 'defense' as const, down: [3, 4], fieldZone: 'red_zone' as const }
    const params = writeFilters(new URLSearchParams('team=KC&down=1'), filters)
    expect(params.get('team')).toBe('KC')
    expect(params.getAll('down')).toEqual(['3', '4'])
    expect(readFilters(params)).toEqual(filters)
    expect(toAnalyticsQuery({ season: null, datasetId: DATASET, team: 'KC' }, filters)).toMatchObject({
      season: null,
      datasetId: DATASET,
      side: 'defense',
      down: [3, 4],
      fieldZone: 'red_zone',
      qtr: undefined,
    })
  })
})

describe('format', () => {
  it('never shows a negative zero', () => {
    expect(formatValue('epa_per_play', -0.00004)).toBe('0.000')
    expect(formatValue('epa_per_play', 0.165)).toBe('+0.165')
    expect(formatValue('success_rate', -0.00001)).toBe('0.0%')
    expect(formatDifference('pass_rate', 0.00001)).toBe('0.0 pts')
    expect(formatDifference('epa_per_play', -0.048)).toBe('-0.048')
    expect(formatValue('yards_per_play', null)).toBe('n/a')
  })

  it('labels unknown keys readably', () => {
    expect(labelFor('epa_per_play')).toBe('EPA / play')
    expect(labelFor('epa_per_dropback')).toBe('EPA per dropback')
    expect(labelFor('red_zone')).toBe('Red zone')
  })
})
