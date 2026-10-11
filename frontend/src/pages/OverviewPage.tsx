import { ArrowRight, Database, Shield, Swords } from 'lucide-react'
import { lazy, Suspense, useCallback, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { DatasetFooter, Definitions, StatTile, Warnings } from '@/features/analytics/parts'
import { ScopePicker } from '@/features/analytics/ScopePicker'
import { parseScope, scopeLink, scopeQuery, writeScope, type Scope } from '@/features/analytics/scope'
import { ThirdDownCard } from '@/features/analytics/TendencyGrid'
import { formatValue } from '@/lib/format'
import { SampleSizeBadge } from '@/features/compare/SampleSizeBadge'
import { useEfficiency, useTendencies, useTrends } from '@/hooks/useAnalytics'
import { useSeasons } from '@/hooks/useCatalog'
import type { Efficiency, Metric, Side } from '@/services/api'

const TrendChart = lazy(() => import('@/features/analytics/charts').then((m) => ({ default: m.TrendChart })))

const TILE_METRICS = ['epa_per_play', 'success_rate', 'yards_per_play', 'explosive_play_rate', 'pass_rate'] as const

function better(metric: string, side: Side): 'higher' | 'lower' | null {
  if (metric === 'pass_rate') return null
  return side === 'offense' ? 'higher' : 'lower'
}

function SidePanel({ data, side }: { data: Efficiency; side: Side }) {
  const all = data.splits.find((s) => s.key === 'all')
  if (!all) return null
  const Icon = side === 'offense' ? Swords : Shield
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <Icon className="size-4" aria-hidden="true" />
          {side === 'offense' ? 'Offense' : 'Defense'}
          <SampleSizeBadge plays={all.plays} games={all.games} />
        </CardTitle>
        <CardDescription>
          {side === 'offense' ? 'Plays this team ran.' : 'Plays this team allowed (lower is better).'}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label={`${side} metrics`}>
          {TILE_METRICS.filter((m) => all.metrics[m]).map((m) => (
            <StatTile
              key={m}
              name={m}
              metric={all.metrics[m] as Metric}
              league={all.league[m]}
              rank={m === 'epa_per_play' && all.rank ? all.rank : null}
              better={better(m, side)}
            />
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" aria-label={`${side} pass and run split`}>
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1 font-medium">Split</th>
                <th className="py-1 text-right font-medium">Plays</th>
                <th className="py-1 text-right font-medium">EPA / play</th>
                <th className="py-1 text-right font-medium">League</th>
                <th className="py-1 text-right font-medium">Success</th>
                <th className="py-1 text-right font-medium">Rank (EPA)</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {data.splits.map((s) => (
                <tr key={s.key} className="border-t">
                  <td className="py-1.5">{s.label}</td>
                  <td className="py-1.5 text-right">{s.plays.toLocaleString()}</td>
                  <td className="py-1.5 text-right">{formatValue('epa_per_play', s.metrics.epa_per_play?.value)}</td>
                  <td className="py-1.5 text-right text-muted-foreground">{formatValue('epa_per_play', s.league.epa_per_play?.value)}</td>
                  <td className="py-1.5 text-right">{formatValue('success_rate', s.metrics.success_rate?.value)}</td>
                  <td className="py-1.5 text-right">{s.rank ? `${s.rank.rank} of ${s.rank.of}` : 'n/a'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

export function OverviewPage() {
  const [params, setParams] = useSearchParams()
  const scope = useMemo(() => parseScope(params), [params])
  const setScope = useCallback(
    (next: Scope) => setParams((p) => writeScope(p, next), { replace: true }),
    [setParams],
  )
  const seasons = useSeasons()
  const base = { ...scopeQuery(scope), team: scope.team }
  const offense = useEfficiency({ ...base, side: 'offense' })
  const defense = useEfficiency({ ...base, side: 'defense' })
  const trends = useTrends({ ...base, side: 'offense' })
  const tendencies = useTendencies({ ...base, side: 'offense' })

  let body
  if (!seasons.isPending && (seasons.data?.length ?? 0) === 0 && !scope.datasetId) {
    body = (
      <EmptyState title="No seasons imported yet" icon={<Database className="size-6 text-muted-foreground" />}>
        Import a season from the Jobs page (admins), or upload your own play-by-play CSV.
      </EmptyState>
    )
  } else if (!scope.team) {
    body = (
      <EmptyState title="Choose a team">
        Pick a team to see its offense and defense against the league, game by game.
      </EmptyState>
    )
  } else if (offense.isError || defense.isError) {
    body = (
      <ErrorState
        title="Could not load the team overview"
        error={offense.error ?? defense.error}
        onRetry={() => {
          void offense.refetch()
          void defense.refetch()
        }}
      />
    )
  } else if (!offense.data || !defense.data) {
    body = (
      <div className="grid gap-4 xl:grid-cols-2" aria-busy="true" aria-label="Loading overview">
        <Skeleton className="h-96" />
        <Skeleton className="h-96" />
      </div>
    )
  } else {
    const name = offense.data.team.name ?? offense.data.team.abbreviation
    body = (
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold tracking-tight">{name}</h2>
          <div className="flex flex-wrap gap-2">
            <Link to={scopeLink('/situational', scope)} className={buttonVariants({ variant: 'outline', size: 'sm' })}>
              Situational breakdown <ArrowRight aria-hidden="true" />
            </Link>
            <Link
              to={scopeLink('/reports', scope, { new: '1' })}
              className={buttonVariants({ variant: 'outline', size: 'sm' })}
            >
              Scouting report <ArrowRight aria-hidden="true" />
            </Link>
          </div>
        </div>
        <Warnings warnings={[...new Set([...offense.data.warnings, ...defense.data.warnings])]} />
        <div className="grid gap-4 xl:grid-cols-2">
          <SidePanel data={offense.data} side="offense" />
          <SidePanel data={defense.data} side="defense" />
        </div>
        <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
          <Card>
            <CardHeader>
              <CardTitle>Offensive EPA per play, game by game</CardTitle>
              <CardDescription>Dashed line: league average for the same week.</CardDescription>
            </CardHeader>
            <CardContent>
              {trends.isError ? (
                <ErrorState title="Could not load trends" error={trends.error} onRetry={() => void trends.refetch()} />
              ) : trends.data ? (
                trends.data.games.length === 0 ? (
                  <EmptyState title="No games match these filters" />
                ) : (
                  <Suspense fallback={<Skeleton className="h-64" />}>
                    <TrendChart data={trends.data} team={scope.team} />
                  </Suspense>
                )
              ) : (
                <Skeleton className="h-64" aria-label="Loading trends" />
              )}
            </CardContent>
          </Card>
          {tendencies.isError ? (
            <ErrorState title="Could not load third downs" error={tendencies.error} onRetry={() => void tendencies.refetch()} />
          ) : tendencies.data ? (
            <ThirdDownCard data={tendencies.data.third_down} />
          ) : (
            <Skeleton className="h-64" aria-label="Loading third downs" />
          )}
        </div>
        <Definitions definitions={offense.data.definitions} />
        <DatasetFooter dataset={offense.data.dataset} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Team overview</h1>
        <p className="mt-1 text-muted-foreground">
          Offense and defense efficiency, ranked against the league, with every sample size shown.
        </p>
      </div>
      <Card>
        <CardContent>
          <ScopePicker scope={scope} onChange={setScope} />
        </CardContent>
      </Card>
      {body}
    </div>
  )
}
