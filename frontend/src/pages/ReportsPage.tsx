import { zodResolver } from '@hookform/resolvers/zod'
import { FileText, Plus } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ScopePicker } from '@/features/analytics/ScopePicker'
import { parseScope, writeScope, type Scope } from '@/features/analytics/scope'
import {
  DEFAULT_REPORT_FORM,
  reportFormSchema,
  toReportRequest,
  type ReportFormInput,
  type ReportFormValues,
} from '@/features/reports/form'
import { ReportStatusBadge } from '@/features/reports/ReportStatusBadge'
import { useCreateReport, useReports } from '@/hooks/useReports'

function CreateReportForm({ onCancel }: { onCancel: () => void }) {
  const [params, setParams] = useSearchParams()
  const scope = useMemo(() => parseScope(params), [params])
  const setScope = useCallback(
    (next: Scope) => setParams((p) => writeScope(p, next), { replace: true }),
    [setParams],
  )
  const form = useForm<ReportFormInput, unknown, ReportFormValues>({
    resolver: zodResolver(reportFormSchema),
    defaultValues: DEFAULT_REPORT_FORM,
  })
  const create = useCreateReport()
  const navigate = useNavigate()
  const errors = form.formState.errors
  const ready = Boolean(scope.team) && (scope.datasetId !== null || scope.season !== null)

  const submit = form.handleSubmit((values) => {
    create.mutate(toReportRequest(scope, values), {
      onSuccess: (report) => void navigate(`/reports/${report.id}`),
    })
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>New scouting report</CardTitle>
        <CardDescription>
          A rule-based summary of one team: strengths and weaknesses ranked against the league, tendencies, third down
          and red zone. The same inputs always give the same report.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" aria-label="New scouting report" onSubmit={(e) => void submit(e)} noValidate>
          <ScopePicker scope={scope} onChange={setScope} />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="report-season-type">Season phase</Label>
              <NativeSelect id="report-season-type" className="w-full" {...form.register('seasonType')}>
                <NativeSelectOption value="">Regular season + playoffs</NativeSelectOption>
                <NativeSelectOption value="REG">Regular season</NativeSelectOption>
                <NativeSelectOption value="POST">Playoffs</NativeSelectOption>
              </NativeSelect>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="report-week-min">From week</Label>
              <Input id="report-week-min" inputMode="numeric" placeholder="1" aria-invalid={Boolean(errors.weekMin)} {...form.register('weekMin')} />
              {errors.weekMin && <p className="text-xs text-destructive">{errors.weekMin.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="report-week-max">To week</Label>
              <Input id="report-week-max" inputMode="numeric" placeholder="18" aria-invalid={Boolean(errors.weekMax)} {...form.register('weekMax')} />
              {errors.weekMax && <p className="text-xs text-destructive">{errors.weekMax.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="report-opponent">Only against</Label>
              <Input id="report-opponent" placeholder="Any opponent" maxLength={3} aria-invalid={Boolean(errors.opponent)} {...form.register('opponent')} />
              {errors.opponent && <p className="text-xs text-destructive">{errors.opponent.message}</p>}
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="report-title">Title (optional)</Label>
            <Input id="report-title" placeholder="Generated from the team and season" aria-invalid={Boolean(errors.title)} {...form.register('title')} />
            {errors.title && <p className="text-xs text-destructive">{errors.title.message}</p>}
          </div>
          {create.isError && <ErrorState title="Could not create the report" error={create.error} />}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={!ready || create.isPending}>
              {create.isPending ? 'Creating…' : 'Generate report'}
            </Button>
            <Button type="button" variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
            {!scope.team && <span className="self-center text-sm text-muted-foreground">Choose a team first.</span>}
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

function ReportList() {
  const reports = useReports()
  if (reports.isError) {
    return <ErrorState title="Could not load your reports" error={reports.error} onRetry={() => void reports.refetch()} />
  }
  if (!reports.data) return <Skeleton className="h-48" aria-label="Loading reports" />
  if (reports.data.items.length === 0) {
    return (
      <EmptyState title="No saved reports yet" icon={<FileText className="size-6 text-muted-foreground" />}>
        Generate a scouting report for any team. It is saved here so you can reopen, export or print it later.
      </EmptyState>
    )
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Saved reports</CardTitle>
      </CardHeader>
      <CardContent>
        <Table aria-label="Saved reports">
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Data</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="hidden sm:table-cell">Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {reports.data.items.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="max-w-64 truncate">
                  <Link className="font-medium underline-offset-4 hover:underline" to={`/reports/${r.id}`}>
                    {r.title}
                  </Link>
                </TableCell>
                <TableCell>
                  {r.dataset_id ? <Badge variant="outline">Upload</Badge> : <Badge variant="secondary">{r.season}</Badge>}
                </TableCell>
                <TableCell>
                  <ReportStatusBadge status={r.status} />
                </TableCell>
                <TableCell className="hidden text-muted-foreground sm:table-cell">
                  {new Date(r.created_at).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export function ReportsPage() {
  const [params, setParams] = useSearchParams()
  const [open, setOpen] = useState(params.get('new') === '1')
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Scouting reports</h1>
          <p className="mt-1 text-muted-foreground">Saved, exportable summaries built from transparent rules.</p>
        </div>
        {!open && (
          <Button onClick={() => setOpen(true)}>
            <Plus aria-hidden="true" /> New report
          </Button>
        )}
      </div>
      {open && (
        <CreateReportForm
          onCancel={() => {
            setOpen(false)
            setParams(new URLSearchParams(), { replace: true })
          }}
        />
      )}
      <ReportList />
    </div>
  )
}
