import type { Metric, MetricKey } from '@/services/api'

export interface MetricMeta {
  key: MetricKey
  label: string
  /** Compact label for chart axes. */
  short: string
  format: (value: number) => string
  /** Better direction from the offense's point of view; null = neutral (style, not quality). */
  higherIsBetter: boolean | null
  chart: boolean
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`
const signed = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(3)}`

export const METRICS: MetricMeta[] = [
  { key: 'epa_per_play', short: 'EPA', label: 'EPA / play', format: signed, higherIsBetter: true, chart: false },
  { key: 'success_rate', short: 'Success', label: 'Success rate', format: pct, higherIsBetter: true, chart: true },
  {
    key: 'yards_per_play',
    short: 'Yds/play',
    label: 'Yards / play',
    format: (v) => v.toFixed(2),
    higherIsBetter: true,
    chart: false,
  },
  {
    key: 'third_down_conversion_rate',
    short: '3rd down',
    label: '3rd-down conversion',
    format: pct,
    higherIsBetter: true,
    chart: true,
  },
  {
    key: 'explosive_play_rate',
    short: 'Explosive',
    label: 'Explosive play rate',
    format: pct,
    higherIsBetter: true,
    chart: true,
  },
  {
    key: 'turnovers_per_game',
    short: 'TO/game',
    label: 'Turnovers / game',
    format: (v) => v.toFixed(2),
    higherIsBetter: false,
    chart: false,
  },
  { key: 'pass_rate', short: 'Pass rate', label: 'Pass rate', format: pct, higherIsBetter: null, chart: true },
]

export function formatMetric(meta: MetricMeta, metric: Metric): string {
  return metric.value === null ? 'n/a' : meta.format(metric.value)
}

/** Which side leads on a metric: 'a', 'b', or null (tie, neutral metric, or missing value). */
export function leader(
  meta: MetricMeta,
  a: Metric,
  b: Metric,
  side: 'offense' | 'defense',
): 'a' | 'b' | null {
  if (meta.higherIsBetter === null || a.value === null || b.value === null) return null
  if (a.value === b.value) return null
  const higherWins = side === 'offense' ? meta.higherIsBetter : !meta.higherIsBetter
  return (a.value > b.value) === higherWins ? 'a' : 'b'
}
