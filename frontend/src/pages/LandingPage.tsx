import { ArrowRight, BarChart3, Filter, Ruler } from 'lucide-react'
import { Link } from 'react-router-dom'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

const FEATURES = [
  {
    icon: BarChart3,
    title: 'Efficiency, not box scores',
    body: 'EPA per play, success rate, third-down conversion, and explosive plays for any two teams.',
  },
  {
    icon: Filter,
    title: 'Situational slices',
    body: 'Filter by down, distance, field position, quarter, play type, and offense or defense.',
  },
  {
    icon: Ruler,
    title: 'Honest numbers',
    body: 'Every metric shows its numerator, denominator, and sample size. No data means n/a, never 0.',
  },
]

export function LandingPage() {
  return (
    <div className="flex flex-col gap-12 py-6 sm:py-12">
      <section className="max-w-2xl">
        <p className="text-sm font-medium text-team-a">NFL play-by-play analytics</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight sm:text-5xl">
          See how two teams really stack up.
        </h1>
        <p className="mt-4 text-lg text-muted-foreground">
          PlaybookIQ turns every snap from the 2023 and 2024 NFL seasons into side-by-side team
          comparisons you can slice by situation.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link to="/compare?team_a=KC&team_b=PHI&season=2024" className={buttonVariants({ size: 'lg' })}>
            Compare Chiefs vs Eagles <ArrowRight aria-hidden="true" />
          </Link>
          <Link to="/compare" className={buttonVariants({ size: 'lg', variant: 'outline' })}>
            Pick your own matchup
          </Link>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, body }) => (
          <Card key={title}>
            <CardContent>
              <Icon className="size-5 text-team-a" aria-hidden="true" />
              <h2 className="mt-3 font-medium">{title}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{body}</p>
            </CardContent>
          </Card>
        ))}
      </section>
    </div>
  )
}
