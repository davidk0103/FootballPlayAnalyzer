import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { METRICS } from './metrics'

export function MetricDefinitions({ definitions }: { definitions: Record<string, string> }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>How these are calculated</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          {METRICS.map((m) => (
            <div key={m.key}>
              <dt className="font-medium">{m.label}</dt>
              <dd className="text-muted-foreground">{definitions[m.key] ?? 'No definition provided.'}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}
