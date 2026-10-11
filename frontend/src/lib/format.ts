import type { Metric } from '@/services/api'

/** Format a metric value by its name: rates as %, EPA signed to 3 places, others to 2. */
export function formatValue(name: string, value: number | null | undefined): string {
  if (value === null || value === undefined) return 'n/a'
  if (name.endsWith('_rate')) return `${(value * 100).toFixed(1)}%`
  if (name.startsWith('epa')) return `${value > 0 ? '+' : ''}${value.toFixed(3)}`
  if (Number.isInteger(value)) return value.toLocaleString()
  return value.toFixed(2)
}

export function formatMetric(name: string, metric: Metric | null | undefined): string {
  return formatValue(name, metric?.value)
}

/** "123 / 456" sample fraction shown under a metric (numerator may be fractional, e.g. EPA). */
export function fraction(metric: Metric): string {
  const n = Number.isInteger(metric.numerator) ? metric.numerator : metric.numerator.toFixed(1)
  return `${n} / ${metric.denominator.toLocaleString()}`
}

export function formatDifference(name: string, diff: number | null | undefined): string {
  if (diff === null || diff === undefined) return ''
  if (name.endsWith('_rate')) return `${diff > 0 ? '+' : ''}${(diff * 100).toFixed(1)} pts`
  if (name.startsWith('epa')) return `${diff > 0 ? '+' : ''}${diff.toFixed(3)}`
  return `${diff > 0 ? '+' : ''}${diff.toFixed(2)}`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export const METRIC_LABELS: Record<string, string> = {
  epa_per_play: 'EPA / play',
  success_rate: 'Success rate',
  yards_per_play: 'Yards / play',
  pass_rate: 'Pass rate',
  first_down_rate: 'First-down rate',
  explosive_play_rate: 'Explosive play rate',
  third_down_conversion_rate: '3rd-down conversion',
  turnovers_per_game: 'Turnovers / game',
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID()
}
