import { ArrowLeftRight, Database, TriangleAlert, Users } from 'lucide-react'
import { lazy, Suspense, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { FiltersPanel } from '@/features/compare/FiltersPanel'
import {
  type CompareState,
  type FilterValues,
  parseCompareParams,
  toComparisonQuery,
  toSearchParams,
} from '@/features/compare/filters'
import { MetricCard } from '@/features/compare/MetricCard'
import { MetricDefinitions } from '@/features/compare/MetricDefinitions'
import { METRICS } from '@/features/compare/metrics'
import { SampleSizeBadge } from '@/features/compare/SampleSizeBadge'
import { SeasonSelect } from '@/features/compare/SeasonSelect'
import { TeamSelect } from '@/features/compare/TeamSelect'
import { useSeasons, useTeams } from '@/hooks/useCatalog'
import { useTeamComparison } from '@/hooks/useTeamComparison'
import type { TeamComparison } from '@/services/api'

const ComparisonBarChart = lazy(() =>
  import('@/features/compare/ComparisonBarChart').then((m) => ({ default: m.ComparisonBarChart })),
)

function PickerSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-[1fr_auto_1fr_10rem]" aria-busy="true" aria-label="Loading teams">
      <Skeleton className="h-14" />
      <Skeleton className="hidden h-14 w-8 sm:block" />
      <Skeleton className="h-14" />
      <Skeleton className="h-14" />
    </div>
  )
}

function ResultsSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading comparison">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {METRICS.map((m) => (
          <Skeleton key={m.key} className="h-28" />
        ))}
      </div>
      <Skeleton className="h-80" />
    </div>
  )
}

function Results({ data, side }: { data: TeamComparison; side: 'offense' | 'defense' }) {
  const { team_a: a, team_b: b } = data
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <span className="flex items-center gap-2">
          <span className="font-medium">{a.team.name}</span>
          <SampleSizeBadge plays={a.sample.plays} games={a.sample.games} />
        </span>
        <span className="flex items-center gap-2">
          <span className="font-medium">{b.team.name}</span>
          <SampleSizeBadge plays={b.sample.plays} games={b.sample.games} />
        </span>
      </div>

      {data.warnings.length > 0 && (
        <Alert>
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Read with care</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4">
              {data.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <section aria-label="Metrics" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {METRICS.map((meta) => (
          <MetricCard
            key={meta.key}
            meta={meta}
            teamA={a.team.abbreviation}
            teamB={b.team.abbreviation}
            a={a.metrics[meta.key]}
            b={b.metrics[meta.key]}
            side={side}
          />
        ))}
      </section>

      <Suspense fallback={<Skeleton className="h-80" aria-label="Loading chart" />}>
        <ComparisonBarChart a={a} b={b} />
      </Suspense>
      <MetricDefinitions definitions={data.definitions} />

      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Database className="size-3.5" aria-hidden="true" />
        Source: {data.dataset.source}, release {data.dataset.version ?? 'unknown'}, sha256{' '}
        <span className="font-mono" title={data.dataset.sha256}>
          {data.dataset.sha256.slice(0, 12)}
        </span>
      </p>
    </div>
  )
}

export function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const state = useMemo(() => parseCompareParams(searchParams), [searchParams])
  const teams = useTeams()
  const seasons = useSeasons()

  const update = (patch: Partial<CompareState>) => {
    setSearchParams(toSearchParams({ ...state, ...patch }), { replace: true })
  }

  const latestSeason = seasons.data?.[0]?.season ?? null
  useEffect(() => {
    if (state.season === null && latestSeason !== null) {
      setSearchParams(toSearchParams({ ...state, season: latestSeason }), { replace: true })
    }
  }, [state, latestSeason, setSearchParams])

  const query = toComparisonQuery(state)
  const comparison = useTeamComparison(query)

  if (teams.isError || seasons.isError) {
    return (
      <ErrorState
        title="Could not load teams and seasons"
        error={teams.error ?? seasons.error}
        onRetry={() => {
          void teams.refetch()
          void seasons.refetch()
        }}
      />
    )
  }

  const catalogLoading = teams.isPending || seasons.isPending
  const noData = !catalogLoading && (seasons.data?.length ?? 0) === 0

  let results
  if (noData) {
    results = (
      <EmptyState title="No seasons imported yet" icon={<Database className="size-6 text-muted-foreground" />}>
        Load data with <code className="rounded bg-muted px-1">make ingest SEASONS=2023,2024</code>,
        then refresh this page.
      </EmptyState>
    )
  } else if (!state.teamA || !state.teamB) {
    results = (
      <EmptyState title="Pick two teams to compare" icon={<Users className="size-6 text-muted-foreground" />}>
        Choose a team on each side. Every number comes from real nflverse play-by-play data, with the
        sample size shown next to it.
      </EmptyState>
    )
  } else if (state.teamA === state.teamB) {
    results = (
      <EmptyState title="Choose two different teams">
        A team compared with itself is not much of a matchup.
      </EmptyState>
    )
  } else if (comparison.isError) {
    results = (
      <ErrorState
        title="Could not load the comparison"
        error={comparison.error}
        onRetry={() => void comparison.refetch()}
      />
    )
  } else if (comparison.data) {
    results = (
      <div className={comparison.isPlaceholderData ? 'opacity-60 transition-opacity' : undefined}>
        <Results data={comparison.data} side={comparison.data.filters.side === 'defense' ? 'defense' : 'offense'} />
      </div>
    )
  } else {
    results = <ResultsSkeleton />
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Team comparison</h1>
        <p className="mt-1 text-muted-foreground">
          Head-to-head efficiency on scrimmage plays, sliced by situation.
        </p>
      </div>

      <Card>
        <CardContent>
          {catalogLoading ? (
            <PickerSkeleton />
          ) : (
            <div className="grid items-end gap-4 sm:grid-cols-[1fr_auto_1fr_10rem]">
              <TeamSelect
                id="team-a"
                label="Team A"
                accent="a"
                teams={teams.data ?? []}
                value={state.teamA}
                disabledValue={state.teamB}
                onChange={(teamA) => update({ teamA })}
              />
              <Button
                variant="ghost"
                size="icon"
                aria-label="Swap teams"
                className="justify-self-center"
                disabled={!state.teamA && !state.teamB}
                onClick={() => update({ teamA: state.teamB, teamB: state.teamA })}
              >
                <ArrowLeftRight aria-hidden="true" />
              </Button>
              <TeamSelect
                id="team-b"
                label="Team B"
                accent="b"
                teams={teams.data ?? []}
                value={state.teamB}
                disabledValue={state.teamA}
                onChange={(teamB) => update({ teamB })}
              />
              <SeasonSelect
                seasons={seasons.data ?? []}
                value={state.season}
                onChange={(season) => update({ season })}
              />
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <FiltersPanel
            value={state.filters}
            onApply={(filters: FilterValues) => update({ filters })}
          />
        </aside>
        <div className="min-w-0">{results}</div>
      </div>
    </div>
  )
}
