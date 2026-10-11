import { Database, Info, TriangleAlert } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { formatDifference, formatMetric, formatValue, fraction, METRIC_LABELS } from '@/lib/format'
import type { Dataset, Metric } from '@/services/api'

export function Warnings({ warnings, title = 'Read with care' }: { warnings: string[]; title?: string }) {
  if (warnings.length === 0) return null
  return (
    <Alert>
      <TriangleAlert aria-hidden="true" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <ul className="list-disc pl-4">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  )
}

export function DatasetFooter({ dataset }: { dataset: Dataset }) {
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <Database className="size-3.5" aria-hidden="true" />
      {dataset.kind === 'upload' ? (
        <>Your upload “{dataset.name}”, processed {dataset.version ? new Date(dataset.version).toLocaleString() : 'n/a'}</>
      ) : (
        <>Source: {dataset.source}, release {dataset.version ?? 'unknown'}</>
      )}
      , sha256{' '}
      <span className="font-mono" title={dataset.sha256}>
        {dataset.sha256.slice(0, 12)}
      </span>
    </p>
  )
}

export function Definitions({
  definitions,
  keys,
  title = 'How these are calculated',
}: {
  definitions: Record<string, string>
  keys?: string[]
  title?: string
}) {
  const entries = (keys ?? Object.keys(definitions)).filter((k) => definitions[k])
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Info className="size-4" aria-hidden="true" /> {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          {entries.map((k) => (
            <div key={k}>
              <dt className="font-medium">{METRIC_LABELS[k] ?? k.replaceAll('_', ' ')}</dt>
              <dd className="text-muted-foreground">{definitions[k]}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}

/** One metric with its league comparison. ``better`` decides the color of the difference. */
export function StatTile({
  name,
  label,
  metric,
  league,
  rank,
  better,
}: {
  name: string
  label?: string
  metric: Metric
  league?: Metric | number | null
  rank?: { rank: number; of: number } | null
  better?: 'higher' | 'lower' | null
}) {
  const leagueValue = typeof league === 'number' || league === null || league === undefined ? league : league.value
  const diff = metric.value !== null && leagueValue !== null && leagueValue !== undefined ? metric.value - leagueValue : null
  const good = diff === null || !better || diff === 0 ? null : (diff > 0) === (better === 'higher')
  return (
    <Card size="sm" aria-label={label ?? METRIC_LABELS[name] ?? name}>
      <CardContent>
        <h3 className="text-sm font-medium text-muted-foreground">{label ?? METRIC_LABELS[name] ?? name}</h3>
        <div
          className={cn('mt-1 text-2xl font-semibold tabular-nums tracking-tight', metric.value === null && 'text-muted-foreground')}
          data-testid={`stat-${name}`}
        >
          {formatMetric(name, metric)}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs tabular-nums text-muted-foreground">
          {metric.value === null ? <span>No qualifying plays</span> : <span>{fraction(metric)}</span>}
          {leagueValue !== undefined && (
            <span>
              League {formatValue(name, leagueValue)}
              {diff !== null && (
                <span
                  className={cn(
                    'ml-1',
                    good === true && 'text-emerald-600 dark:text-emerald-400',
                    good === false && 'text-rose-600 dark:text-rose-400',
                  )}
                >
                  ({formatDifference(name, diff)})
                </span>
              )}
            </span>
          )}
          {rank && (
            <span>
              Rank {rank.rank} of {rank.of}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
