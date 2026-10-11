import { ArrowRight, CheckCircle2, Play, ShieldCheck, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Warnings } from '@/features/analytics/parts'
import { JobProgress } from '@/features/jobs/JobProgress'
import { UploadStatusBadge } from '@/features/uploads/UploadStatusBadge'
import {
  useDeleteUpload,
  useProcessUpload,
  useRejectedRows,
  useUpload,
  useUploadTeams,
  useValidateUpload,
} from '@/hooks/useUploads'
import { formatBytes } from '@/lib/format'
import type { MappingValidation, UploadDetail } from '@/services/api'

const EDITABLE = ['uploaded', 'validated', 'failed']
const NONE = ''

function Preview({ upload }: { upload: UploadDetail }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Preview</CardTitle>
        <CardDescription>
          First {upload.preview.length} of {upload.row_count.toLocaleString()} rows, {upload.columns.length} columns,
          delimited by {upload.delimiter === '\t' ? 'tabs' : `“${upload.delimiter}”`}. Shown as plain text.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="max-h-80 overflow-auto rounded-lg border">
          <Table aria-label="File preview" className="text-xs">
            <TableHeader className="sticky top-0 bg-card">
              <TableRow>
                <TableHead className="w-10 text-right">#</TableHead>
                {upload.columns.map((c) => (
                  <TableHead key={c} className="font-mono">
                    {c}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {upload.preview.map((row, i) => (
                <TableRow key={i}>
                  <TableCell className="text-right text-muted-foreground">{i + 1}</TableCell>
                  {upload.columns.map((c, j) => (
                    <TableCell key={c} className="max-w-48 truncate font-mono" title={row[j]}>
                      {row[j]}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function ValidationResult({ result }: { result: MappingValidation }) {
  if (result.mapping_errors.length > 0) {
    return (
      <Alert variant="destructive" data-testid="mapping-errors">
        <AlertTitle>Fix the mapping</AlertTitle>
        <AlertDescription>
          <ul className="list-disc pl-4">
            {result.mapping_errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </AlertDescription>
      </Alert>
    )
  }
  return (
    <div className="flex flex-col gap-3" data-testid="validation-result">
      <Alert>
        <CheckCircle2 aria-hidden="true" />
        <AlertTitle>Mapping works</AlertTitle>
        <AlertDescription>
          Checked the first {result.checked_rows.toLocaleString()} of {result.total_rows.toLocaleString()} rows:{' '}
          {result.accepted_rows.toLocaleString()} accepted, {result.rejected_rows.toLocaleString()} would be set aside.
          Rejected rows are kept for review, not silently dropped.
        </AlertDescription>
      </Alert>
      <Warnings warnings={result.warnings} title="Heads up" />
      {result.issues.length > 0 && <IssueTable issues={result.issues} title="Example problems in the sample" />}
    </div>
  )
}

function IssueTable({ issues, title }: { issues: MappingValidation['issues']; title: string }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">{title}</h3>
      <div className="max-h-72 overflow-auto rounded-lg border">
        <Table aria-label={title} className="text-xs">
          <TableHeader>
            <TableRow>
              <TableHead className="w-16 text-right">Row</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead className="hidden md:table-cell">Values</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {issues.map((issue) => (
              <TableRow key={issue.row_number}>
                <TableCell className="text-right tabular-nums">{issue.row_number}</TableCell>
                <TableCell className="whitespace-normal">{issue.reason}</TableCell>
                <TableCell className="hidden max-w-96 truncate font-mono text-muted-foreground md:table-cell">
                  {Object.entries(issue.values)
                    .map(([k, v]) => `${k}=${v}`)
                    .join(', ')}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function MappingEditor({ upload }: { upload: UploadDetail }) {
  const [mapping, setMapping] = useState<Record<string, string>>(() => ({
    ...upload.suggested_mapping,
    ...(upload.mapping ?? {}),
  }))
  const validate = useValidateUpload(upload.id)
  const process = useProcessUpload(upload.id)
  const editable = EDITABLE.includes(upload.status) && upload.file_retained
  const canProcess = editable && upload.status !== 'uploaded' && upload.mapping !== null && !validate.isPending
  const sample = (column: string) => {
    const j = upload.columns.indexOf(column)
    return j < 0 ? [] : upload.preview.slice(0, 3).map((r) => r[j] ?? '')
  }
  const used = new Set(Object.values(mapping).filter(Boolean))
  const missing = upload.schema_fields.filter((f) => f.required && !mapping[f.name])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Map columns</CardTitle>
        <CardDescription>
          We matched what we could from the header names. Required fields are marked; anything else is optional and
          leaves its metric as n/a when missing.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="overflow-x-auto">
          <Table aria-label="Column mapping">
            <TableHeader>
              <TableRow>
                <TableHead>PlaybookIQ field</TableHead>
                <TableHead>Your column</TableHead>
                <TableHead className="hidden lg:table-cell">Sample values</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {upload.schema_fields.map((field) => {
                const column = mapping[field.name] ?? NONE
                return (
                  <TableRow key={field.name}>
                    <TableCell className="align-top whitespace-normal">
                      <div className="flex items-center gap-2 font-medium">
                        {field.label}
                        {field.required && <Badge variant="outline">Required</Badge>}
                      </div>
                      <p className="max-w-72 text-xs text-muted-foreground">{field.description}</p>
                    </TableCell>
                    <TableCell className="align-top">
                      <NativeSelect
                        aria-label={`Column for ${field.label}`}
                        className="w-44"
                        disabled={!editable}
                        value={column}
                        onChange={(e) => {
                          validate.reset()
                          setMapping((m) => ({ ...m, [field.name]: e.target.value }))
                        }}
                      >
                        <NativeSelectOption value={NONE}>{field.required ? 'Choose a column' : 'Not in file'}</NativeSelectOption>
                        {upload.columns.map((c) => (
                          <NativeSelectOption key={c} value={c} disabled={used.has(c) && c !== column}>
                            {c}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                    </TableCell>
                    <TableCell className="hidden max-w-56 truncate align-top font-mono text-xs text-muted-foreground lg:table-cell">
                      {column ? sample(column).join(' · ') : ''}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
        {!upload.file_retained && (
          <p className="text-sm text-muted-foreground">
            The original file was deleted after processing, so the mapping is read-only. Upload the file again to remap.
          </p>
        )}
        {validate.isError && <ErrorState title="Validation failed" error={validate.error} />}
        {validate.data && <ValidationResult result={validate.data} />}
        {process.isError && <ErrorState title="Could not start processing" error={process.error} />}
        {editable && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant={canProcess ? 'outline' : 'default'}
              disabled={validate.isPending || missing.length > 0}
              onClick={() => validate.mutate(mapping)}
            >
              <ShieldCheck aria-hidden="true" /> {validate.isPending ? 'Checking…' : 'Check mapping'}
            </Button>
            <Button disabled={!canProcess || process.isPending} onClick={() => process.mutate()}>
              <Play aria-hidden="true" /> {process.isPending ? 'Starting…' : 'Process all rows'}
            </Button>
            {missing.length > 0 && (
              <span className="text-sm text-muted-foreground">
                Map {missing.map((f) => f.label).join(', ')} first.
              </span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function Rejected({ id, total }: { id: string; total: number }) {
  const [page, setPage] = useState(1)
  const rows = useRejectedRows(id, page, total > 0)
  if (total === 0) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle>Rows set aside ({total.toLocaleString()})</CardTitle>
        <CardDescription>These rows failed a check and are not part of any metric.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {rows.isError ? (
          <ErrorState title="Could not load rejected rows" error={rows.error} onRetry={() => void rows.refetch()} />
        ) : !rows.data ? (
          <Skeleton className="h-40" />
        ) : (
          <>
            <IssueTable issues={rows.data.items} title="Rejected rows" />
            {rows.data.total > rows.data.stored_limit && (
              <p className="text-xs text-muted-foreground">Only the first {rows.data.stored_limit} are kept for review.</p>
            )}
            {rows.data.total > rows.data.page_size && (
              <div className="flex items-center gap-2 text-sm">
                <Button size="sm" variant="outline" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
                  Previous
                </Button>
                <span className="text-muted-foreground">Page {page}</span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page * rows.data.page_size >= Math.min(rows.data.total, rows.data.stored_limit)}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

function ReadySummary({ upload }: { upload: UploadDetail }) {
  const teams = useUploadTeams(upload.id, true)
  const q = `dataset=${upload.id}`
  return (
    <Card>
      <CardHeader>
        <CardTitle>Processed</CardTitle>
        <CardDescription>
          {upload.stored_count?.toLocaleString()} plays stored, {upload.rejected_count?.toLocaleString() ?? 0} set aside
          {upload.seasons.length > 0 && ` · seasons ${upload.seasons.join(', ')}`}.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Warnings warnings={upload.warnings} title="Heads up" />
        <div className="flex flex-wrap gap-2">
          <Link to={`/situational?${q}`} className={buttonVariants({ size: 'sm' })}>
            Explore situations <ArrowRight aria-hidden="true" />
          </Link>
          <Link to={`/overview?${q}`} className={buttonVariants({ size: 'sm', variant: 'outline' })}>
            Team overview
          </Link>
          <Link to={`/reports?new=1&${q}`} className={buttonVariants({ size: 'sm', variant: 'outline' })}>
            Scouting report
          </Link>
        </div>
        {teams.isError ? (
          <ErrorState title="Could not load teams" error={teams.error} onRetry={() => void teams.refetch()} />
        ) : !teams.data ? (
          <Skeleton className="h-24" />
        ) : (
          <div className="max-h-64 overflow-auto rounded-lg border">
            <Table aria-label="Teams in this upload" className="text-sm">
              <TableHeader>
                <TableRow>
                  <TableHead>Team</TableHead>
                  <TableHead className="text-right">Offense plays</TableHead>
                  <TableHead className="text-right">Defense plays</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className="tabular-nums">
                {teams.data.map((t) => (
                  <TableRow key={t.abbreviation}>
                    <TableCell>{t.abbreviation}</TableCell>
                    <TableCell className="text-right">{t.offense_plays.toLocaleString()}</TableCell>
                    <TableCell className="text-right">{t.defense_plays.toLocaleString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function DeleteButton({ id, disabled }: { id: string; disabled: boolean }) {
  const [confirming, setConfirming] = useState(false)
  const remove = useDeleteUpload()
  const navigate = useNavigate()
  if (!confirming) {
    return (
      <Button variant="outline" size="sm" disabled={disabled} onClick={() => setConfirming(true)}>
        <Trash2 aria-hidden="true" /> Delete
      </Button>
    )
  }
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-muted-foreground">Delete this upload and its plays?</span>
      <Button
        variant="destructive"
        size="sm"
        disabled={remove.isPending}
        onClick={() => remove.mutate(id, { onSuccess: () => void navigate('/uploads') })}
      >
        Delete
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
        Keep
      </Button>
      {remove.isError && <span className="text-sm text-destructive">{remove.error.message}</span>}
    </div>
  )
}

export function UploadDetailPage() {
  const { id = '' } = useParams()
  const upload = useUpload(id)

  if (upload.isError) {
    return <ErrorState title="Could not load this upload" error={upload.error} onRetry={() => void upload.refetch()} />
  }
  if (!upload.data) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading upload">
        <Skeleton className="h-12 w-72" />
        <Skeleton className="h-64" />
        <Skeleton className="h-96" />
      </div>
    )
  }
  const u = upload.data
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to="/uploads" className="text-sm text-muted-foreground hover:underline">
            ← Your data
          </Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-3 text-2xl font-semibold tracking-tight">
            <span className="truncate">{u.name}</span>
            <UploadStatusBadge status={u.status} />
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {u.original_filename} · {formatBytes(u.size_bytes)} · uploaded {new Date(u.created_at).toLocaleString()}
          </p>
        </div>
        <DeleteButton id={u.id} disabled={u.status === 'processing'} />
      </div>

      {u.status === 'failed' && u.error && (
        <Alert variant="destructive">
          <AlertTitle>Processing failed</AlertTitle>
          <AlertDescription>{u.error} Adjust the mapping and try again.</AlertDescription>
        </Alert>
      )}
      {u.status === 'processing' && (
        <Card>
          <CardHeader>
            <CardTitle>Processing</CardTitle>
            <CardDescription>Checking and storing every row. You can leave this page; it keeps going.</CardDescription>
          </CardHeader>
          <CardContent>
            {u.job ? <JobProgress job={u.job} label="Processing upload" /> : <Skeleton className="h-8" />}
          </CardContent>
        </Card>
      )}
      {u.status === 'ready' && <ReadySummary upload={u} />}
      {u.status === 'ready' && <Rejected id={u.id} total={u.rejected_count ?? 0} />}
      {u.status !== 'processing' && <MappingEditor key={u.id} upload={u} />}
      {u.preview.length > 0 ? <Preview upload={u} /> : <EmptyState title="No preview rows" />}
    </div>
  )
}
