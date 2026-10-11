import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { MIN_SAMPLE } from '@/features/compare/SampleSizeBadge'
import { formatDifference, formatValue } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { TendencyCell, ThirdDown } from '@/services/api'

const DISTANCES = ['short', 'medium', 'long'] as const
const DISTANCE_SHORT: Record<string, string> = { short: '1-3', medium: '4-7', long: '8+' }
const DOWN_LABEL = ['1st', '2nd', '3rd', '4th']

/** Pass rate by down and distance against the league, with the play count in every cell. */
export function TendencyGrid({ cells, title = 'Play-calling tendencies' }: { cells: TendencyCell[]; title?: string }) {
  const lookup = new Map(cells.map((c) => [`${c.down}-${c.distance}`, c]))
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>
          Pass rate by down and yards to go, with the league rate below. Cells under {MIN_SAMPLE}{' '}
          plays are faded.
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[28rem] border-separate border-spacing-1 text-sm" aria-label="Pass rate by down and distance">
          <thead>
            <tr>
              <th className="text-left font-medium text-muted-foreground" scope="col">
                Down
              </th>
              {DISTANCES.map((d) => (
                <th key={d} scope="col" className="font-medium text-muted-foreground">
                  <span className="capitalize">{d}</span> ({DISTANCE_SHORT[d]})
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[1, 2, 3, 4].map((down) => (
              <tr key={down}>
                <th scope="row" className="text-left font-medium">
                  {DOWN_LABEL[down - 1]}
                </th>
                {DISTANCES.map((d) => {
                  const cell = lookup.get(`${down}-${d}`)
                  if (!cell || cell.plays === 0) {
                    return (
                      <td key={d} className="rounded-md bg-muted/40 p-2 text-center text-muted-foreground">
                        No plays
                      </td>
                    )
                  }
                  const diff =
                    cell.pass_rate.value !== null && cell.league_pass_rate.value !== null
                      ? cell.pass_rate.value - cell.league_pass_rate.value
                      : null
                  const intensity = cell.pass_rate.value ?? 0
                  return (
                    <td
                      key={d}
                      className={cn('rounded-md p-2 text-center tabular-nums', cell.plays < MIN_SAMPLE && 'opacity-50')}
                      style={{ backgroundColor: `color-mix(in oklch, var(--team-a) ${Math.round(intensity * 45)}%, transparent)` }}
                    >
                      <div className="font-semibold">{formatValue('pass_rate', cell.pass_rate.value)}</div>
                      <div className="text-xs text-muted-foreground">
                        Lg {formatValue('pass_rate', cell.league_pass_rate.value)}
                        {diff !== null && ` (${formatDifference('pass_rate', diff)})`}
                      </div>
                      <div className="text-xs text-muted-foreground">{cell.plays} plays</div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

export function ThirdDownCard({ data }: { data: ThirdDown }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Third down</CardTitle>
        <CardDescription>
          {data.plays} third-down plays in {data.games} games
          {data.avg_yards_to_go !== null && `, ${data.avg_yards_to_go.toFixed(1)} yards to go on average`}.
          {data.converted_by_penalty > 0 && ` ${data.converted_by_penalty} converted by a defensive penalty.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl className="grid grid-cols-3 gap-3 text-sm">
          <div>
            <dt className="text-muted-foreground">Conversion</dt>
            <dd className="text-xl font-semibold tabular-nums" data-testid="third-down-conversion">
              {formatValue('conversion_rate', data.conversion_rate.value)}
            </dd>
            <dd className="text-xs text-muted-foreground">
              League {formatValue('conversion_rate', data.league_conversion_rate.value)}
              {data.rank && ` · rank ${data.rank.rank} of ${data.rank.of}`}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Pass rate</dt>
            <dd className="text-xl font-semibold tabular-nums">{formatValue('pass_rate', data.pass_rate.value)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">EPA / play</dt>
            <dd className="text-xl font-semibold tabular-nums">{formatValue('epa_per_play', data.epa_per_play.value)}</dd>
          </div>
        </dl>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" aria-label="Third down by distance">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1 font-medium">Distance</th>
                <th className="py-1 text-right font-medium">Plays</th>
                <th className="py-1 text-right font-medium">Converted</th>
                <th className="py-1 text-right font-medium">League</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {data.by_distance.map((b) => (
                <tr key={b.distance} className="border-t">
                  <td className="py-1.5 capitalize">
                    {b.distance} ({DISTANCE_SHORT[b.distance] ?? b.distance})
                  </td>
                  <td className="py-1.5 text-right">{b.plays}</td>
                  <td className="py-1.5 text-right">{formatValue('conversion_rate', b.conversion_rate.value)}</td>
                  <td className="py-1.5 text-right text-muted-foreground">
                    {formatValue('conversion_rate', b.league_conversion_rate.value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
