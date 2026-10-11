import { Download, FileJson, FileSpreadsheet, Printer, RotateCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ErrorState } from '@/components/StateViews'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { DatasetFooter, Definitions, Warnings } from '@/features/analytics/parts'
import { TendencyGrid, ThirdDownCard } from '@/features/analytics/TendencyGrid'
import { SampleSizeBadge } from '@/features/compare/SampleSizeBadge'
import { ReportStatusBadge } from '@/features/reports/ReportStatusBadge'
import { useCreateExport, useCreateReport, useDeleteReport, useReport } from '@/hooks/useReports'
import { formatBytes, formatDifference, formatValue } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Report, ReportRequest, ScoutingReport, SideReport } from '@/services/api'

const KIND_STYLE = {
  strength: { label: 'Strength', className: 'border-emerald-500/40 bg-emerald-500/5' },
  weakness: { label: 'Weakness', className: 'border-rose-500/40 bg-rose-500/5' },
  tendency: { label: 'Tendency', className: 'border-sky-500/40 bg-sky-500/5' },
} as const

function Findings({ report }: { report: ScoutingReport }) {
  if (report.findings.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Key findings</CardTitle>
          <CardDescription>
            Nothing stands out: no metric ranks in the top or bottom third with enough plays to trust it.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Key findings</CardTitle>
        <CardDescription>
          Top third of the league is a strength, bottom third a weakness; a pass rate at least 5 points from the league
          is a tendency. Only metrics with enough plays qualify.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-2 md:grid-cols-2" aria-label="Key findings">
          {report.findings.map((f) => (
            <li key={`${f.side}-${f.metric}-${f.kind}`} className={cn('rounded-lg border-l-4 border p-3 text-sm', KIND_STYLE[f.kind].className)}>
              <div className="mb-1 flex gap-2">
                <Badge variant="outline">{KIND_STYLE[f.kind].label}</Badge>
                <Badge variant="secondary" className="capitalize">
                  {f.side}
                </Badge>
              </div>
              {f.text}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

function SideTable({ side }: { side: SideReport }) {
  return (
    <Card className="break-inside-avoid">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 capitalize">
          {side.side}
          <SampleSizeBadge plays={side.plays} games={side.games} />
        </CardTitle>
        <CardDescription>{side.side === 'offense' ? 'Plays run.' : 'Plays allowed; lower is better except pass rate.'}</CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[30rem] text-sm" aria-label={`${side.side} metrics`}>
          <thead className="text-left text-muted-foreground">
            <tr>
              <th className="py-1 font-medium">Metric</th>
              <th className="py-1 text-right font-medium">Team</th>
              <th className="py-1 text-right font-medium">League</th>
              <th className="py-1 text-right font-medium">Diff</th>
              <th className="py-1 text-right font-medium">Rank</th>
              <th className="py-1 text-right font-medium">Sample</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {side.metrics.map((m) => {
              const good = m.difference === null || !m.better || m.difference === 0 ? null : (m.difference > 0) === (m.better === 'higher')
              return (
                <tr key={m.name} className="border-t">
                  <td className="py-1.5">{m.label}</td>
                  <td className="py-1.5 text-right font-medium">{formatValue(m.name, m.value)}</td>
                  <td className="py-1.5 text-right text-muted-foreground">{formatValue(m.name, m.league_value)}</td>
                  <td
                    className={cn(
                      'py-1.5 text-right',
                      good === true && 'text-emerald-600 dark:text-emerald-400',
                      good === false && 'text-rose-600 dark:text-rose-400',
                    )}
                  >
                    {formatDifference(m.name, m.difference) || 'n/a'}
                  </td>
                  <td className="py-1.5 text-right">{m.rank !== null ? `${m.rank} / ${m.of}` : 'n/a'}</td>
                  <td className="py-1.5 text-right text-muted-foreground">{m.denominator.toLocaleString()}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

function RedZone({ report }: { report: ScoutingReport }) {
  return (
    <Card className="break-inside-avoid">
      <CardHeader>
        <CardTitle>Red zone</CardTitle>
        <CardDescription>Plays starting inside the opponent 20.</CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm" aria-label="Red zone">
          <thead className="text-left text-muted-foreground">
            <tr>
              <th className="py-1 font-medium">Side</th>
              <th className="py-1 text-right font-medium">Plays</th>
              <th className="py-1 text-right font-medium">TD rate</th>
              <th className="py-1 text-right font-medium">League</th>
              <th className="py-1 text-right font-medium">EPA / play</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {[report.offense, report.defense].map((s) => (
              <tr key={s.side} className="border-t">
                <td className="py-1.5 capitalize">{s.side}</td>
                <td className="py-1.5 text-right">{s.red_zone.plays}</td>
                <td className="py-1.5 text-right font-medium">{formatValue('touchdown_rate', s.red_zone.touchdown_rate.value)}</td>
                <td className="py-1.5 text-right text-muted-foreground">
                  {formatValue('touchdown_rate', s.league_red_zone.touchdown_rate.value)}
                </td>
                <td className="py-1.5 text-right">{formatValue('epa_per_play', s.red_zone.epa_per_play.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

const CATEGORY_LABEL = { passing: 'Passing', rushing: 'Rushing', receiving: 'Receiving' } as const
const VOLUME_LABEL = { passing: 'att', rushing: 'car', receiving: 'tgt' } as const

function Leaders({ report }: { report: ScoutingReport }) {
  if (report.top_players.length === 0) return null
  return (
    <Card className="break-inside-avoid">
      <CardHeader>
        <CardTitle>Top players</CardTitle>
        <CardDescription>By yards, from public play-by-play.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-3">
        {(['passing', 'rushing', 'receiving'] as const).map((cat) => (
          <div key={cat}>
            <h3 className="mb-1 text-sm font-medium">{CATEGORY_LABEL[cat]}</h3>
            <ol className="flex flex-col gap-1 text-sm">
              {report.top_players
                .filter((p) => p.category === cat)
                .map((p) => (
                  <li key={p.player_id} className="flex justify-between gap-2 tabular-nums">
                    <Link to={`/players?player=${encodeURIComponent(p.player_id)}${report.filters.season ? `&season=${report.filters.season}` : ''}`} className="truncate hover:underline">
                      {p.name ?? p.player_id}
                    </Link>
                    <span className="text-muted-foreground">
                      {p.yards.toLocaleString()} yds · {p.volume} {VOLUME_LABEL[cat]}
                    </span>
                  </li>
                ))}
            </ol>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function Exports({ report }: { report: Report }) {
  const create = useCreateExport(report.id)
  const pending = report.exports.some((e) => e.status === 'pending')
  return (
    <Card className="print:hidden">
      <CardHeader>
        <CardTitle>Export</CardTitle>
        <CardDescription>CSV for spreadsheets, JSON for code. Files are built in the background.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" disabled={create.isPending || pending} onClick={() => create.mutate('csv')}>
            <FileSpreadsheet aria-hidden="true" /> Export CSV
          </Button>
          <Button variant="outline" size="sm" disabled={create.isPending || pending} onClick={() => create.mutate('json')}>
            <FileJson aria-hidden="true" /> Export JSON
          </Button>
        </div>
        {create.isError && <p className="text-sm text-destructive">{create.error.message}</p>}
        {report.exports.length > 0 && (
          <ul className="flex flex-col divide-y rounded-lg border text-sm" aria-label="Exports">
            {report.exports.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                <Badge variant="secondary" className="uppercase">
                  {e.format}
                </Badge>
                <span className="text-muted-foreground">{new Date(e.created_at).toLocaleString()}</span>
                <span className="ml-auto flex items-center gap-2">
                  {e.status === 'pending' && <span className="text-muted-foreground">Building…</span>}
                  {e.status === 'failed' && <span className="text-destructive">{e.error ?? 'Failed'}</span>}
                  {e.status === 'ready' && e.download_url && (
                    <a href={e.download_url} className={buttonVariants({ size: 'sm' })} download>
                      <Download aria-hidden="true" /> Download{e.size_bytes !== null && ` (${formatBytes(e.size_bytes)})`}
                    </a>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function ReportBody({ report }: { report: ScoutingReport }) {
  return (
    <div className="flex flex-col gap-4">
      <Warnings warnings={report.warnings} />
      <Findings report={report} />
      <div className="grid gap-4 xl:grid-cols-2 print:grid-cols-1">
        <SideTable side={report.offense} />
        <SideTable side={report.defense} />
      </div>
      <div className="grid gap-4 xl:grid-cols-2 print:grid-cols-1">
        <ThirdDownCard data={report.offense.third_down} />
        <RedZone report={report} />
      </div>
      <TendencyGrid cells={report.tendencies} title="Offensive play-calling tendencies" />
      <Leaders report={report} />
      <Card className="break-inside-avoid">
        <CardHeader>
          <CardTitle>Limitations</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc pl-4 text-sm text-muted-foreground">
            {report.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Definitions definitions={report.definitions} />
      <DatasetFooter dataset={report.dataset} />
      <p className="text-xs text-muted-foreground">Generated {new Date(report.generated_at).toLocaleString()} by PlaybookIQ.</p>
    </div>
  )
}

function describe(report: Report): string {
  const f = report.filters as Partial<ReportRequest>
  const parts = [report.team, report.dataset_id ? 'your upload' : String(report.season)]
  if (f.season_type) parts.push(f.season_type === 'REG' ? 'regular season' : 'playoffs')
  if (f.week_min || f.week_max) parts.push(`weeks ${f.week_min ?? 1}-${f.week_max ?? 22}`)
  if (f.opponent) parts.push(`vs ${f.opponent}`)
  return parts.join(' · ')
}

export function ReportDetailPage() {
  const { id = '' } = useParams()
  const report = useReport(id)
  const remove = useDeleteReport()
  const retry = useCreateReport()
  const navigate = useNavigate()
  const [confirming, setConfirming] = useState(false)

  if (report.isError) {
    return <ErrorState title="Could not load this report" error={report.error} onRetry={() => void report.refetch()} />
  }
  if (!report.data) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading report">
        <Skeleton className="h-12 w-80" />
        <Skeleton className="h-40" />
        <Skeleton className="h-96" />
      </div>
    )
  }
  const r = report.data
  return (
    <article className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to="/reports" className="text-sm text-muted-foreground hover:underline print:hidden">
            ← Saved reports
          </Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-3 text-2xl font-semibold tracking-tight">
            {r.title}
            <span className="print:hidden">
              <ReportStatusBadge status={r.status} />
            </span>
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{describe(r)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 print:hidden">
          <Button variant="outline" size="sm" disabled={r.status !== 'ready'} onClick={() => window.print()}>
            <Printer aria-hidden="true" /> Print
          </Button>
          {confirming ? (
            <>
              <Button
                variant="destructive"
                size="sm"
                disabled={remove.isPending}
                onClick={() => remove.mutate(r.id, { onSuccess: () => void navigate('/reports') })}
              >
                Delete report
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
                Keep
              </Button>
            </>
          ) : (
            <Button variant="outline" size="sm" disabled={r.status === 'pending'} onClick={() => setConfirming(true)}>
              <Trash2 aria-hidden="true" /> Delete
            </Button>
          )}
        </div>
      </div>

      {r.status === 'pending' && (
        <Card>
          <CardContent className="flex flex-col gap-2" aria-live="polite">
            <p className="text-sm font-medium">Generating the report…</p>
            <Progress value={null} aria-label="Generating report" />
            <p className="text-xs text-muted-foreground">This usually takes a few seconds. The page updates on its own.</p>
          </CardContent>
        </Card>
      )}
      {r.status === 'failed' && (
        <Alert variant="destructive">
          <AlertTitle>The report could not be generated</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-2">
            {r.error ?? 'Unknown error.'}
            <Button
              size="sm"
              variant="outline"
              disabled={retry.isPending}
              onClick={() =>
                retry.mutate(
                  { ...(r.filters as ReportRequest), title: r.title, idempotency_key: null },
                  { onSuccess: (next) => void navigate(`/reports/${next.id}`) },
                )
              }
            >
              <RotateCw aria-hidden="true" /> Try again
            </Button>
            {retry.isError && <span>{retry.error.message}</span>}
          </AlertDescription>
        </Alert>
      )}
      {r.status === 'ready' && r.report && (
        <>
          <Exports report={r} />
          <ReportBody report={r.report} />
        </>
      )}
    </article>
  )
}
