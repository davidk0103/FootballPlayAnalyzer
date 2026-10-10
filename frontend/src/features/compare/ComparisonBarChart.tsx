import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { TeamStats } from '@/services/api'
import { METRICS } from './metrics'

const toPct = (v: number | null) => (v === null ? null : Math.round(v * 1000) / 10)

export function ComparisonBarChart({ a, b }: { a: TeamStats; b: TeamStats }) {
  const teamA = a.team.abbreviation
  const teamB = b.team.abbreviation
  const data = METRICS.filter((m) => m.chart).map((m) => ({
    metric: m.short,
    [teamA]: toPct(a.metrics[m.key].value),
    [teamB]: toPct(b.metrics[m.key].value),
  }))

  return (
    <Card>
      <CardHeader>
        <CardTitle>Rate comparison</CardTitle>
        <CardDescription>
          Percent of scrimmage plays. Missing bars mean no qualifying plays.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-72 w-full" role="img" aria-label={`Bar chart comparing ${teamA} and ${teamB}`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border" />
              <XAxis dataKey="metric" tick={{ fontSize: 12 }} interval={0} tickLine={false} />
              <YAxis unit="%" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
              <Tooltip
                formatter={(value) => (value === null ? 'n/a' : `${String(value)}%`)}
                contentStyle={{ borderRadius: 8, fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey={teamA} fill="var(--team-a)" radius={[4, 4, 0, 0]} />
              <Bar dataKey={teamB} fill="var(--team-b)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
