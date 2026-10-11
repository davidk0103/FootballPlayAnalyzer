import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatValue, METRIC_LABELS } from '@/lib/format'
import type { SituationRow, Trends } from '@/services/api'

function chartValue(metric: string, v: number | null | undefined): number | null {
  if (v === null || v === undefined) return null
  return metric.endsWith('_rate') ? Math.round(v * 1000) / 10 : Math.round(v * 1000) / 1000
}

/** One metric per situation: the selected team (or league when no team) against the league. */
export function SituationChart({
  rows,
  metric,
  teamLabel,
}: {
  rows: SituationRow[]
  metric: string
  teamLabel: string | null
}) {
  const unit = metric.endsWith('_rate') ? '%' : ''
  const data = rows.map((r) => ({
    label: r.label,
    [teamLabel ?? 'League']: chartValue(metric, r.metrics[metric]?.value),
    ...(teamLabel && r.league ? { League: chartValue(metric, r.league[metric]?.value) } : {}),
  }))
  return (
    <div
      className="h-72 w-full"
      role="img"
      aria-label={`Bar chart of ${METRIC_LABELS[metric] ?? metric} by situation${teamLabel ? ` for ${teamLabel} and the league` : ''}`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border" />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} interval={0} tickLine={false} />
          <YAxis unit={unit} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
          <Tooltip
            formatter={(value) => (value === null ? 'n/a' : `${String(value)}${unit}`)}
            contentStyle={{ borderRadius: 8, fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey={teamLabel ?? 'League'} fill="var(--team-a)" radius={[4, 4, 0, 0]} />
          {teamLabel && <Bar dataKey="League" fill="var(--muted-foreground)" radius={[4, 4, 0, 0]} />}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function TrendChart({ data, team }: { data: Trends; team: string }) {
  const points = data.games.map((g) => ({
    label: g.week !== null ? `${g.season_type === 'POST' ? 'P' : 'W'}${g.week}` : g.game_key,
    opponent: g.opponent,
    plays: g.plays,
    [team]: chartValue('epa_per_play', g.metrics.epa_per_play?.value),
    'League avg': chartValue('epa_per_play', g.league_epa_per_play),
  }))
  return (
    <div className="h-64 w-full" role="img" aria-label={`Line chart of ${team} EPA per play by game against the league average`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
          <Tooltip
            formatter={(value) => (value === null ? 'n/a' : formatValue('epa_per_play', Number(value)))}
            labelFormatter={(label, payload) => {
              const p = payload[0]?.payload as { opponent?: string | null; plays?: number } | undefined
              return p ? `${String(label)} vs ${p.opponent ?? '?'} (${p.plays ?? 0} plays)` : String(label)
            }}
            contentStyle={{ borderRadius: 8, fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey={team} stroke="var(--team-a)" strokeWidth={2} dot={{ r: 2 }} connectNulls />
          <Line type="monotone" dataKey="League avg" stroke="var(--muted-foreground)" strokeDasharray="4 4" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
