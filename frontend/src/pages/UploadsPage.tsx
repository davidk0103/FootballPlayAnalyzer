import { FileSpreadsheet, FileUp, Upload as UploadIcon } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { UploadStatusBadge } from '@/features/uploads/UploadStatusBadge'
import { checkFile, displayName } from '@/features/uploads/validation'
import { useCreateUpload, useMyUploads } from '@/hooks/useUploads'
import { formatBytes } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ApiError } from '@/services/api'

function uploadError(error: unknown): { message: string; existingId: string | null } {
  if (error instanceof ApiError) {
    const details = error.details as { existing_upload_id?: string } | null
    return { message: error.message, existingId: error.code === 'duplicate_upload' ? (details?.existing_upload_id ?? null) : null }
  }
  return { message: error instanceof Error ? error.message : 'Upload failed.', existingId: null }
}

function Dropzone() {
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const create = useCreateUpload()
  const navigate = useNavigate()

  const choose = (f: File | undefined) => {
    create.reset()
    if (!f) return
    const issue = checkFile(f)
    setProblem(issue)
    setFile(issue ? null : f)
    if (!issue) setName(displayName(f))
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    choose(e.dataTransfer.files[0])
  }

  const submit = () => {
    if (!file) return
    create.mutate(
      { file, name: name.trim() || undefined },
      { onSuccess: (upload) => void navigate(`/uploads/${upload.id}`) },
    )
  }
  const failure = create.isError ? uploadError(create.error) : null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload play-by-play</CardTitle>
        <CardDescription>
          A CSV with one row per play, up to 25 MB and 200,000 rows. You will map its columns to PlaybookIQ fields
          next. Uploads are private to your account.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div
          role="button"
          tabIndex={0}
          aria-label="Choose a CSV file or drop it here"
          className={cn(
            'flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
            dragging ? 'border-primary bg-primary/5' : 'hover:bg-muted/50',
          )}
          onClick={() => input.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              input.current?.click()
            }
          }}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <FileUp className="size-7 text-muted-foreground" aria-hidden="true" />
          {file ? (
            <p className="text-sm">
              <span className="font-medium">{file.name}</span>{' '}
              <span className="text-muted-foreground">({formatBytes(file.size)})</span>
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Choose a file</span> or drag it here
            </p>
          )}
          <input
            ref={input}
            type="file"
            accept=".csv,.tsv,.txt,text/csv"
            className="sr-only"
            data-testid="file-input"
            tabIndex={-1}
            onChange={(e) => {
              choose(e.target.files?.[0])
              e.target.value = ''
            }}
          />
        </div>
        {problem && (
          <p role="alert" className="text-sm text-destructive">
            {problem}
          </p>
        )}
        {file && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="upload-name">Name</Label>
            <Input id="upload-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
          </div>
        )}
        {failure && (
          <Alert variant="destructive">
            <AlertTitle>Upload rejected</AlertTitle>
            <AlertDescription>
              {failure.message}
              {failure.existingId && (
                <>
                  {' '}
                  <Link className="underline" to={`/uploads/${failure.existingId}`}>
                    Open the existing upload
                  </Link>
                  .
                </>
              )}
            </AlertDescription>
          </Alert>
        )}
        <div>
          <Button onClick={submit} disabled={!file || create.isPending}>
            <UploadIcon aria-hidden="true" /> {create.isPending ? 'Uploading and checking…' : 'Upload and check'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function UploadList() {
  const uploads = useMyUploads()
  if (uploads.isError) {
    return <ErrorState title="Could not load your uploads" error={uploads.error} onRetry={() => void uploads.refetch()} />
  }
  if (!uploads.data) return <Skeleton className="h-48" aria-label="Loading uploads" />
  if (uploads.data.items.length === 0) {
    return (
      <EmptyState title="No uploads yet" icon={<FileSpreadsheet className="size-6 text-muted-foreground" />}>
        Upload a play-by-play CSV (for example an nflverse export, or your own charting) to analyze it with the same
        metrics as the public data.
      </EmptyState>
    )
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Your uploads</CardTitle>
      </CardHeader>
      <CardContent>
        <Table aria-label="Your uploads">
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Rows</TableHead>
              <TableHead className="hidden sm:table-cell">Uploaded</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {uploads.data.items.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="max-w-48 truncate">
                  <Link className="font-medium underline-offset-4 hover:underline" to={`/uploads/${u.id}`}>
                    {u.name}
                  </Link>
                </TableCell>
                <TableCell>
                  <UploadStatusBadge status={u.status} />
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {u.stored_count !== null ? `${u.stored_count.toLocaleString()} plays` : u.row_count.toLocaleString()}
                </TableCell>
                <TableCell className="hidden text-muted-foreground sm:table-cell">
                  {new Date(u.created_at).toLocaleDateString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export function UploadsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Your data</h1>
        <p className="mt-1 text-muted-foreground">
          Bring your own play-by-play. Once processed it works everywhere the public data does.
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Dropzone />
        <UploadList />
      </div>
    </div>
  )
}
