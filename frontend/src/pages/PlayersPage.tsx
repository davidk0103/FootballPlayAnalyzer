import { Search, UserRound, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Skeleton } from '@/components/ui/skeleton'
import { DatasetFooter, Definitions, Warnings } from '@/features/analytics/parts'
import { SampleSizeBadge } from '@/features/compare/SampleSizeBadge'
import { usePlayerSearch, usePlayerStats } from '@/hooks/useAnalytics'
import { useSeasons } from '@/hooks/useCatalog'
import { useDebounced } from '@/hooks/useDebounced'
import { formatValue } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Metric, PlayerStats } from '@/services/api'

const POSITIONS = ['QB', 'RB', 'WR', 'TE', 'FB']
const MAX_COMPARE = 2

const PLAYER_STAT_LABELS: Record<string, string> = {
  pass_attempts: 'Pass attempts',
  completions: 'Completions',
  completion_rate: 'Completion rate',
  passing_yards: 'Passing yards',
  yards_per_attempt: 'Yards / attempt',
  passing_touchdowns: 'Passing TDs',
  interceptions: 'Interceptions',
  sacks: 'Sacks taken',
  epa_per_dropback: 'EPA / dropback',
  rush_attempts: 'Rush attempts',
  rushing_yards: 'Rushing yards',
  yards_per_carry: 'Yards / carry',
  rushing_touchdowns: 'Rushing TDs',
  epa_per_rush: 'EPA / rush',
  targets: 'Targets',
  receptions: 'Receptions',
  catch_rate: 'Catch rate',
  receiving_yards: 'Receiving yards',
  yards_per_target: 'Yards / target',
  receiving_touchdowns: 'Receiving TDs',
  epa_per_target: 'EPA / target',
}

const CATEGORIES = [
  { key: 'passing', label: 'Passing', volume: 'pass_attempts' },
  { key: 'rushing', label: 'Rushing', volume: 'rush_attempts' },
  { key: 'receiving', label: 'Receiving', volume: 'targets' },
] as const

type StatValue = number | Metric

function display(key: string, value: StatValue | undefined): string {
  if (value === undefined) return 'n/a'
  if (typeof value === 'number') return value.toLocaleString()
  return formatValue(key, value.value)
}

function denominator(value: StatValue | undefined): string | null {
  return value !== undefined && typeof value !== 'number' && value.value !== null
    ? `${value.denominator.toLocaleString()}`
    : null
}

function PlayerSearchPanel({
  season,
  selected,
  onAdd,
}: {
  season: number | null
  selected: string[]
  onAdd: (id: string) => void
}) {
  const [term, setTerm] = useState('')
  const [position, setPosition] = useState('')
  const debounced = useDebounced(term)
  const results = usePlayerSearch(debounced, season, position)
  const full = selected.length >= MAX_COMPARE

  return (
    <Card>
      <CardHeader>
        <CardTitle>Find players</CardTitle>
        <CardDescription>Search by name. Pick up to two players to compare.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="player-search">Name</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input
                id="player-search"
                className="pl-8"
                placeholder="e.g. Goff, St. Brown"
                value={term}
                onChange={(e) => setTerm(e.target.value)}
                autoComplete="off"
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="player-position">Position</Label>
            <NativeSelect id="player-position" className="w-full" value={position} onChange={(e) => setPosition(e.target.value)}>
              <NativeSelectOption value="">Any</NativeSelectOption>
              {POSITIONS.map((p) => (
                <NativeSelectOption key={p} value={p}>
                  {p}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
        </div>
        {results.isError ? (
          <ErrorState title="Search failed" error={results.error} onRetry={() => void results.refetch()} />
        ) : !results.data ? (
          results.isFetching ? (
            <Skeleton className="h-40" aria-label="Searching players" />
          ) : (
            <p className="text-sm text-muted-foreground">Type at least two letters.</p>
          )
        ) : results.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No players match “{debounced}”{season ? ` in ${season}` : ''}.</p>
        ) : (
          <ul className={cn('flex flex-col divide-y rounded-lg border', results.isPlaceholderData && 'opacity-60')} aria-label="Player results">
            {results.data.items.map((p) => {
              const picked = selected.includes(p.id)
              return (
                <li key={p.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <span className="min-w-0 flex-1 truncate font-medium">{p.name ?? p.id}</span>
                  {p.position && <Badge variant="secondary">{p.position}</Badge>}
                  {p.season_plays !== null && (
                    <span className="hidden text-xs text-muted-foreground tabular-nums sm:inline">{p.season_plays} plays</span>
                  )}
                  <Button
                    size="sm"
                    variant={picked ? 'secondary' : 'outline'}
                    disabled={picked || full}
                    onClick={() => onAdd(p.id)}
                    aria-label={`Compare ${p.name ?? p.id}`}
                  >
                    {picked ? 'Added' : 'Compare'}
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
        {results.data && results.data.total > results.data.items.length && (
          <p className="text-xs text-muted-foreground">
            Showing {results.data.items.length} of {results.data.total}. Refine the name to narrow it down.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function useStats(id: string | undefined, season: number | null) {
  return usePlayerStats(id ?? null, { season })
}

function Comparison({ ids, season, onRemove }: { ids: string[]; season: number | null; onRemove: (id: string) => void }) {
  const a = useStats(ids[0], season)
  const b = useStats(ids[1], season)
  const queries = [a, b].slice(0, ids.length)
  const failed = queries.find((q) => q.isError)
  if (failed) {
    return <ErrorState title="Could not load player stats" error={failed.error} onRetry={() => queries.forEach((q) => void q.refetch())} />
  }
  if (queries.some((q) => !q.data)) {
    return <Skeleton className="h-96" aria-label="Loading player stats" />
  }
  const players = queries.map((q) => q.data as PlayerStats)
  const categories = CATEGORIES.filter((c) =>
    players.some((p) => {
      const v = p[c.key][c.volume]
      return typeof v === 'number' && v > 0
    }),
  )
  const first = players[0] as PlayerStats

  return (
    <div className="flex flex-col gap-4">
      <Warnings warnings={[...new Set(players.flatMap((p) => p.warnings))]} />
      <Card>
        <CardHeader>
          <CardTitle>{players.length === 2 ? 'Side by side' : 'Player statistics'}</CardTitle>
          <CardDescription>{season ? `${season} season` : 'All imported seasons'}, regular season and playoffs.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[22rem] text-sm" aria-label="Player comparison">
            <thead>
              <tr className="text-left align-bottom">
                <th className="py-2 font-medium text-muted-foreground">Stat</th>
                {players.map((p) => (
                  <th key={p.player.id} className="py-2 text-right font-medium">
                    <div className="flex items-center justify-end gap-1">
                      {p.player.name ?? p.player.id}
                      <Button size="icon-xs" variant="ghost" aria-label={`Remove ${p.player.name ?? p.player.id}`} onClick={() => onRemove(p.player.id)}>
                        <X aria-hidden="true" />
                      </Button>
                    </div>
                    <div className="mt-1 flex flex-wrap justify-end gap-1 font-normal">
                      {p.player.position && <Badge variant="secondary">{p.player.position}</Badge>}
                      {p.teams.length > 0 && <Badge variant="outline">{p.teams.join(' / ')}</Badge>}
                      <SampleSizeBadge plays={p.sample.plays} games={p.sample.games} />
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            {categories.length === 0 ? (
              <tbody>
                <tr>
                  <td colSpan={players.length + 1} className="py-6 text-center text-muted-foreground">
                    No passing, rushing or receiving plays in this season.
                  </td>
                </tr>
              </tbody>
            ) : (
              categories.map((c) => (
                <tbody key={c.key}>
                  <tr>
                    <th colSpan={players.length + 1} className="pt-4 pb-1 text-left text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                      {c.label}
                    </th>
                  </tr>
                  {Object.keys(first[c.key]).map((stat) => (
                    <tr key={stat} className="border-t tabular-nums">
                      <td className="py-1.5">{PLAYER_STAT_LABELS[stat] ?? stat.replaceAll('_', ' ')}</td>
                      {players.map((p) => {
                        const v = p[c.key][stat] as StatValue | undefined
                        const d = denominator(v)
                        return (
                          <td key={p.player.id} className="py-1.5 text-right" data-testid={`${p.player.id}-${stat}`}>
                            {display(stat, v)}
                            {d && <span className="ml-1 text-xs text-muted-foreground">({d})</span>}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              ))
            )}
          </table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Limitations</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc pl-4 text-sm text-muted-foreground">
            {first.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Definitions definitions={first.definitions} />
      <DatasetFooter dataset={first.dataset} />
    </div>
  )
}

export function PlayersPage() {
  const [params, setParams] = useSearchParams()
  const seasons = useSeasons()
  const ids = useMemo(() => params.getAll('player').slice(0, MAX_COMPARE), [params])
  const seasonParam = Number(params.get('season'))
  const season = Number.isInteger(seasonParam) && seasonParam >= 1999 ? seasonParam : (seasons.data?.[0]?.season ?? null)

  const update = (nextIds: string[], nextSeason: number | null = season) => {
    const next = new URLSearchParams()
    if (nextSeason !== null) next.set('season', String(nextSeason))
    for (const id of nextIds) next.append('player', id)
    setParams(next, { replace: true })
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Player explorer</h1>
        <p className="mt-1 text-muted-foreground">
          Passing, rushing and receiving production from public play-by-play, with EPA per play.
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="player-season">Season</Label>
            <NativeSelect
              id="player-season"
              className="w-full"
              value={season === null ? '' : String(season)}
              disabled={seasons.isPending}
              onChange={(e) => update(ids, Number(e.target.value))}
            >
              {(seasons.data ?? []).map((s) => (
                <NativeSelectOption key={s.season} value={String(s.season)}>
                  {s.season}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <PlayerSearchPanel season={season} selected={ids} onAdd={(id) => update([...ids, id])} />
        </div>
        <div className="min-w-0">
          {seasons.isError ? (
            <ErrorState title="Could not load seasons" error={seasons.error} onRetry={() => void seasons.refetch()} />
          ) : ids.length === 0 ? (
            <EmptyState title="Pick a player" icon={<UserRound className="size-6 text-muted-foreground" />}>
              Search on the left and add one or two players. Player stats come from public data only; uploads do
              not carry player names.
            </EmptyState>
          ) : (
            <Comparison ids={ids} season={season} onRemove={(id) => update(ids.filter((x) => x !== id))} />
          )}
        </div>
      </div>
    </div>
  )
}
