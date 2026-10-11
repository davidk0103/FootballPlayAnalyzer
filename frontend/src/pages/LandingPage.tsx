import { ArrowRight, BarChart3, FileText, Filter, Ruler, Upload, UserRound } from 'lucide-react'
import { Link } from 'react-router-dom'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

const FEATURES = [
  {
    icon: BarChart3,
    title: 'Efficiency, not box scores',
    body: 'EPA per play, success rate, third-down conversion and explosive plays, ranked against the league.',
    to: '/overview?team=DET&season=2024',
  },
  {
    icon: Filter,
    title: 'Situational explorer',
    body: 'Break any team, or the whole league, down by down, distance, field position, quarter and score.',
    to: '/situational?team=KC&season=2024&group_by=down',
  },
  {
    icon: UserRound,
    title: 'Player explorer',
    body: 'Search passers, rushers and receivers and compare two of them side by side.',
    to: '/players',
  },
  {
    icon: Upload,
    title: 'Your own data',
    body: 'Upload a play-by-play CSV, map its columns, and analyze it with the same metrics. Private to you.',
    to: '/uploads',
  },
  {
    icon: FileText,
    title: 'Scouting reports',
    body: 'Rule-based strengths, weaknesses and tendencies, saved for later and exportable as CSV or JSON.',
    to: '/reports?new=1',
  },
  {
    icon: Ruler,
    title: 'Honest numbers',
    body: 'Every metric shows its numerator, denominator and sample size. No data means n/a, never 0.',
    to: '/compare?team_a=KC&team_b=PHI&season=2024',
  },
]

export function LandingPage() {
  return (
    <div className="flex flex-col gap-12 py-6 sm:py-12">
      <section className="max-w-2xl">
        <p className="text-sm font-medium text-team-a">NFL play-by-play analytics</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight sm:text-5xl">
          Scout any team in minutes, from every snap.
        </h1>
        <p className="mt-4 text-lg text-muted-foreground">
          PlaybookIQ turns public nflverse play-by-play, or your own uploaded charting, into situational splits, player
          comparisons and saved scouting reports you can print or export.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link to="/overview?team=DET&season=2024" className={buttonVariants({ size: 'lg' })}>
            Explore the 2024 Lions <ArrowRight aria-hidden="true" />
          </Link>
          <Link to="/reports?new=1" className={buttonVariants({ size: 'lg', variant: 'outline' })}>
            Build a scouting report
          </Link>
          <Link to="/uploads" className={buttonVariants({ size: 'lg', variant: 'ghost' })}>
            Upload your data
          </Link>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, body, to }) => (
          <Link key={title} to={to} className="group rounded-xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
            <Card className="h-full transition-colors group-hover:bg-muted/40">
              <CardContent>
                <Icon className="size-5 text-team-a" aria-hidden="true" />
                <h2 className="mt-3 font-medium">{title}</h2>
                <p className="mt-1 text-sm text-muted-foreground">{body}</p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </section>
    </div>
  )
}
