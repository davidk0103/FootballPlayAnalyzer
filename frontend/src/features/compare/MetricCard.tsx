import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { Metric } from '@/services/api'
import { formatMetric, leader, type MetricMeta } from './metrics'

function Side({
  team,
  metric,
  meta,
  leads,
  accent,
}: {
  team: string
  metric: Metric
  meta: MetricMeta
  leads: boolean
  accent: 'a' | 'b'
}) {
  const missing = metric.value === null
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <span
          aria-hidden="true"
          className={cn('size-2 rounded-full', accent === 'a' ? 'bg-team-a' : 'bg-team-b')}
        />
        {team}
      </div>
      <div
        className={cn(
          'mt-0.5 text-2xl font-semibold tabular-nums tracking-tight',
          missing && 'text-muted-foreground',
          leads && 'text-emerald-600 dark:text-emerald-400',
        )}
        data-testid={`metric-${meta.key}-${accent}`}
      >
        {formatMetric(meta, metric)}
      </div>
      <div className="text-xs tabular-nums text-muted-foreground">
        {missing
          ? 'No qualifying plays'
          : `${Number.isInteger(metric.numerator) ? metric.numerator : metric.numerator.toFixed(1)} / ${metric.denominator}`}
      </div>
    </div>
  )
}

export function MetricCard({
  meta,
  teamA,
  teamB,
  a,
  b,
  side,
}: {
  meta: MetricMeta
  teamA: string
  teamB: string
  a: Metric
  b: Metric
  side: 'offense' | 'defense'
}) {
  const lead = leader(meta, a, b, side)
  return (
    <Card size="sm" aria-label={meta.label}>
      <CardContent>
        <h3 className="text-sm font-medium">{meta.label}</h3>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <Side team={teamA} metric={a} meta={meta} leads={lead === 'a'} accent="a" />
          <Side team={teamB} metric={b} meta={meta} leads={lead === 'b'} accent="b" />
        </div>
      </CardContent>
    </Card>
  )
}
