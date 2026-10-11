import { Database } from 'lucide-react'
import { lazy, Suspense, useCallback, useMemo } from 'react'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { readFilters, toAnalyticsQuery, writeFilters } from '@/features/analytics/filters'
import { DatasetFooter, Definitions, Warnings } from '@/features/analytics/parts'
import { ScopePicker } from '@/features/analytics/ScopePicker'
import { parseScope, scopeQuery, writeScope, type Scope } from '@/features/analytics/scope'
import { TendencyGrid, ThirdDownCard } from '@/features/analytics/TendencyGrid'
import { FiltersPanel } from '@/features/compare/FiltersPanel'
import { MIN_SAMPLE } from '@/features/compare/SampleSizeBadge'
import { useSituational, useTendencies } from '@/hooks/useAnalytics'
import { useSeasons } from '@/hooks/useCatalog'
import { useUrlParams } from '@/hooks/useUrlParams'
import { formatDifference, formatValue, METRIC_LABELS } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { GroupBy, Situational } from '@/services/api'

const SituationChart = lazy(() =>
  import('@/features/analytics/charts').then((m) => ({ default: m.SituationChart })),
)

const GROUP_BY_LABELS: Record<GroupBy, string> = {
  down: 'Down',
  distance: 'Distance to go',
  field_zone: 'Field position',
  qtr: 'Quarter',
  score_state: 'Score margin',
  play_type: 'Play type',
}
const GROUPS = Object.keys(GROUP_BY_LABELS) as GroupBy[]
const METRICS = ['epa_per_play', 'success_rate', 'yards_per_play', 'pass_rate', 'first_down_rate', 'explosive_play_rate']

function parseGroup(raw: string | null): GroupBy {
  return GROUPS.includes(raw as GroupBy) ? (raw as GroupBy) : 'down'
}

function SituationTable({ data, metric }: { data: Situational; metric: string }) {
  const hasTeam = data.team !== null
  const rows = [...data.rows, { ...data.overall, label: 'All situations', key: '__all' }]
  return (
    <Table aria-label="Situational breakdown">
      <TableHeader>
        <TableRow>
          <TableHead>{GROUP_BY_LABELS[data.group_by as GroupBy] ?? data.group_by}</TableHead>
          <TableHead className="text-right">Plays</TableHead>
          <TableHead className="text-right">{METRIC_LABELS[metric]}</TableHead>
          {hasTeam && <TableHead className="text-right">League</TableHead>}
          {hasTeam && <TableHead className="text-right">Difference</TableHead>}
          <TableHead className="hidden text-right md:table-cell">Sample</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody className="tabular-nums">
        {rows.map((r) => {
          const m = r.metrics[metric]
          const lg = r.league?.[metric]
          const diff = m?.value != null && lg?.value != null ? m.value - lg.value : null
          return (
            <TableRow key={r.key} className={cn(r.key === '__all' && 'font-medium', r.plays < MIN_SAMPLE && 'text-muted-foreground')}>
              <TableCell>
                {r.label}
                {r.plays > 0 && r.plays < MIN_SAMPLE && <span className="ml-1 text-xs">(small sample)</span>}
              </TableCell>
              <TableCell className="text-right">{r.plays.toLocaleString()}</TableCell>
              <TableCell className="text-right" data-testid={`row-${r.key}-value`}>
                {formatValue(metric, m?.value)}
              </TableCell>
              {hasTeam && <TableCell className="text-right text-muted-foreground">{formatValue(metric, lg?.value)}</TableCell>}
              {hasTeam && <TableCell className="text-right">{formatDifference(metric, diff) || 'n/a'}</TableCell>}
              <TableCell className="hidden text-right text-muted-foreground md:table-cell">
                {m ? `${Number.isInteger(m.numerator) ? m.numerator : m.numerator.toFixed(1)} / ${m.denominator}` : 'n/a'}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

export function SituationalPage() {
  const [params, setParams] = useUrlParams()
  const scope = useMemo(() => parseScope(params), [params])
  const filters = useMemo(() => readFilters(params), [params])
  const groupBy = parseGroup(params.get('group_by'))
  const metric = METRICS.includes(params.get('metric') ?? '') ? (params.get('metric') as string) : 'epa_per_play'
  const seasons = useSeasons()

  const setScope = useCallback(
    (next: Scope) => setParams((p) => writeScope(p, next)),
    [setParams],
  )
  const setParam = (key: string, value: string) =>
    setParams((p) => {
      const next = new URLSearchParams(p)
      next.set(key, value)
      return next
    })

  const query = toAnalyticsQuery(scope, filters)
  const situational = useSituational({ ...query, team: scope.team || null, groupBy })
  const tendencies = useTendencies({ ...scopeQuery(scope), side: filters.side, team: scope.team })

  let results
  if (!seasons.isPending && (seasons.data?.length ?? 0) === 0 && !scope.datasetId) {
    results = (
      <EmptyState title="No seasons imported yet" icon={<Database className="size-6 text-muted-foreground" />}>
        Import a season from the Jobs page (admins), or upload your own play-by-play CSV.
      </EmptyState>
    )
  } else if (situational.isError) {
    results = (
      <ErrorState
        title="Could not load the situational breakdown"
        error={situational.error}
        onRetry={() => void situational.refetch()}
      />
    )
  } else if (!situational.data) {
    results = (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading situations">
        <Skeleton className="h-72" />
        <Skeleton className="h-64" />
      </div>
    )
  } else if (situational.data.overall.plays === 0) {
    results = (
      <EmptyState title="No plays match these filters">
        Loosen a filter (for example, clear the quarter or field position) to see results.
      </EmptyState>
    )
  } else {
    const data = situational.data
    const teamLabel = data.team?.abbreviation ?? null
    results = (
      <div className={cn('flex flex-col gap-6', situational.isPlaceholderData && 'opacity-60 transition-opacity')}>
        <Warnings warnings={data.warnings} />
        <Card>
          <CardHeader>
            <CardTitle>
              {METRIC_LABELS[metric]} by {GROUP_BY_LABELS[groupBy].toLowerCase()}
            </CardTitle>
            <CardDescription>
              {teamLabel
                ? `${data.team?.name ?? teamLabel} ${filters.side === 'defense' ? 'defense (plays allowed)' : 'offense'} against the league.`
                : `League-wide, ${filters.side === 'defense' ? 'from the defense side' : 'all offenses'}.`}{' '}
              {data.overall.plays.toLocaleString()} plays in {data.overall.games} games.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <Suspense fallback={<Skeleton className="h-72" aria-label="Loading chart" />}>
              <SituationChart rows={data.rows} metric={metric} teamLabel={teamLabel} />
            </Suspense>
            <SituationTable data={data} metric={metric} />
          </CardContent>
        </Card>
        {scope.team &&
          (tendencies.isError ? (
            <ErrorState title="Could not load tendencies" error={tendencies.error} onRetry={() => void tendencies.refetch()} />
          ) : tendencies.data ? (
            <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
              <TendencyGrid cells={tendencies.data.down_distance} />
              <ThirdDownCard data={tendencies.data.third_down} />
            </div>
          ) : (
            <Skeleton className="h-64" aria-label="Loading tendencies" />
          ))}
        <Definitions definitions={data.definitions} keys={METRICS} />
        <DatasetFooter dataset={data.dataset} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Situational explorer</h1>
        <p className="mt-1 text-muted-foreground">
          How a team, or the whole league, performs by down, distance, field position, quarter and score.
        </p>
      </div>
      <Card>
        <CardContent className="flex flex-col gap-4">
          <ScopePicker scope={scope} onChange={setScope} teamOptional />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="group-by">Break down by</Label>
              <NativeSelect id="group-by" className="w-full" value={groupBy} onChange={(e) => setParam('group_by', e.target.value)}>
                {GROUPS.map((g) => (
                  <NativeSelectOption key={g} value={g}>
                    {GROUP_BY_LABELS[g]}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="metric">Metric</Label>
              <NativeSelect id="metric" className="w-full" value={metric} onChange={(e) => setParam('metric', e.target.value)}>
                {METRICS.map((m) => (
                  <NativeSelectOption key={m} value={m}>
                    {METRIC_LABELS[m]}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <FiltersPanel value={filters} onApply={(f) => setParams((p) => writeFilters(p, f))} />
        </aside>
        <div className="min-w-0">{results}</div>
      </div>
    </div>
  )
}
