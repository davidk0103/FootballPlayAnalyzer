import { describe, expect, it } from 'vitest'
import { formatMetric, leader, METRICS } from './metrics'

const meta = (key: string) => {
  const found = METRICS.find((m) => m.key === key)
  if (!found) throw new Error(key)
  return found
}
const m = (value: number | null) => ({ value, numerator: 0, denominator: value === null ? 0 : 10 })

describe('metric formatting', () => {
  it('formats values and shows n/a for null, never 0', () => {
    expect(formatMetric(meta('epa_per_play'), m(0.0625))).toBe('+0.063')
    expect(formatMetric(meta('epa_per_play'), m(-0.1))).toBe('-0.100')
    expect(formatMetric(meta('success_rate'), m(0.4734))).toBe('47.3%')
    expect(formatMetric(meta('success_rate'), m(null))).toBe('n/a')
  })
})

describe('leader', () => {
  it('higher wins on offense, lower wins on defense', () => {
    expect(leader(meta('success_rate'), m(0.5), m(0.4), 'offense')).toBe('a')
    expect(leader(meta('success_rate'), m(0.5), m(0.4), 'defense')).toBe('b')
  })

  it('fewer turnovers is better on offense', () => {
    expect(leader(meta('turnovers_per_game'), m(1.2), m(0.6), 'offense')).toBe('b')
  })

  it('has no leader for neutral metrics, ties, or missing values', () => {
    expect(leader(meta('pass_rate'), m(0.6), m(0.4), 'offense')).toBeNull()
    expect(leader(meta('success_rate'), m(0.4), m(0.4), 'offense')).toBeNull()
    expect(leader(meta('success_rate'), m(null), m(0.4), 'offense')).toBeNull()
  })
})
